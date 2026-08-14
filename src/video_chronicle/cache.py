"""Private content-addressed cache for normalized media clips.

The cache is deliberately an optimization boundary: callers may treat every
exception as a miss and continue with a clean normalization.
"""

from __future__ import annotations

import hashlib
import errno
import ctypes
import json
import os
import secrets
import shutil
import stat
import sys
import time
import threading
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from fractions import Fraction
from typing import Any, Iterator

from .domain import ExportRequest, MediaItem, SourceFingerprint
from .ports import CommandRunner


CACHE_SCHEMA = "video-chronicle-normalized-clip-cache"
CACHE_VERSION = 1
CACHE_MARKER = ".video-chronicle-cache"
CACHE_LOCK = ".video-chronicle-cache.lock"
NORMALIZATION_PROFILE = "normalize-v1"
NORMALIZATION_PROFILE_V2 = "normalize-v2"
ARTIFACT_NAME = "clip.mp4"
MANIFEST_NAME = "manifest.json"
MAX_CACHE_BYTES = 10 * 1024**3
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_MARKER_BYTES = 4096
MAX_UNUSED_AGE = timedelta(days=30)
MUTATION_LOCK_TIMEOUT = 5.0
_MANIFEST_FIELDS = {
    "schema",
    "version",
    "key",
    "identity",
    "created_at",
    "artifact_size",
    "artifact_sha256",
}


class CacheEntryRejected(RuntimeError):
    """An existing cache entry failed the strict trust contract."""


def default_cache_root() -> Path:
    """Return the platform user-cache location without creating it."""

    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
        return base / "VideoChronicle" / "cache"
    if sys_cache := os.environ.get("XDG_CACHE_HOME"):
        return Path(sys_cache).expanduser() / "video-chronicle"
    return Path.home() / ".cache" / "video-chronicle"


