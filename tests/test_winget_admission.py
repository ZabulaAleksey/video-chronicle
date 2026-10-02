from __future__ import annotations

import ctypes
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QProcess

from video_chronicle import process_control, tooling, tool_setup
from video_chronicle.tool_setup import ManagedToolSetupProcess


def test_winget_resolution_ignores_path_and_environment_localappdata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    alias = tmp_path / "Microsoft" / "WindowsApps" / "winget.exe"
    alias.parent.mkdir(parents=True)
    alias.write_bytes(b"fixture alias placeholder")
    monkeypatch.setattr(tooling.os, "name", "nt")
    monkeypatch.setattr(tooling, "_known_local_app_data", lambda: tmp_path)

    original_lstat = Path.lstat

    def fake_lstat(path: Path):
        if path == alias:
            return SimpleNamespace(
                st_file_attributes=0x400,
                st_reparse_tag=tooling._APP_EXEC_LINK_REPARSE_TAG,
            )
        return original_lstat(path)

    monkeypatch.setattr(
        Path, "lstat", fake_lstat
    )
    monkeypatch.setattr(
        tooling.shutil,
        "which",
        lambda *_args, **_kwargs: pytest.fail("PATH must not select WinGet"),
    )

    assert tooling.resolve_winget(
        {
            "PATH": str(tmp_path / "attacker"),
            "LOCALAPPDATA": str(tmp_path / "spoofed-profile"),
        }
    ) == str(alias)


@pytest.mark.parametrize(
    ("attributes", "tag"),
    [
        (0, None),
        (0x400, 0xA000000C),  # symbolic link
        (0x400, 0xA0000003),  # mount-point/junction
        (0x400, 0x8000001C),  # another reparse kind
    ],
)
def test_winget_resolution_rejects_non_alias_candidates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    attributes: int,
    tag: int | None,
) -> None:
    alias = tmp_path / "Microsoft" / "WindowsApps" / "winget.exe"
    alias.parent.mkdir(parents=True)
    alias.write_bytes(b"placeholder")
    monkeypatch.setattr(tooling.os, "name", "nt")
    monkeypatch.setattr(tooling, "_known_local_app_data", lambda: tmp_path)
    original_lstat = Path.lstat

    def fake_lstat(path: Path):
        if path == alias:
            return SimpleNamespace(st_file_attributes=attributes, st_reparse_tag=tag)
        return original_lstat(path)

    monkeypatch.setattr(Path, "lstat", fake_lstat)

    assert tooling.resolve_winget() is None


class _FakeWinApiFunction:
    def __init__(self, callback):
        self.callback = callback

    def __call__(self, *args):
        return self.callback(*args)


class _FakeKernel32:
    def __init__(self, *, family: str, package_root: str, image_path: str):
        self.full_name = "Microsoft.DesktopAppInstaller_1.27.460.0_x64__8wekyb3d8bbwe"
        self.family = family
        self.package_root = package_root
        self.image_path = image_path
        self.GetPackageFullName = _FakeWinApiFunction(
            lambda handle, length, buffer: self._write(
                self.full_name, length, buffer
            )
        )
        self.PackageFamilyNameFromFullName = _FakeWinApiFunction(
            lambda full_name, length, buffer: self._write(
                self.family, length, buffer
            )
        )
        self.GetPackagePathByFullName = _FakeWinApiFunction(
            lambda full_name, length, buffer: self._write(
                self.package_root, length, buffer
            )
        )
        self.QueryFullProcessImageNameW = _FakeWinApiFunction(self._write_image)

    @staticmethod
    def _write(value: str, length, buffer) -> int:
        if buffer is None:
            length._obj.value = len(value) + 1
            return 122
        ctypes.memmove(
            buffer,
            ctypes.create_unicode_buffer(value),
            (len(value) + 1) * ctypes.sizeof(ctypes.c_wchar),
        )
        length._obj.value = len(value) + 1
        return 0

    def _write_image(self, handle, flags, buffer, length) -> int:
        ctypes.memmove(
            buffer,
            ctypes.create_unicode_buffer(self.image_path),
            (len(self.image_path) + 1) * ctypes.sizeof(ctypes.c_wchar),
        )
        length._obj.value = len(self.image_path)
        return 1


