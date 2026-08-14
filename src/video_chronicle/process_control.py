"""Platform-owned subprocess trees with bounded cooperative termination.

Only trusted, already-resolved media tools cross this boundary.  Commands are
always list argv and never pass through a shell.
"""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from typing import Protocol


COOPERATIVE_GRACE_SECONDS = 2.0
FORCE_KILL_SECONDS = 3.0
POLL_SECONDS = 0.05


class CancellationSignal(Protocol):
    @property
    def cancel_requested(self) -> bool: ...


class ProcessControlError(RuntimeError):
    """Base error for a managed subprocess boundary."""


class ProcessSafetyError(ProcessControlError):
    """Whole-tree ownership or confirmed termination was not available."""


class ProcessTreeUnavailable(ProcessSafetyError):
    """The platform could not establish ownership of the complete tree."""


class ProcessTreeTerminationError(ProcessSafetyError):
    """The owned process tree did not stop inside the bounded kill budget."""


class ProcessCancelled(ProcessControlError):
    """A cancellation request stopped the complete owned process tree."""


class ProcessTimedOut(ProcessControlError):
    pass


class ProcessOutputLimitExceeded(ProcessControlError):
    pass


def safe_cancel_supported() -> bool:
    """Return whether this platform has a supported whole-tree primitive."""

    return os.name == "nt" or os.name == "posix"


class _WindowsJob:
    """Minimal ctypes wrapper for an unnamed KILL_ON_JOB_CLOSE Job Object."""

    def __init__(self) -> None:
        if os.name != "nt":
            raise ProcessTreeUnavailable("Windows Job Objects are unavailable")
        import ctypes
        from ctypes import wintypes

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_ulonglong),
                ("WriteOperationCount", ctypes.c_ulonglong),
                ("OtherOperationCount", ctypes.c_ulonglong),
                ("ReadTransferCount", ctypes.c_ulonglong),
                ("WriteTransferCount", ctypes.c_ulonglong),
                ("OtherTransferCount", ctypes.c_ulonglong),
            ]

        class BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_longlong),
                ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", BASIC_LIMIT_INFORMATION),
                ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        class BASIC_ACCOUNTING_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("TotalUserTime", ctypes.c_longlong),
                ("TotalKernelTime", ctypes.c_longlong),
                ("ThisPeriodTotalUserTime", ctypes.c_longlong),
                ("ThisPeriodTotalKernelTime", ctypes.c_longlong),
                ("TotalPageFaultCount", wintypes.DWORD),
                ("TotalProcesses", wintypes.DWORD),
                ("ActiveProcesses", wintypes.DWORD),
                ("TotalTerminatedProcesses", wintypes.DWORD),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.SetInformationJobObject.argtypes = (
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        )
        kernel32.SetInformationJobObject.restype = wintypes.BOOL
        kernel32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
        kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel32.TerminateJobObject.argtypes = (wintypes.HANDLE, wintypes.UINT)
        kernel32.TerminateJobObject.restype = wintypes.BOOL
        kernel32.QueryInformationJobObject.argtypes = (
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.c_void_p,
        )
        kernel32.QueryInformationJobObject.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL

        handle = kernel32.CreateJobObjectW(None, None)
        if not handle:
            raise ProcessTreeUnavailable(
                f"CreateJobObjectW failed ({ctypes.get_last_error()})"
            )
        info = EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = 0x00002000
        if not kernel32.SetInformationJobObject(
            handle, 9, ctypes.byref(info), ctypes.sizeof(info)
        ):
            error = ctypes.get_last_error()
            kernel32.CloseHandle(handle)
            raise ProcessTreeUnavailable(
                f"SetInformationJobObject failed ({error})"
            )
        self._ctypes = ctypes
        self._kernel32 = kernel32
        self._handle = handle
        self._accounting_type = BASIC_ACCOUNTING_INFORMATION

    def assign(self, process: subprocess.Popen[bytes]) -> None:
        process_handle = self._ctypes.c_void_p(int(process._handle))  # type: ignore[attr-defined]
        if not self._kernel32.AssignProcessToJobObject(self._handle, process_handle):
            raise ProcessTreeUnavailable(
                "AssignProcessToJobObject failed "
                f"({self._ctypes.get_last_error()})"
            )

    def terminate(self) -> None:
        if self._handle and not self._kernel32.TerminateJobObject(self._handle, 1):
            raise ProcessTreeTerminationError(
                f"TerminateJobObject failed ({self._ctypes.get_last_error()})"
            )

    def active_processes(self) -> int:
        info = self._accounting_type()
        if not self._kernel32.QueryInformationJobObject(
            self._handle,
            1,
            self._ctypes.byref(info),
            self._ctypes.sizeof(info),
            None,
        ):
            raise ProcessTreeTerminationError(
                "QueryInformationJobObject failed "
                f"({self._ctypes.get_last_error()})"
            )
        return int(info.ActiveProcesses)

    def wait_empty(self, deadline: float) -> bool:
        while time.monotonic() < deadline:
            if self.active_processes() == 0:
                return True
            time.sleep(POLL_SECONDS)
        return self.active_processes() == 0

    def close(self, *, require_success: bool = False) -> None:
        if self._handle:
            success = self._kernel32.CloseHandle(self._handle)
            if success:
                self._handle = None
            elif require_success:
                raise ProcessTreeTerminationError(
                    f"CloseHandle(job) failed ({self._ctypes.get_last_error()})"
                )