class NormalizedClipCache:
    """Filesystem adapter implementing immutable normalized-clip entries."""

    def __init__(self, root: Path | None = None) -> None:
        raw_root = root or default_cache_root()
        _reject_unsafe_raw_cache_path(raw_root)
        self.root = Path(os.path.abspath(raw_root.expanduser()))
        self._lock = threading.RLock()
        self._active = 0
        self._tool_identities: dict[tuple[str, int, int], dict[str, Any]] = {}
        self.hits = 0
        self.misses = 0

    @contextmanager
    def operation(self) -> Iterator[None]:
        with self._lock:
            if self._active == 0:
                self._tool_identities.clear()
            self._active += 1
        try:
            yield
        finally:
            with self._lock:
                self._active -= 1

    def restore(
        self,
        item: MediaItem,
        request: ExportRequest,
        destination: Path,
        runner: CommandRunner,
    ) -> bool:
        self._validate_root_scope(request)
        if not self.root.exists():
            self.misses += 1
            return False
        if self.root.is_dir() and not any(self.root.iterdir()):
            self._ensure_root(request)
        self._require_root()
        identity = self._build_identity(item, request, runner)
        key = cache_key(identity)
        entry = self.root / key
        if not entry.exists():
            self.misses += 1
            return False
        try:
            manifest = self._read_manifest(entry, key)
            if manifest["identity"] != identity:
                raise ValueError("cache identity mismatch")
            artifact = entry / ARTIFACT_NAME
            _require_regular_private_path(artifact)
            artifact_stat = artifact.stat()
            if artifact_stat.st_size > MAX_CACHE_BYTES:
                raise CacheEntryRejected("cache artifact exceeds the size cap")
            if artifact_stat.st_size != manifest["artifact_size"]:
                raise ValueError("cache artifact size mismatch")
            if _sha256_stable(artifact, max_bytes=MAX_CACHE_BYTES)[0] != manifest["artifact_sha256"]:
                raise ValueError("cache artifact hash mismatch")
            _validate_normalized_stream(artifact, request.ffprobe, runner)
            destination.parent.mkdir(parents=True, exist_ok=True)
            _copy_with_checkpoints(artifact, destination)
            if _sha256_stable(destination, max_bytes=MAX_CACHE_BYTES)[0] != manifest["artifact_sha256"]:
                destination.unlink(missing_ok=True)
                raise ValueError("restored artifact hash mismatch")
            os.utime(entry, None)
        except Exception as exc:
            destination.unlink(missing_ok=True)
            self.misses += 1
            from .execution import ExportCancelled
            from .process_control import ProcessSafetyError

            if isinstance(exc, (ExportCancelled, ProcessSafetyError)):
                raise
            if isinstance(exc, CacheEntryRejected):
                raise
            raise CacheEntryRejected(f"cache entry rejected: {exc}") from exc
        self.hits += 1
        return True

    def store(
        self,
        item: MediaItem,
        request: ExportRequest,
        artifact: Path,
        runner: CommandRunner,
    ) -> bool:
        # Serialize writers in one process so stale-tmp recovery never races a
        # currently populated temp entry. Cross-process publication remains
        # protected by the no-replace commit boundary.
        with self._lock:
            return self._store(item, request, artifact, runner)

    def _store(
        self,
        item: MediaItem,
        request: ExportRequest,
        artifact: Path,
        runner: CommandRunner,
    ) -> bool:
        self._validate_root_scope(request)
        identity = self._build_identity(item, request, runner)
        key = cache_key(identity)
        artifact_stat = artifact.stat()
        if artifact_stat.st_size > MAX_CACHE_BYTES:
            return False
        artifact_hash, artifact_stat = _sha256_stable(artifact, max_bytes=MAX_CACHE_BYTES)
        _validate_normalized_stream(artifact, request.ffprobe, runner)
        self._ensure_root(request)
        with self._mutation_lock():
            return self._store_locked(
                identity, key, artifact, artifact_hash, artifact_stat
            )

    def _store_locked(
        self,
        identity: dict[str, Any],
        key: str,
        artifact: Path,
        artifact_hash: str,
        artifact_stat: os.stat_result,
    ) -> bool:
        self._purge_staging()
        current_bytes = self._actual_cache_bytes()
        if current_bytes + artifact_stat.st_size > MAX_CACHE_BYTES:
            return False
        final = self.root / key
        if final.exists():
            if self._entry_matches(final, key):
                return True
            raise CacheEntryRejected(f"existing cache entry is incompatible: {key}")
        temporary = self.root / f"tmp-{secrets.token_hex(12)}"
        temporary.mkdir(mode=0o700)
        try:
            copied = temporary / ARTIFACT_NAME
            _copy_with_checkpoints(artifact, copied)
            copied_hash, copied_stat = _sha256_stable(copied, max_bytes=MAX_CACHE_BYTES)
            if (copied_hash, copied_stat.st_size) != (artifact_hash, artifact_stat.st_size):
                raise OSError("cache copy verification failed")
            _fsync_file(copied)
            os.chmod(copied, 0o400)
            now = datetime.now(UTC).isoformat()
            version = 2 if key.startswith("clip-v2-") else 1
            manifest = {
                "schema": CACHE_SCHEMA,
                "version": version,
                "key": key,
                "identity": identity,
                "created_at": now,
                "artifact_size": copied_stat.st_size,
                "artifact_sha256": copied_hash,
            }
            manifest_path = temporary / MANIFEST_NAME
            manifest_path.write_text(_canonical_json(manifest), encoding="utf-8")
            _fsync_file(manifest_path)
            os.chmod(manifest_path, 0o400)
            self._read_manifest(temporary, key, enforce_directory_name=False)
            _fsync_directory(temporary)
            try:
                _commit_directory_no_replace(temporary, final)
            except FileExistsError:
                if self._entry_matches(final, key):
                    return True
                raise CacheEntryRejected(f"concurrent cache entry is incompatible: {key}")
            _fsync_directory(self.root)
            return True
        finally:
            if temporary.exists():
                _remove_verified_tree(temporary, allow_tmp=True)

    def prune(self) -> int:
        """Remove expired/LRU verified entries; call only after successful export."""

        with self._lock:
            if not self.root.exists():
                return 0
            self._require_root()
            with self._mutation_lock():
                return self._prune_locked()

    def _prune_locked(self) -> int:
        self._purge_staging()
        now = datetime.now(UTC)
        entries: list[tuple[datetime, int, Path]] = []
        for entry in self._entry_directories():
            try:
                manifest = self._read_manifest(entry, entry.name)
                artifact = entry / ARTIFACT_NAME
                artifact_stat = artifact.stat()
                if artifact_stat.st_size > MAX_CACHE_BYTES:
                    continue
                if artifact_stat.st_size != manifest["artifact_size"]:
                    continue
                verified = datetime.fromtimestamp(entry.stat().st_mtime, UTC)
                entries.append((verified, artifact_stat.st_size, entry))
            except Exception:
                continue
        removed = 0
        total = self._actual_cache_bytes()
        for verified, size, entry in sorted(entries, key=lambda value: value[0]):
            if now - verified <= MAX_UNUSED_AGE and total <= MAX_CACHE_BYTES:
                continue
            self._trash_entry(entry)
            total -= size
            removed += 1
        return removed

    def purge(
        self,
        *,
        protected_input: Path | None = None,
        protected_output: Path | None = None,
    ) -> int:
        with self._lock:
            if self._active:
                raise RuntimeError("cache purge is unavailable during an active operation")
            self._validate_purge_scope(protected_input, protected_output)
            if not self.root.exists():
                return 0
            self._require_root()
            with self._mutation_lock():
                entries = list(self._entry_directories())
                for entry in entries:
                    self._trash_entry(entry)
                self._purge_staging()
                return len(entries)

    def _ensure_root(self, request: ExportRequest) -> None:
        self._validate_root_scope(request)
        root = self.root
        if root.exists():
            _require_directory(root)
            names = {candidate.name for candidate in root.iterdir()}
            if CACHE_MARKER in names:
                self._require_root()
                return
            if names - {CACHE_LOCK}:
                self._require_root()
            os.chmod(root, 0o700)
        else:
            root.mkdir(parents=True, mode=0o700)
        os.chmod(root, 0o700)
        if os.name == "nt":
            _apply_and_verify_windows_owner_acl(root)
        with self._mutation_lock():
            marker = root / CACHE_MARKER
            if marker.exists():
                self._require_root()
                return
            unexpected = {
                candidate.name for candidate in root.iterdir()
            } - {CACHE_LOCK}
            if unexpected:
                raise RuntimeError(f"cache marker is missing: {root}")
            marker.write_text(
                _canonical_json({"schema": CACHE_SCHEMA, "version": CACHE_VERSION}),
                encoding="utf-8",
            )
            _fsync_file(marker)
            os.chmod(marker, 0o400)
            (root / "trash").mkdir(mode=0o700, exist_ok=True)
            _fsync_directory(root)

    @contextmanager
    def _mutation_lock(self) -> Iterator[None]:
        lock_path = self.root / CACHE_LOCK
        if _is_symlink_or_reparse(lock_path):
            raise RuntimeError(f"unsafe cache mutation lock: {lock_path}")
        flags = os.O_CREAT | os.O_RDWR
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        descriptor = os.open(lock_path, flags, 0o600)
        stream = os.fdopen(descriptor, "r+b")
        try:
            os.chmod(lock_path, 0o600)
            if lock_path.stat().st_size == 0:
                stream.write(b"\0")
                stream.flush()
                os.fsync(stream.fileno())
            deadline = time.monotonic() + MUTATION_LOCK_TIMEOUT
            while True:
                _execution_checkpoint()
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
                        raise RuntimeError("cache mutation lock is busy") from exc
                    time.sleep(0.05)
            try:
                yield
            finally:
                stream.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        finally:
            stream.close()

    def _validate_root_scope(self, request: ExportRequest) -> None:
        root = self.root
        _reject_reparse_ancestors(root)
        home = Path.home().resolve(strict=False)
        input_dir = request.input_dir.resolve(strict=False)
        output = request.output.resolve(strict=False)
        if (
            root == Path(root.anchor)
            or root in {home, input_dir, output, output.parent}
            or root.is_relative_to(input_dir)
        ):
            raise RuntimeError(f"unsafe cache root: {root}")
        self._require_private_platform_root(allow_empty=True)

    def _validate_purge_scope(
        self, protected_input: Path | None, protected_output: Path | None
    ) -> None:
        root = self.root.resolve(strict=False)
        home = Path.home().resolve(strict=False)
        if root == Path(root.anchor) or root == home:
            raise RuntimeError(f"unsafe cache purge root: {root}")
        if protected_input is not None:
            boundary = protected_input.expanduser().resolve(strict=False)
            if root == boundary or root.is_relative_to(boundary):
                raise RuntimeError(f"cache purge root is inside protected path: {boundary}")
        if protected_output is not None:
            output = protected_output.expanduser().resolve(strict=False)
            if root in {output, output.parent}:
                raise RuntimeError(f"cache purge root conflicts with output path: {output}")
        self._require_private_platform_root(allow_empty=True)

    def _require_private_platform_root(self, *, allow_empty: bool = False) -> None:
        raw = str(self.root)
        if raw.startswith(("\\\\", "//", "\\\\?\\", "\\??\\")):
            raise RuntimeError("cache root must not be a UNC or device path")
        if os.name == "nt":
            drive_type = ctypes.windll.kernel32.GetDriveTypeW(str(Path(self.root.anchor)))
            if drive_type != 3:  # DRIVE_FIXED; inherit the current profile ACL.
                raise RuntimeError("cache root must be on a fixed local drive")
            allowed = [Path.home().resolve(strict=False)]
            if local := os.environ.get("LOCALAPPDATA"):
                allowed.append(Path(local).resolve(strict=False))
            resolved = self.root.resolve(strict=False)
            if not any(resolved == base or resolved.is_relative_to(base) for base in allowed):
                raise RuntimeError("Windows cache root must be under the current user profile")
            if self.root.exists() and not allow_empty:
                _verify_windows_owner_acl(self.root)
        elif self.root.exists():
            info = self.root.stat()
            empty = allow_empty and self.root.is_dir() and not any(self.root.iterdir())
            if info.st_uid != os.geteuid() or (
                stat.S_IMODE(info.st_mode) & 0o077 and not empty
            ):
                raise RuntimeError("cache root must be owned by the current user with mode 0700")

    def _build_identity(
        self, item: MediaItem, request: ExportRequest, runner: CommandRunner
    ) -> dict[str, Any]:
        identities: dict[str, dict[str, Any]] = {}
        for label, executable in (
            ("ffmpeg", request.ffmpeg),
            ("ffprobe", request.ffprobe),
        ):
            info = Path(executable).stat()
            memo_key = (str(Path(executable).resolve()), info.st_size, info.st_mtime_ns)
            identity = self._tool_identities.get(memo_key)
            if identity is None:
                identity = _tool_identity(executable, runner)
                self._tool_identities[memo_key] = identity
            identities[label] = identity
        return build_clip_identity(
            item, request, runner, tool_identities=identities
        )

    def _require_root(self) -> None:
        _require_directory(self.root)
        marker = self.root / CACHE_MARKER
        if not marker.exists():
            raise RuntimeError(f"cache marker is missing: {self.root}")
        _require_regular_private_path(marker)
        value = _read_bounded_json(marker, MAX_MARKER_BYTES)
        if value != {"schema": CACHE_SCHEMA, "version": CACHE_VERSION}:
            raise RuntimeError(f"cache marker does not match: {self.root}")
        if os.name == "nt":
            # Migrate an exact older app root to a protected owner-only DACL.
            _apply_and_verify_windows_owner_acl(self.root)
        self._require_private_platform_root()

    def _read_manifest(
        self, entry: Path, key: str, *, enforce_directory_name: bool = True
    ) -> dict[str, Any]:
        _require_directory(entry)
        if (enforce_directory_name and entry.name != key) or not key.startswith(("clip-v1-", "clip-v2-")):
            raise ValueError("cache key/directory mismatch")
        manifest_path = entry / MANIFEST_NAME
        _require_regular_private_path(manifest_path)
        manifest = _read_bounded_json(manifest_path, MAX_MANIFEST_BYTES)
        if type(manifest) is not dict or set(manifest) != _MANIFEST_FIELDS:
            raise ValueError("cache manifest fields do not match")
        expected_version = 2 if key.startswith("clip-v2-") else 1
        if manifest["schema"] != CACHE_SCHEMA or manifest["version"] != expected_version:
            raise ValueError("cache manifest version is incompatible")
        if manifest["key"] != key or cache_key(manifest["identity"]) != key:
            raise ValueError("cache manifest key does not match")
        if (
            type(manifest["artifact_size"]) is not int
            or manifest["artifact_size"] < 0
            or manifest["artifact_size"] > MAX_CACHE_BYTES
        ):
            raise ValueError("invalid cache artifact size")
        if not _is_sha256(manifest["artifact_sha256"]):
            raise ValueError("invalid cache artifact hash")
        _parse_utc(manifest["created_at"])
        if set(path.name for path in entry.iterdir()) != {MANIFEST_NAME, ARTIFACT_NAME}:
            raise ValueError("cache entry contains unexpected files")
        return manifest

    def _actual_cache_bytes(self) -> int:
        total = 0
        for candidate in self.root.iterdir():
            if candidate.name.startswith(("clip-v1-", "clip-v2-", "tmp-")):
                total += _safe_tree_bytes(candidate)
            elif candidate.name == "trash":
                _require_directory(candidate)
                for child in candidate.iterdir():
                    total += _safe_tree_bytes(child)
        return total

    def _entry_matches(self, entry: Path, key: str) -> bool:
        try:
            manifest = self._read_manifest(entry, key)
            existing_hash, existing_stat = _sha256_stable(
                entry / ARTIFACT_NAME, max_bytes=MAX_CACHE_BYTES
            )
            return (
                existing_hash == manifest["artifact_sha256"]
                and existing_stat.st_size == manifest["artifact_size"]
            )
        except Exception:
            return False

    def _entry_directories(self) -> Iterator[Path]:
        for candidate in self.root.iterdir():
            if candidate.name.startswith(("clip-v1-", "clip-v2-")):
                _require_directory(candidate)
                yield candidate

    def _trash_entry(self, entry: Path) -> None:
        self._read_manifest(entry, entry.name)
        trash = self.root / "trash"
        if not trash.exists():
            trash.mkdir(mode=0o700)
        _require_directory(trash)
        target = trash / f"{entry.name}-{secrets.token_hex(8)}"
        entry.rename(target)
        _remove_verified_tree(target)

    def _purge_staging(self) -> None:
        trash = self.root / "trash"
        if trash.exists():
            _require_directory(trash)
            for candidate in trash.iterdir():
                if not candidate.name.startswith(("clip-v1-", "clip-v2-")):
                    raise RuntimeError(f"unrecognized cache trash entry: {candidate}")
                manifest_path = candidate / MANIFEST_NAME
                _require_regular_private_path(manifest_path)
                raw = _read_bounded_json(manifest_path, MAX_MANIFEST_BYTES)
                key = raw.get("key") if isinstance(raw, dict) else None
                if not isinstance(key, str):
                    raise RuntimeError(f"unverified cache trash entry: {candidate}")
                self._read_manifest(candidate, key, enforce_directory_name=False)
                _remove_verified_tree(candidate)
        for candidate in self.root.glob("tmp-*"):
            if _is_symlink_or_reparse(candidate) or not candidate.is_dir():
                raise RuntimeError(f"unsafe cache temporary entry: {candidate}")
            names = {child.name for child in candidate.iterdir()}
            if not names.issubset({MANIFEST_NAME, ARTIFACT_NAME}):
                raise RuntimeError(f"unverified cache temporary entry: {candidate}")
            _remove_verified_tree(candidate, allow_tmp=True)