def _install_fake_kernel32(monkeypatch: pytest.MonkeyPatch, api: _FakeKernel32) -> None:
    monkeypatch.setattr(tooling.os, "name", "nt")
    monkeypatch.setattr(
        tooling.ctypes, "WinDLL", lambda *_args, **_kwargs: api, raising=False
    )


def test_winget_process_admission_accepts_exact_package_family_and_image(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = r"C:\Program Files\WindowsApps\Microsoft.DesktopAppInstaller_1.27.460.0_x64__8wekyb3d8bbwe"
    api = _FakeKernel32(
        family=tooling._WINGET_PACKAGE_FAMILY,
        package_root=root,
        image_path=root + r"\winget.exe",
    )
    _install_fake_kernel32(monkeypatch, api)
    tooling.admit_winget_process(SimpleNamespace(_handle=123))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("family", "image_path"),
    [
        ("Other.Package_1234567890abc", r"C:\pkg\winget.exe"),
        (
            tooling._WINGET_PACKAGE_FAMILY,
            r"C:\Users\Public\winget.exe",
        ),
        (
            tooling._WINGET_PACKAGE_FAMILY,
            r"C:\Program Files\WindowsApps\Other.Package_1234567890abc\winget.exe",
        ),
        (
            tooling._WINGET_PACKAGE_FAMILY,
            r"C:\Program Files\WindowsApps\Microsoft.DesktopAppInstaller_1.27.460.0_x64__8wekyb3d8bbwe\other.exe",
        ),
    ],
)
def test_winget_process_admission_rejects_wrong_family_or_image(
    monkeypatch: pytest.MonkeyPatch, family: str, image_path: str
) -> None:
    root = r"C:\Program Files\WindowsApps\Microsoft.DesktopAppInstaller_1.27.460.0_x64__8wekyb3d8bbwe"
    api = _FakeKernel32(family=family, package_root=root, image_path=image_path)
    _install_fake_kernel32(monkeypatch, api)

    with pytest.raises(OSError):
        tooling.admit_winget_process(SimpleNamespace(_handle=123))  # type: ignore[arg-type]


@pytest.mark.parametrize("status,required_size", [(15700, 0), (122, 1025), (0, 0)])
def test_winget_process_admission_rejects_no_package_or_invalid_identity_size(
    status: int, required_size: int
) -> None:
    def invalid_package_api(length, buffer) -> int:
        length._obj.value = required_size
        return status

    with pytest.raises(OSError):
        tooling._read_package_string(invalid_package_api)


