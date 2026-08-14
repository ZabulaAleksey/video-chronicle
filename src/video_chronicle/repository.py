"""Project repository port plus in-memory and durable JSON adapters."""

from __future__ import annotations

import json
import os
import secrets
import stat
import time
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Iterator, Protocol, runtime_checkable

from .project import ProjectState
from .serialization import project_from_mapping, project_to_mapping


class ProjectNotFoundError(KeyError):
    """Raised when a project ID is absent from a repository."""


class RevisionConflictError(RuntimeError):
    """An optimistic writer no longer owns the expected revision."""


class ProjectRepositoryError(RuntimeError):
    """Durable project storage could not complete safely."""


@runtime_checkable
class ProjectRepository(Protocol):
    def save(self, state: ProjectState, *, expected_revision: int | None = None) -> ProjectState | None: ...
    def get(self, project_id: str) -> ProjectState: ...
    def list_project_ids(self) -> tuple[str, ...]: ...
    def restore_backup(self, project_id: str, *, expected_revision: int) -> ProjectState: ...


class InMemoryProjectRepository:
    """Process-local reference adapter with the durable revision policy."""

    def __init__(self) -> None:
        self._projects: dict[str, ProjectState] = {}
        self._backups: dict[str, ProjectState] = {}

    def save(self, state: ProjectState, *, expected_revision: int | None = None) -> ProjectState | None:
        if not isinstance(state, ProjectState):
            raise TypeError("state must be ProjectState")
        if expected_revision is None:  # MODEL-001 compatibility path.
            previous = self._projects.get(state.project_id)
            if previous is not None:
                self._backups[state.project_id] = previous
            self._projects[state.project_id] = state
            return None
        current = self._projects.get(state.project_id)
        actual = current.revision if current is not None else 0
        if actual != expected_revision:
            raise RevisionConflictError(f"expected revision {expected_revision}, found {actual}")
        published = replace(
            state,
            revision=max(state.revision, expected_revision + 1),
            migrated_from_v1=False,
        )
        if current is not None:
            self._backups[state.project_id] = current
        self._projects[state.project_id] = published
        return published

    def get(self, project_id: str) -> ProjectState:
        try:
            return self._projects[project_id]
        except KeyError as exc:
            raise ProjectNotFoundError(project_id) from exc

    def list_project_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._projects))

    def restore_backup(self, project_id: str, *, expected_revision: int) -> ProjectState:
        current = self.get(project_id)
        if current.revision != expected_revision:
            raise RevisionConflictError(f"expected revision {expected_revision}, found {current.revision}")
        try:
            backup = self._backups[project_id]
        except KeyError as exc:
            raise ProjectNotFoundError(f"backup:{project_id}") from exc
        restored = replace(backup, revision=expected_revision + 1, migrated_from_v1=False)
        self._backups[project_id] = current
        self._projects[project_id] = restored
        return restored