def build_clip_identity(
    item: MediaItem,
    request: ExportRequest,
    runner: CommandRunner,
    *,
    tool_identities: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    source_hash, source_stat = _sha256_stable(item.path)
    expected = item.source_fingerprint
    if expected is not None and SourceFingerprint.capture(item.path) != expected:
        raise ValueError("source fingerprint changed before cache reuse")
    overlay = request.overlay
    font: dict[str, Any] | None = None
    if overlay.font_file is not None:
        font_hash, font_stat = _sha256_stable(overlay.font_file)
        font = {
            "path_sha256": _path_hash(overlay.font_file),
            "sha256": font_hash,
            "size": font_stat.st_size,
            "mtime_ns": font_stat.st_mtime_ns,
        }
    decision = item.date_decision
    date_identity: dict[str, Any] = {
        "taken_at": item.taken_at.isoformat(timespec="microseconds"),
        "date_source": item.date_source,
        "policy_version": decision.policy_version if decision else None,
        "selected": _date_candidate_identity(decision.selected) if decision else None,
        "all_valid": (
            [_date_candidate_identity(candidate) for candidate in decision.all_valid]
            if decision
            else []
        ),
        "conflicts": (
            [_date_candidate_identity(candidate) for candidate in decision.conflicts]
            if decision
            else []
        ),
    }
    fingerprint = expected or SourceFingerprint(
        source_stat.st_dev,
        source_stat.st_ino,
        source_stat.st_size,
        source_stat.st_mtime_ns,
        source_stat.st_ctime_ns,
        source_hash,
    )
    identity = {
        "source_path_sha256": _path_hash(item.path),
        "source_fingerprint": {
            "device": fingerprint.device,
            "inode": fingerprint.inode,
            "size": fingerprint.size,
            "mtime_ns": fingerprint.mtime_ns,
            "ctime_ns": fingerprint.ctime_ns,
        },
        "source_sha256": source_hash,
        "recorded_date": date_identity,
        "media_shape": {"is_photo": item.is_photo, "has_audio": item.has_audio},
        "mode": request.mode.value,
        "overlay": {
            "enabled": overlay.enabled,
            "format": overlay.format,
            "position": overlay.position,
            "horizontal_margin": overlay.horizontal_margin,
            "vertical_margin": overlay.vertical_margin,
            "font_size": overlay.font_size,
            "text_color": overlay.text_color,
            "outline_color": overlay.outline_color,
            "outline_width": overlay.outline_width,
            "font_identity": list(overlay.font_identity) if overlay.font_identity else None,
            "font": font,
        },
        "encoding": {"crf": request.crf, "preset": request.preset},
        "normalization": NORMALIZATION_PROFILE_V2 if item.trim_applied else NORMALIZATION_PROFILE,
        "tools": tool_identities
        or {
            "ffmpeg": _tool_identity(request.ffmpeg, runner),
            "ffprobe": _tool_identity(request.ffprobe, runner),
        },
    }
    if item.trim_applied:
        if item.trim_out_us is None:
            raise ValueError("edited trim requires a resolved out point")
        identity["trim"] = {"in_us": item.trim_in_us, "out_us": item.trim_out_us}
    return identity


def cache_key(identity: dict[str, Any]) -> str:
    digest = hashlib.sha256(_canonical_json(identity).encode("utf-8")).hexdigest()
    version = 2 if identity.get("normalization") == NORMALIZATION_PROFILE_V2 else 1
    return f"clip-v{version}-{digest}"


def _date_candidate_identity(candidate: Any) -> dict[str, Any]:
    return {
        "wall_time": candidate.wall_time.isoformat(timespec="microseconds"),
        "raw_value": candidate.raw_value,
        "origin": candidate.origin,
        "key": candidate.key,
        "raw_key": candidate.raw_key,
        "location": candidate.location,
        "timezone": candidate.timezone,
        "priority": candidate.priority,
    }


def _tool_identity(executable: str, runner: CommandRunner) -> dict[str, Any]:
    path = Path(executable)
    info = path.stat()
    result = runner(
        [executable, "-version"],
        f"tool identity failed for {path.name}",
        timeout=15,
        max_output_bytes=1024 * 1024,
    )
    output = (result.stdout + "\n" + result.stderr).encode("utf-8")
    return {
        "version_sha256": hashlib.sha256(output).hexdigest(),
        "executable_size": info.st_size,
        "executable_mtime_ns": info.st_mtime_ns,
    }


def _validate_normalized_stream(
    artifact: Path, ffprobe: str, runner: CommandRunner
) -> None:
    result = runner(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=format_name:stream=codec_type,codec_name,width,height,r_frame_rate,pix_fmt,profile,level,time_base,sample_rate,channels",
            "-of",
            "json",
            str(artifact),
        ],
        f"cache FFprobe failed for {artifact.name}",
        timeout=30,
        max_output_bytes=1024 * 1024,
    )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("cache FFprobe returned invalid JSON") from exc
    streams = payload.get("streams")
    if not isinstance(streams, list):
        raise ValueError("cache FFprobe stream list is missing")
    video = [stream for stream in streams if stream.get("codec_type") == "video"]
    audio = [stream for stream in streams if stream.get("codec_type") == "audio"]
    format_value = payload.get("format")
    format_name = format_value.get("format_name") if isinstance(format_value, dict) else None
    if not isinstance(format_name, str) or "mp4" not in format_name.split(","):
        raise ValueError("cached clip container is incompatible")
    if len(video) != 1 or video[0].get("codec_name") != "h264":
        raise ValueError("cached clip video stream is incompatible")
    if video[0].get("width") != 1600 or video[0].get("height") != 900:
        raise ValueError("cached clip dimensions are incompatible")
    try:
        frame_rate = Fraction(str(video[0].get("r_frame_rate")))
    except (ValueError, ZeroDivisionError):
        frame_rate = Fraction(0)
    if frame_rate != 60:
        raise ValueError("cached clip frame rate is incompatible")
    if video[0].get("pix_fmt") != "yuv420p":
        raise ValueError("cached clip pixel format is incompatible")
    # libx264's ultrafast preset can emit a Constrained Baseline SPS even
    # with ``-profile:v high`` because it disables all High-only coding tools.
    # The cache key binds preset and tool identity, so both observed outputs
    # are compatible with the existing normalize-v1 argv contract.
    if str(video[0].get("profile", "")).casefold() not in {
        "high",
        "constrained baseline",
    }:
        raise ValueError("cached clip profile is incompatible")
    level = str(video[0].get("level", "")).replace(".", "")
    if level != "42":
        raise ValueError("cached clip level is incompatible")
    if video[0].get("time_base") != "1/60000":
        raise ValueError("cached clip time base is incompatible")
    if len(audio) != 1 or audio[0].get("codec_name") != "aac":
        raise ValueError("cached clip audio stream is incompatible")
    if str(audio[0].get("sample_rate")) != "48000" or audio[0].get("channels") != 2:
        raise ValueError("cached clip audio format is incompatible")