def test_managed_process_admits_only_after_job_assignment_before_resume(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    class FakeProcess:
        pid = 321
        _handle = 123

        def __init__(self, *args, **kwargs) -> None:
            events.append("spawn-suspended")

        def kill(self) -> None:
            events.append("kill")

        def wait(self, timeout=None) -> int:
            events.append("reap")
            return 0

    class FakeJob:
        def assign(self, process) -> None:
            events.append("job-assign")

        def resume_primary(self, process) -> None:
            events.append("resume")

        def close(self, *, require_success=False) -> None:
            events.append("job-close")

    monkeypatch.setattr(process_control.os, "name", "nt")
    monkeypatch.setattr(
        process_control.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False
    )
    monkeypatch.setattr(process_control, "_WindowsJob", FakeJob)
    monkeypatch.setattr(process_control.subprocess, "Popen", FakeProcess)

    process_control.ManagedProcess(
        ["winget.exe"], admission_callback=lambda _process: events.append("admit")
    )

    assert events == ["spawn-suspended", "job-assign", "admit", "resume"]


def test_managed_process_reaps_suspended_process_when_admission_rejects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    class FakeProcess:
        pid = 321

        def __init__(self, *args, **kwargs) -> None:
            events.append("spawn-suspended")

        def kill(self) -> None:
            events.append("kill")

        def wait(self, timeout=None) -> int:
            events.append("reap")
            return 0

    class FakeJob:
        def assign(self, process) -> None:
            events.append("job-assign")

        def resume_primary(self, process) -> None:
            events.append("resume")

        def close(self, *, require_success=False) -> None:
            events.append("job-close")

    def reject(_process) -> None:
        events.append("reject")
        raise OSError("identity mismatch")

    monkeypatch.setattr(process_control.os, "name", "nt")
    monkeypatch.setattr(
        process_control.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False
    )
    monkeypatch.setattr(process_control, "_WindowsJob", FakeJob)
    monkeypatch.setattr(process_control.subprocess, "Popen", FakeProcess)

    with pytest.raises(OSError, match="identity mismatch"):
        process_control.ManagedProcess(["winget.exe"], admission_callback=reject)

    assert events == [
        "spawn-suspended",
        "job-assign",
        "reject",
        "kill",
        "job-close",
        "reap",
    ]


def test_discovered_winget_alias_swap_is_rejected_before_resume(
    qapp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    alias = tmp_path / "Microsoft" / "WindowsApps" / "winget.exe"
    alias.parent.mkdir(parents=True)
    alias.write_bytes(b"test alias placeholder")
    monkeypatch.setattr(tooling.os, "name", "nt")
    monkeypatch.setattr(tooling, "_known_local_app_data", lambda: tmp_path)
    original_lstat = Path.lstat

    def fake_lstat(path: Path):
        if path == alias:
            return SimpleNamespace(
                st_file_attributes=0x400,
                st_reparse_tag=tooling._APP_EXEC_LINK_REPARSE_TAG,
            )
        return original_lstat(path)

    monkeypatch.setattr(Path, "lstat", fake_lstat)
    discovered = tooling.resolve_winget({"LOCALAPPDATA": str(tmp_path / "spoofed")})
    assert discovered == str(alias)

    root = r"C:\Program Files\WindowsApps\Microsoft.DesktopAppInstaller_1.27.460.0_x64__8wekyb3d8bbwe"
    api = _FakeKernel32(
        family=tooling._WINGET_PACKAGE_FAMILY,
        package_root=root,
        image_path=r"C:\Users\Public\winget.exe",
    )
    _install_fake_kernel32(monkeypatch, api)
    real_admission = tooling.admit_winget_process

    class FakeProcess:
        pid = 321
        _handle = 123

        def __init__(self, *args, **kwargs) -> None:
            events.append("spawn-suspended")

        def kill(self) -> None:
            events.append("kill")

        def wait(self, timeout=None) -> int:
            events.append("reap")
            return 1

    class FakeJob:
        def assign(self, process) -> None:
            events.append("job-assign")

        def resume_primary(self, process) -> None:
            events.append("resume")

        def close(self, *, require_success=False) -> None:
            events.append("job-close")

    def traced_admission(process) -> None:
        events.append("admit")
        try:
            real_admission(process)
        except BaseException as error:
            events.append(f"admission-error:{type(error).__name__}:{error}")
            raise

    def run_managed(command, **kwargs):
        process_control.ManagedProcess(
            command, admission_callback=kwargs["admission_callback"]
        )
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(process_control.os, "name", "nt")
    monkeypatch.setattr(
        process_control.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False
    )
    monkeypatch.setattr(process_control, "_WindowsJob", FakeJob)
    monkeypatch.setattr(process_control.subprocess, "Popen", FakeProcess)
    monkeypatch.setattr(tooling, "admit_winget_process", traced_admission)
    monkeypatch.setattr(tool_setup, "run_managed_command", run_managed)

    setup = ManagedToolSetupProcess(timeout=2)
    setup.setProgram(discovered)
    setup.setArguments(tooling.winget_ffmpeg_install_arguments())
    completions = []
    setup.finished.connect(lambda value, status: completions.append((value, status)))
    setup.start()
    deadline = time.monotonic() + 3
    while not completions and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)

    assert completions == [(1, QProcess.ExitStatus.CrashExit)]
    assert events[0:3] == ["spawn-suspended", "job-assign", "admit"]
    assert setup.last_error == "OSError"
    assert events == [
        "spawn-suspended",
        "job-assign",
        "admit",
        "admission-error:OSError:WinGet process image is outside its registered package root",
        "kill",
        "job-close",
        "reap",
    ]
    setup.deleteLater()