class JsonProjectRepository:
    """Strict schema-v2 files with per-project locks, backup, and rollback."""

    LOCK_TIMEOUT = 5.0
    MAX_PROJECT_BYTES = 16 * 1024 * 1024

    def __init__(self, root: Path) -> None:
        raw = str(root)
        if raw.replace("/", "\\").startswith(("\\\\", "\\??\\", "\\.\\")):
            raise ProjectRepositoryError("project root must not be UNC/device syntax")
        self.root = Path(os.path.abspath(root.expanduser()))
        if self.root == Path(self.root.anchor):
            raise ProjectRepositoryError("project root must not be a filesystem root")
        _reject_reparse_ancestors(self.root)
        created = not self.root.exists()
        if not created:
            _require_safe_directory(self.root)
        else:
            self.root.mkdir(parents=True, mode=0o700)
        if os.name == "nt":
            from .cache import _apply_and_verify_windows_owner_acl, _verify_windows_owner_acl
            if created:
                _apply_and_verify_windows_owner_acl(self.root)
            else:
                _verify_windows_owner_acl(self.root)
        else:
            if created:
                os.chmod(self.root, 0o700)
        if os.name != "nt" and (self.root.stat().st_uid != os.geteuid() or stat.S_IMODE(self.root.stat().st_mode) != 0o700):
            raise ProjectRepositoryError("project root must be owner-only mode 0700")
        root_info = self.root.stat()
        self._root_identity = (root_info.st_dev, root_info.st_ino)

    def save(self, state: ProjectState, *, expected_revision: int) -> ProjectState:
        if not isinstance(state, ProjectState):
            raise TypeError("state must be ProjectState")
        with self._project_lock(state.project_id):
            path = self._path(state.project_id)
            previous = self._read_bytes(path) if path.exists() else None
            current = self._decode(previous, migrate=True) if previous is not None else None
            if current is not None and current.project_id != state.project_id:
                raise ProjectRepositoryError("project payload ID does not match filename")
            actual = current.revision if current is not None else 0
            if actual != expected_revision:
                raise RevisionConflictError(f"expected revision {expected_revision}, found {actual}")
            published = replace(
                state,
                revision=max(state.revision, expected_revision + 1),
                migrated_from_v1=False,
            )
            encoded = _canonical_bytes(project_to_mapping(published, force_v2=True))
            self._publish(path, encoded, previous)
            return published

    def get(self, project_id: str) -> ProjectState:
        path = self._path(project_id)
        if not path.exists():
            raise ProjectNotFoundError(project_id)
        state = self._decode(self._read_bytes(path), migrate=True)
        if state.project_id != project_id:
            raise ProjectRepositoryError("project payload ID does not match filename")
        return state

    def list_project_ids(self) -> tuple[str, ...]:
        values = []
        for path in self.root.glob("*.json"):
            _require_safe_file(path)
            state = self._decode(self._read_bytes(path), migrate=True)
            if path.name != f"{state.project_id}.json":
                raise ProjectRepositoryError(f"project filename does not match payload: {path.name}")
            values.append(state.project_id)
        return tuple(sorted(values))

    def restore_backup(self, project_id: str, *, expected_revision: int) -> ProjectState:
        with self._project_lock(project_id):
            path = self._path(project_id)
            backup_path = path.with_suffix(".json.bak")
            if not path.exists():
                raise ProjectNotFoundError(project_id)
            if not backup_path.exists():
                raise ProjectNotFoundError(f"backup:{project_id}")
            current_bytes = self._read_bytes(path)
            current = self._decode(current_bytes, migrate=True)
            if current.project_id != project_id:
                raise ProjectRepositoryError("current project payload ID does not match filename")
            if current.revision != expected_revision:
                raise RevisionConflictError(f"expected revision {expected_revision}, found {current.revision}")
            backup = self._decode(self._read_bytes(backup_path), migrate=True)
            if backup.project_id != project_id:
                raise ProjectRepositoryError("backup project payload ID does not match filename")
            restored = replace(backup, revision=expected_revision + 1, migrated_from_v1=False)
            restored_bytes = _canonical_bytes(project_to_mapping(restored, force_v2=True))
            self._write_atomic(path.with_suffix(".json.rollback"), current_bytes)
            self._write_atomic(path, restored_bytes)
            return restored

    def _path(self, project_id: str) -> Path:
        if not isinstance(project_id, str) or not project_id or project_id.strip() != project_id or any(character.isspace() for character in project_id):
            raise ValueError("invalid project_id")
        if any(character in project_id for character in "/\\:\x00") or project_id in {".", ".."}:
            raise ValueError("project_id must not contain path syntax")
        return self.root / f"{project_id}.json"

    def _read_bytes(self, path: Path) -> bytes:
        self._assert_root_identity()
        _require_safe_file(path)
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"): flags |= os.O_NOFOLLOW
        if hasattr(os, "O_BINARY"): flags |= os.O_BINARY
        descriptor = os.open(path, flags)
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ProjectRepositoryError("project file must be a single-link regular file")
            current = path.stat()
            if (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino):
                raise ProjectRepositoryError("project file changed while opening")
            if info.st_size > self.MAX_PROJECT_BYTES:
                raise ProjectRepositoryError("project file exceeds size limit")
            with os.fdopen(descriptor, "rb") as stream:
                descriptor = -1
                return stream.read(self.MAX_PROJECT_BYTES + 1)
        finally:
            if descriptor >= 0: os.close(descriptor)

    def _decode(self, value: bytes, *, migrate: bool) -> ProjectState:
        try:
            payload = json.loads(value.decode("utf-8", errors="strict"))
            return project_from_mapping(payload, migrate=migrate)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise ProjectRepositoryError(f"invalid project payload: {exc}") from exc

    def _publish(self, path: Path, encoded: bytes, previous: bytes | None) -> None:
        temporary = self._prepare_temp(path, encoded)
        try:
            if previous is not None:
                self._write_atomic(path.with_suffix(".json.bak"), previous)
            os.replace(temporary, path)
            _fsync_directory(self.root)
        finally:
            temporary.unlink(missing_ok=True)

    def _write_atomic(self, destination: Path, value: bytes) -> None:
        if destination.exists():
            _require_safe_file(destination)
        temporary = self._prepare_temp(destination, value)
        try:
            os.replace(temporary, destination)
            _fsync_directory(self.root)
        finally:
            temporary.unlink(missing_ok=True)

    def _prepare_temp(self, destination: Path, value: bytes) -> Path:
        self._assert_root_identity()
        temporary = self.root / f".{destination.name}.{secrets.token_hex(8)}.tmp"
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        if hasattr(os, "O_BINARY"): flags |= os.O_BINARY
        descriptor = os.open(temporary, flags, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(value); stream.flush(); os.fsync(stream.fileno())
            self._decode(temporary.read_bytes(), migrate=True)
            return temporary
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    @contextmanager
    def _project_lock(self, project_id: str) -> Iterator[None]:
        self._assert_root_identity()
        lock = self._path(project_id).with_suffix(".lock")
        if _is_symlink_or_reparse(lock):
            raise ProjectRepositoryError("unsafe project lock")
        flags = os.O_RDWR
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        created = False
        try:
            descriptor = os.open(lock, flags | os.O_CREAT | os.O_EXCL, 0o600)
            created = True
        except FileExistsError:
            descriptor = os.open(lock, flags)
        stream = os.fdopen(descriptor, "r+b")
        try:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ProjectRepositoryError("project lock must be a single-link regular file")
            current = lock.stat()
            if (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino):
                raise ProjectRepositoryError("project lock changed while opening")
            if created:
                stream.write(b"\0"); stream.flush(); os.fsync(stream.fileno())
            elif info.st_size != 1:
                raise ProjectRepositoryError("existing project lock has invalid size")
            deadline = time.monotonic() + self.LOCK_TIMEOUT
            while True:
                from .execution import current_execution_context
                context = current_execution_context()
                if context is not None:
                    context.checkpoint()
                try:
                    stream.seek(0)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError as exc:
                    if time.monotonic() >= deadline:
                        raise ProjectRepositoryError("project lock is busy") from exc
                    time.sleep(0.05)
            yield
        finally:
            try:
                stream.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
            finally:
                stream.close()

    def _assert_root_identity(self) -> None:
        _require_safe_directory(self.root)
        info = self.root.stat()
        if (info.st_dev, info.st_ino) != self._root_identity:
            raise ProjectRepositoryError("project root identity changed")
        if os.name == "nt":
            from .cache import _verify_windows_owner_acl
            _verify_windows_owner_acl(self.root)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _is_symlink_or_reparse(path: Path) -> bool:
    try: info = path.lstat()
    except OSError: return False
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _reject_reparse_ancestors(path: Path) -> None:
    candidate = path
    while not candidate.exists() and candidate != candidate.parent: candidate = candidate.parent
    while candidate != candidate.parent:
        if _is_symlink_or_reparse(candidate): raise ProjectRepositoryError(f"project root traverses symlink/reparse: {candidate}")
        candidate = candidate.parent


def _require_safe_file(path: Path) -> None:
    if _is_symlink_or_reparse(path) or not path.is_file(): raise ProjectRepositoryError(f"unsafe project file: {path}")


def _require_safe_directory(path: Path) -> None:
    if _is_symlink_or_reparse(path) or not path.is_dir(): raise ProjectRepositoryError(f"unsafe project directory: {path}")


def _fsync_directory(path: Path) -> None:
    if os.name == "nt": return
    descriptor = os.open(path, os.O_RDONLY)
    try: os.fsync(descriptor)
    finally: os.close(descriptor)


__all__ = ["InMemoryProjectRepository", "JsonProjectRepository", "ProjectNotFoundError", "ProjectRepository", "ProjectRepositoryError", "RevisionConflictError"]