def _sha256_stable(
    path: Path, *, max_bytes: int | None = None
) -> tuple[str, os.stat_result]:
    _require_regular_private_path(path)
    before = path.stat()
    if max_bytes is not None and before.st_size > max_bytes:
        raise ValueError(f"file exceeds the cache size cap: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            _execution_checkpoint()
            digest.update(chunk)
    after = path.stat()
    fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
    if any(getattr(before, field) != getattr(after, field) for field in fields):
        raise ValueError(f"file changed while hashing: {path}")
    return digest.hexdigest(), after


def _path_hash(path: Path) -> str:
    value = os.path.normcase(str(path.expanduser().resolve(strict=True)))
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _reject_unsafe_raw_cache_path(value: Path) -> None:
    """Reject network/device syntax before any filesystem-resolving operation."""

    raw = str(value)
    normalized = raw.replace("/", "\\")
    if normalized.startswith(("\\\\", "\\??\\", "\\.\\")):
        raise RuntimeError("cache root must not be a UNC or device path")


def _read_bounded_json(path: Path, maximum: int) -> Any:
    info = path.stat()
    if info.st_size > maximum:
        raise CacheEntryRejected(f"cache metadata exceeds {maximum} bytes: {path.name}")
    with path.open("rb") as stream:
        payload = stream.read(maximum + 1)
    if len(payload) > maximum:
        raise CacheEntryRejected(f"cache metadata exceeds {maximum} bytes: {path.name}")
    try:
        return json.loads(payload.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CacheEntryRejected(f"invalid cache JSON: {path.name}") from exc


def _execution_checkpoint() -> None:
    from .execution import current_execution_context

    context = current_execution_context()
    if context is not None:
        context.checkpoint()


def _copy_with_checkpoints(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with source.open("rb") as source_stream, destination.open("xb") as target_stream:
            while chunk := source_stream.read(1024 * 1024):
                _execution_checkpoint()
                target_stream.write(chunk)
            target_stream.flush()
            os.fsync(target_stream.fileno())
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def _commit_directory_no_replace(temporary: Path, final: Path) -> None:
    """Commit a prepared entry without ever replacing an existing directory."""

    if os.name == "nt":
        os.rename(temporary, final)  # Windows rename is create-if-absent.
        return
    source_bytes = os.fsencode(temporary)
    final_bytes = os.fsencode(final)
    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform.startswith("linux") and hasattr(libc, "renameat2"):
        result = libc.renameat2(-100, source_bytes, -100, final_bytes, 1)
        if result == 0:
            return
        error = ctypes.get_errno()
        if error == errno.EEXIST:
            raise FileExistsError(error, os.strerror(error), final)
        if error not in {errno.ENOSYS, errno.EINVAL, errno.ENOTSUP}:
            raise OSError(error, os.strerror(error), final)
    elif sys.platform == "darwin" and hasattr(libc, "renamex_np"):
        result = libc.renamex_np(source_bytes, final_bytes, 0x00000004)
        if result == 0:
            return
        error = ctypes.get_errno()
        if error == errno.EEXIST:
            raise FileExistsError(error, os.strerror(error), final)
        if error not in {errno.ENOSYS, errno.EINVAL, errno.ENOTSUP}:
            raise OSError(error, os.strerror(error), final)

    # Portable reservation fallback. The manifest is moved last, so readers
    # never accept a partially populated reservation as a valid entry.
    final.mkdir(mode=0o700)
    try:
        os.rename(temporary / ARTIFACT_NAME, final / ARTIFACT_NAME)
        _fsync_file(final / ARTIFACT_NAME)
        _fsync_directory(final)
        os.rename(temporary / MANIFEST_NAME, final / MANIFEST_NAME)
        _fsync_directory(final)
        temporary.rmdir()
    except Exception:
        _remove_verified_tree(final)
        raise


def _is_symlink_or_reparse(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return False
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def _require_regular_private_path(path: Path) -> None:
    if _is_symlink_or_reparse(path):
        raise ValueError(f"unsafe symlink/reparse path: {path}")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(f"expected a regular file: {path}")


def _require_directory(path: Path) -> None:
    if _is_symlink_or_reparse(path):
        raise ValueError(f"unsafe symlink/reparse directory: {path}")
    if not path.is_dir():
        raise ValueError(f"expected a directory: {path}")


def _safe_tree_bytes(path: Path) -> int:
    _require_directory(path)
    total = 0
    for parent, directories, files in os.walk(path, followlinks=False):
        for name in directories:
            _require_directory(Path(parent) / name)
        for name in files:
            candidate = Path(parent) / name
            _require_regular_private_path(candidate)
            total += candidate.stat().st_size
    return total


class _SidAndAttributes(ctypes.Structure):
    _fields_ = [("sid", ctypes.c_void_p), ("attributes", ctypes.c_ulong)]


class _TokenUser(ctypes.Structure):
    _fields_ = [("user", _SidAndAttributes)]


class _AclSizeInformation(ctypes.Structure):
    _fields_ = [
        ("ace_count", ctypes.c_ulong),
        ("acl_bytes_in_use", ctypes.c_ulong),
        ("acl_bytes_free", ctypes.c_ulong),
    ]


class _AceHeader(ctypes.Structure):
    _fields_ = [
        ("ace_type", ctypes.c_ubyte),
        ("ace_flags", ctypes.c_ubyte),
        ("ace_size", ctypes.c_ushort),
    ]


def _current_windows_user_sid() -> ctypes.Array[Any]:
    kernel32 = ctypes.windll.kernel32
    advapi32 = ctypes.windll.advapi32
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    advapi32.OpenProcessToken.argtypes = [
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    advapi32.OpenProcessToken.restype = ctypes.c_int
    advapi32.GetTokenInformation.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_ulong),
    ]
    advapi32.GetLengthSid.argtypes = [ctypes.c_void_p]
    advapi32.GetLengthSid.restype = ctypes.c_ulong
    advapi32.CopySid.argtypes = [ctypes.c_ulong, ctypes.c_void_p, ctypes.c_void_p]
    token = ctypes.c_void_p()
    if not advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), 0x0008, ctypes.byref(token)):
        raise ctypes.WinError()
    try:
        required = ctypes.c_ulong()
        advapi32.GetTokenInformation(token, 1, None, 0, ctypes.byref(required))
        token_buffer = ctypes.create_string_buffer(required.value)
        if not advapi32.GetTokenInformation(
            token, 1, token_buffer, required.value, ctypes.byref(required)
        ):
            raise ctypes.WinError()
        sid = ctypes.cast(token_buffer, ctypes.POINTER(_TokenUser)).contents.user.sid
        sid_length = advapi32.GetLengthSid(sid)
        sid_copy = ctypes.create_string_buffer(sid_length)
        if not advapi32.CopySid(sid_length, sid_copy, sid):
            raise ctypes.WinError()
        return sid_copy
    finally:
        kernel32.CloseHandle(token)


def _apply_and_verify_windows_owner_acl(path: Path) -> None:
    if os.name != "nt":
        return
    advapi32 = ctypes.windll.advapi32
    advapi32.InitializeAcl.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong]
    advapi32.AddAccessAllowedAceEx.argtypes = [
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_void_p,
    ]
    advapi32.SetNamedSecurityInfoW.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_int,
        ctypes.c_ulong,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    sid = _current_windows_user_sid()
    sid_length = advapi32.GetLengthSid(sid)
    acl_size = 8 + 8 + sid_length
    acl = ctypes.create_string_buffer(acl_size)
    if not advapi32.InitializeAcl(acl, acl_size, 2):
        raise ctypes.WinError()
    # OBJECT_INHERIT_ACE | CONTAINER_INHERIT_ACE; protect children too.
    if not advapi32.AddAccessAllowedAceEx(acl, 2, 0x03, 0x001F01FF, sid):
        raise ctypes.WinError()
    result = advapi32.SetNamedSecurityInfoW(
        str(path), 1, 0x00000004 | 0x80000000, None, None, acl, None
    )
    if result:
        raise ctypes.WinError(result)
    _verify_windows_owner_acl(path)