class ManagedProcess:
    """A root process whose descendants are owned by a platform tree."""

    def __init__(self, command: list[str]) -> None:
        if not command or not all(isinstance(part, str) for part in command):
            raise TypeError("command must be a non-empty list of strings")
        if not safe_cancel_supported():
            raise ProcessTreeUnavailable(
                "safe process-tree cancellation is unsupported on this platform"
            )
        self._job: _WindowsJob | None = _WindowsJob() if os.name == "nt" else None
        creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            self.process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=creation_flags,
                start_new_session=os.name == "posix",
                shell=False,
            )
        except Exception:
            if self._job is not None:
                self._job.close()
            raise
        if self._job is not None:
            try:
                self._job.assign(self.process)
            except Exception:
                # Assignment is the ownership commit point.  Before it succeeds,
                # cancellation cannot be advertised.  Stop/reap the trusted root
                # immediately; do not continue with parent-only cancellation.
                self.process.kill()
                self.process.wait()
                self._job.close()
                raise

    def _wait_until(self, deadline: float) -> bool:
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                return True
            time.sleep(POLL_SECONDS)
        return self.process.poll() is not None

    def _posix_group_alive(self) -> bool:
        if os.name != "posix":
            return False
        try:
            os.killpg(self.process.pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def _wait_group_until(self, deadline: float) -> bool:
        while time.monotonic() < deadline:
            # Reap our direct child while checking the wider process group;
            # otherwise the root zombie itself can keep the group observable.
            self.process.poll()
            if not self._posix_group_alive():
                return True
            time.sleep(POLL_SECONDS)
        self.process.poll()
        return not self._posix_group_alive()

    def terminate_tree(self) -> None:
        """Try FFmpeg's stdin ``q``, then force-stop and reap the whole tree."""

        root_already_exited = self.process.poll() is not None
        if root_already_exited:
            self.process.wait()
            if os.name == "posix" and not self._posix_group_alive():
                return
        else:
            try:
                if self.process.stdin is not None:
                    self.process.stdin.write(b"q\n")
                    self.process.stdin.flush()
                    self.process.stdin.close()
            except (BrokenPipeError, OSError):
                pass
        root_exited = root_already_exited or self._wait_until(
            time.monotonic() + COOPERATIVE_GRACE_SECONDS
        )

        if os.name == "nt":
            assert self._job is not None
            if self._job.active_processes() != 0:
                self._job.terminate()
            if not self._job.wait_empty(time.monotonic() + FORCE_KILL_SECONDS):
                raise ProcessTreeTerminationError(
                    "Windows Job Object still has active processes after termination"
                )
            if not root_exited and not self._wait_until(
                time.monotonic() + FORCE_KILL_SECONDS
            ):
                raise ProcessTreeTerminationError(
                    "root process was not reaped after Job Object termination"
                )
            self.process.wait(timeout=FORCE_KILL_SECONDS)
            return
        else:
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            if not self._wait_group_until(time.monotonic() + 0.25):
                try:
                    os.killpg(self.process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        tree_stopped = (
            self._wait_until(time.monotonic() + FORCE_KILL_SECONDS)
            if os.name == "nt"
            else self._wait_group_until(time.monotonic() + FORCE_KILL_SECONDS)
        )
        if not tree_stopped:
            raise ProcessTreeTerminationError(
                "owned process tree did not stop inside the kill/reap budget"
            )
        self.process.wait(timeout=FORCE_KILL_SECONDS)

    def close(self) -> None:
        if self._job is not None:
            self._job.close()

    def close_confirmed(self) -> None:
        if self._job is not None:
            self._job.close(require_success=True)


def run_managed_command(
    command: list[str],
    *,
    cancellation: CancellationSignal | None,
    timeout: float | None,
    max_output_bytes: int,
) -> subprocess.CompletedProcess[str]:
    """Run one command with bounded capture and whole-tree termination."""

    if max_output_bytes < 0:
        raise ValueError("max_output_bytes must be non-negative")
    if cancellation is not None and cancellation.cancel_requested:
        raise ProcessCancelled("operation cancelled before tool start")

    threads: list[threading.Thread] = []
    started_threads: list[threading.Thread] = []
    tree_confirmed = False
    managed = ManagedProcess(command)
    try:
        process = managed.process
        buffers = {"stdout": bytearray(), "stderr": bytearray()}
        lock = threading.Lock()
        limit_exceeded = threading.Event()

        def drain(name: str, stream) -> None:
            while True:
                chunk = stream.read(64 * 1024)
                if not chunk:
                    return
                with lock:
                    used = len(buffers["stdout"]) + len(buffers["stderr"])
                    remaining = max(0, max_output_bytes - used)
                    buffers[name].extend(chunk[:remaining])
                    if len(chunk) > remaining:
                        limit_exceeded.set()
                        return

        threads = [
            threading.Thread(
                target=drain, args=("stdout", process.stdout), daemon=True
            ),
            threading.Thread(
                target=drain, args=("stderr", process.stderr), daemon=True
            ),
        ]
        for thread in threads:
            try:
                thread.start()
            finally:
                if thread.ident is not None:
                    started_threads.append(thread)

        started = time.monotonic()
        terminal_error: ProcessControlError | None = None
        while process.poll() is None:
            if cancellation is not None and cancellation.cancel_requested:
                terminal_error = ProcessCancelled("operation cancelled")
                break
            if limit_exceeded.is_set():
                terminal_error = ProcessOutputLimitExceeded(
                    f"tool output exceeded {max_output_bytes} bytes"
                )
                break
            if timeout is not None and time.monotonic() - started >= timeout:
                terminal_error = ProcessTimedOut(f"timed out after {timeout:g} seconds")
                break
            time.sleep(POLL_SECONDS)
        if terminal_error is not None:
            managed.terminate_tree()
        else:
            process.wait()
            managed.terminate_tree()
        # KILL_ON_JOB_CLOSE also contains an unexpected helper that outlived a
        # normally-exited root and may still hold inherited output pipes.
        managed.close_confirmed()
        tree_confirmed = True
        for thread in started_threads:
            thread.join(timeout=FORCE_KILL_SECONDS)
        if any(thread.is_alive() for thread in started_threads):
            raise ProcessTreeTerminationError("tool output pipes did not close after reap")
        if terminal_error is not None:
            raise terminal_error
        if limit_exceeded.is_set():
            raise ProcessOutputLimitExceeded(
                f"tool output exceeded {max_output_bytes} bytes"
            )
        stdout = bytes(buffers["stdout"]).decode("utf-8", errors="replace")
        stderr = bytes(buffers["stderr"]).decode("utf-8", errors="replace")
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
    except BaseException as original:
        if tree_confirmed:
            raise
        try:
            managed.terminate_tree()
            managed.close_confirmed()
            for thread in started_threads:
                thread.join(timeout=FORCE_KILL_SECONDS)
            if any(thread.is_alive() for thread in started_threads):
                raise ProcessTreeTerminationError(
                    "tool output pipes did not close after exceptional reap"
                )
        except BaseException as safety_failure:
            note = (
                "SAFETY FAILURE while terminating the owned process tree: "
                f"{type(safety_failure).__name__}: {safety_failure}"
            )
            if hasattr(original, "add_note"):
                original.add_note(note)
            raise original from safety_failure
        raise
    finally:
        managed.close()
