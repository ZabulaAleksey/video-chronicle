from __future__ import annotations

import json
import os
import shutil
import sys
import threading
import time
from pathlib import Path

import pytest

from video_chronicle.process_control import (
    ProcessCancelled,
    ProcessOutputLimitExceeded,
    ProcessTimedOut,
    run_managed_command,
    safe_cancel_supported,
)


class _Cancellation:
    def __init__(self) -> None:
        self.requested = threading.Event()

    @property
    def cancel_requested(self) -> bool:
        return self.requested.is_set()


def _pid_alive(pid: int) -> bool:
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        exit_code = wintypes.DWORD()
        success = kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
        kernel32.CloseHandle(handle)
        return bool(success and exit_code.value == 259)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


@pytest.mark.skipif(not safe_cancel_supported(), reason="no supported tree primitive")
def test_cancel_reaps_root_child_and_grandchild_inside_bound(tmp_path: Path) -> None:
    pid_file = tmp_path / "tree pids.json"
    grandchild_code = "import time; time.sleep(60)"
    child_code = (
        "import json,subprocess,sys,time;"
        "g=subprocess.Popen([sys.executable,'-c',sys.argv[2]],"
        "stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);"
        "open(sys.argv[1],'w',encoding='utf-8').write(json.dumps([g.pid]));"
        "time.sleep(60)"
    )
    root_code = (
        "import json,subprocess,sys,time;"
        "c=subprocess.Popen([sys.executable,'-c',sys.argv[2],sys.argv[1],sys.argv[3]],"
        "stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);"
        "p=sys.argv[1];"
        "exec(\"while True:\\n"
        " try:\\n"
        "  ids=json.load(open(p,encoding='utf-8'));break\\n"
        " except Exception: time.sleep(.02)\");"
        "open(p,'w',encoding='utf-8').write(json.dumps([c.pid,*ids]));"
        "time.sleep(60)"
    )
    command = [
        sys.executable,
        "-c",
        root_code,
        str(pid_file),
        child_code,
        grandchild_code,
    ]
    cancellation = _Cancellation()
    errors: list[BaseException] = []

    def target() -> None:
        try:
            run_managed_command(
                command,
                cancellation=cancellation,
                timeout=30,
                max_output_bytes=1024 * 1024,
            )
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=target)
    thread.start()
    deadline = time.monotonic() + 5
    pids: list[int] = []
    while time.monotonic() < deadline:
        try:
            candidate = json.loads(pid_file.read_text(encoding="utf-8"))
            if isinstance(candidate, list) and len(candidate) == 2:
                pids = candidate
                break
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        time.sleep(0.02)
    if len(pids) != 2:
        cancellation.requested.set()
        thread.join(5.5)
        pytest.fail("helper process tree did not publish two PIDs")
    child_pid, grandchild_pid = pids

    started = time.monotonic()
    cancellation.requested.set()
    thread.join(5.5)
    elapsed = time.monotonic() - started

    assert not thread.is_alive()
    assert elapsed <= 5.5
    assert len(errors) == 1 and isinstance(errors[0], ProcessCancelled)
    deadline = time.monotonic() + 1
    while any(_pid_alive(pid) for pid in (child_pid, grandchild_pid)) and time.monotonic() < deadline:
        time.sleep(0.02)
    assert not _pid_alive(child_pid)
    assert not _pid_alive(grandchild_pid)


class _SyntheticInterrupt(BaseException):
    pass