def _verify_windows_owner_acl(path: Path) -> None:
    if os.name != "nt":
        return
    advapi32 = ctypes.windll.advapi32
    kernel32 = ctypes.windll.kernel32
    advapi32.GetNamedSecurityInfoW.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_int,
        ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    advapi32.EqualSid.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    advapi32.GetAclInformation.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_int,
    ]
    advapi32.GetAce.argtypes = [
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    advapi32.GetSecurityDescriptorControl.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_ushort),
        ctypes.POINTER(ctypes.c_ulong),
    ]
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    owner = ctypes.c_void_p()
    dacl = ctypes.c_void_p()
    security_descriptor = ctypes.c_void_p()
    result = advapi32.GetNamedSecurityInfoW(
        str(path),
        1,
        0x00000001 | 0x00000004,
        ctypes.byref(owner),
        None,
        ctypes.byref(dacl),
        None,
        ctypes.byref(security_descriptor),
    )
    if result:
        raise ctypes.WinError(result)
    try:
        sid = _current_windows_user_sid()
        control = ctypes.c_ushort()
        revision = ctypes.c_ulong()
        if not advapi32.GetSecurityDescriptorControl(
            security_descriptor, ctypes.byref(control), ctypes.byref(revision)
        ):
            raise ctypes.WinError()
        info = _AclSizeInformation()
        if dacl and not advapi32.GetAclInformation(
            dacl, ctypes.byref(info), ctypes.sizeof(info), 2
        ):
            raise ctypes.WinError()
        ace = ctypes.c_void_p()
        if dacl and info.ace_count == 1 and not advapi32.GetAce(
            dacl, 0, ctypes.byref(ace)
        ):
            raise ctypes.WinError()
        header = (
            ctypes.cast(ace, ctypes.POINTER(_AceHeader)).contents if ace else None
        )
        mask = (
            ctypes.cast(ace.value + 4, ctypes.POINTER(ctypes.c_ulong)).contents.value
            if ace
            else 0
        )
        ace_sid = ctypes.c_void_p(ace.value + 8) if ace else None
        _validate_windows_acl_contract(
            control=control.value,
            dacl_present=bool(dacl),
            ace_count=info.ace_count,
            owner_matches=bool(owner and advapi32.EqualSid(owner, sid)),
            ace_type=header.ace_type if header else -1,
            ace_flags=header.ace_flags if header else 0,
            access_mask=mask,
            ace_sid_matches=bool(
                ace_sid is not None and advapi32.EqualSid(ace_sid, sid)
            ),
        )
    finally:
        if security_descriptor:
            kernel32.LocalFree(security_descriptor)