def test_unexpected_base_exception_still_reaps_uninherited_process_tree(
    tmp_path: Path,
) -> None:
    pid_file = tmp_path / "exception-tree.json"
    grandchild_code = "import time; time.sleep(60)"
    child_code = (
        "import json,subprocess,sys,time;"
        "g=subprocess.Popen([sys.executable,'-c',sys.argv[2]],"
        "stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);"
        "open(sys.argv[1],'w',encoding='utf-8').write(json.dumps([g.pid]));"
        "time.sleep(60)"
    )
    root_code = (
        "import json,subprocess,sys,time;"
        "c=subprocess.Popen([sys.executable,'-c',sys.argv[2],sys.argv[1],sys.argv[3]],"
        "stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);"
        "p=sys.argv[1];"
        "exec(\"while True:\\n"
        " try:\\n"
        "  ids=json.load(open(p,encoding='utf-8'));break\\n"
        " except Exception: time.sleep(.02)\");"
        "open(p,'w',encoding='utf-8').write(json.dumps([c.pid,*ids]));"
        "time.sleep(60)"
    )

    class InterruptAfterTree:
        @property
        def cancel_requested(self) -> bool:
            try:
                values = json.loads(pid_file.read_text(encoding="utf-8"))
            except (FileNotFoundError, json.JSONDecodeError):
                return False
            if isinstance(values, list) and len(values) == 2:
                raise _SyntheticInterrupt("synthetic interrupt")
            return False

    with pytest.raises(_SyntheticInterrupt, match="synthetic interrupt"):
        run_managed_command(
            [
                sys.executable,
                "-c",
                root_code,
                str(pid_file),
                child_code,
                grandchild_code,
            ],
            cancellation=InterruptAfterTree(),
            timeout=30,
            max_output_bytes=1024 * 1024,
        )

    child_pid, grandchild_pid = json.loads(pid_file.read_text(encoding="utf-8"))
    deadline = time.monotonic() + 1
    while any(_pid_alive(pid) for pid in (child_pid, grandchild_pid)) and time.monotonic() < deadline:
        time.sleep(0.02)
    assert not _pid_alive(child_pid)
    assert not _pid_alive(grandchild_pid)


@pytest.mark.parametrize("failure", ["timeout", "output-limit"])
def test_timeout_and_output_limit_use_bounded_tree_termination(
    failure: str, monkeypatch
) -> None:
    import video_chronicle.process_control as control

    monkeypatch.setattr(control, "COOPERATIVE_GRACE_SECONDS", 0.01)
    monkeypatch.setattr(control, "FORCE_KILL_SECONDS", 1.0)
    if failure == "timeout":
        command = [sys.executable, "-c", "import time; time.sleep(60)"]
        expected = ProcessTimedOut
        timeout = 0.05
        limit = 1024
    else:
        command = [
            sys.executable,
            "-c",
            "import sys,time; sys.stdout.write('x'*65536); sys.stdout.flush(); time.sleep(60)",
        ]
        expected = ProcessOutputLimitExceeded
        timeout = 10
        limit = 1024

    started = time.monotonic()
    with pytest.raises(expected):
        run_managed_command(
            command,
            cancellation=None,
            timeout=timeout,
            max_output_bytes=limit,
        )
    assert time.monotonic() - started < 2


@pytest.mark.skipif(not safe_cancel_supported(), reason="no supported tree primitive")
def test_real_ffmpeg_cancel_is_bounded_when_binary_is_available() -> None:
    project_root = Path(__file__).resolve().parents[1]
    bundled = project_root / "ffmpeg1" / "bin" / (
        "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    )
    ffmpeg = os.environ.get("VIDEO_CHRONICLE_FFMPEG")
    executable = (
        str(Path(ffmpeg).resolve())
        if ffmpeg and Path(ffmpeg).is_file()
        else str(bundled.resolve())
        if bundled.is_file()
        else shutil.which("ffmpeg")
    )
    if executable is None:
        pytest.skip("real FFmpeg is unavailable")

    cancellation = _Cancellation()
    errors: list[BaseException] = []

    def target() -> None:
        try:
            run_managed_command(
                [
                    executable,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "testsrc2=size=640x360:rate=60",
                    "-t",
                    "60",
                    "-f",
                    "null",
                    "-",
                ],
                cancellation=cancellation,
                timeout=30,
                max_output_bytes=1024 * 1024,
            )
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=target)
    thread.start()
    time.sleep(0.15)
    started = time.monotonic()
    cancellation.requested.set()
    thread.join(5.5)

    assert not thread.is_alive()
    assert time.monotonic() - started <= 5.5
    assert len(errors) == 1 and isinstance(errors[0], ProcessCancelled)


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object contract")
def test_windows_job_close_failure_is_explicit_and_retryable() -> None:
    import ctypes
    from video_chronicle.process_control import (
        ProcessTreeTerminationError,
        _WindowsJob,
    )

    class FailingKernel:
        @staticmethod
        def CloseHandle(handle):
            return 0

    job = object.__new__(_WindowsJob)
    job._handle = 123  # type: ignore[attr-defined]
    job._kernel32 = FailingKernel()  # type: ignore[attr-defined]
    job._ctypes = ctypes  # type: ignore[attr-defined]

    with pytest.raises(ProcessTreeTerminationError, match="CloseHandle"):
        job.close(require_success=True)
    assert job._handle == 123  # type: ignore[attr-defined]