def _validate_windows_acl_contract(
    *,
    control: int,
    dacl_present: bool,
    ace_count: int,
    owner_matches: bool,
    ace_type: int,
    ace_flags: int,
    access_mask: int,
    ace_sid_matches: bool,
) -> None:
    if not owner_matches:
        raise RuntimeError("Windows cache root owner is not the current user")
    if not dacl_present:
        raise RuntimeError("Windows cache root has no private DACL")
    if control & 0x1000 == 0:  # SE_DACL_PROTECTED
        raise RuntimeError("Windows cache root DACL is not protected")
    if (
        ace_count != 1
        or ace_type != 0
        or ace_flags & 0x03 != 0x03
        or access_mask != 0x001F01FF
        or not ace_sid_matches
    ):
        raise RuntimeError("Windows cache root DACL is not owner-only full access")


def _reject_reparse_ancestors(path: Path) -> None:
    candidate = path
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    while candidate != candidate.parent:
        if _is_symlink_or_reparse(candidate):
            raise RuntimeError(f"cache path traverses a symlink/reparse point: {candidate}")
        candidate = candidate.parent


def _remove_verified_tree(path: Path, *, allow_tmp: bool = False) -> None:
    if _is_symlink_or_reparse(path) or not path.is_dir():
        raise RuntimeError(f"refusing to remove unsafe cache directory: {path}")
    if not allow_tmp and not path.name.startswith(("clip-v1-", "clip-v2-")):
        raise RuntimeError(f"refusing to remove unrecognized cache entry: {path}")
    for parent, directories, files in os.walk(path, followlinks=False):
        for name in [*directories, *files]:
            candidate = Path(parent) / name
            if _is_symlink_or_reparse(candidate):
                raise RuntimeError(f"cache entry contains unsafe path: {candidate}")
            try:
                os.chmod(candidate, 0o600 if candidate.is_file() else 0o700)
            except OSError:
                pass
    shutil.rmtree(path)


def _parse_utc(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("cache timestamp must be a string")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError("cache timestamp must be UTC")
    return parsed


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


def _fsync_file(path: Path) -> None:
    with path.open("r+b") as stream:
        os.fsync(stream.fileno())


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
