"""Qt adapter over the bounded, owned process-tree boundary for tool setup."""

from __future__ import annotations

import math
import subprocess
from collections.abc import Callable

from PySide6.QtCore import QObject, QProcess, QThread, Signal, Slot

from video_chronicle.execution import OperationCancellation
from video_chronicle.process_control import run_managed_command

SETUP_TIMEOUT_SECONDS = 1800.0
SETUP_MAX_OUTPUT_BYTES = 1024 * 1024


class _SetupThread(QThread):
    def __init__(
        self, task: Callable[[], subprocess.CompletedProcess[str]], parent: QObject
    ):
        super().__init__(parent)
        self.task = task
        self.result: subprocess.CompletedProcess[str] | None = None
        self.error: BaseException | None = None

    def run(self) -> None:
        try:
            self.result = self.task()
        except BaseException as error:  # noqa: BLE001 - Qt worker must always deliver terminal state
            # Even a worker failure must restore the UI after the owned runner's
            # exception cleanup. No output or environment is sent to the GUI.
            self.error = error


class ManagedToolSetupProcess(QObject):
    """Single-use QProcess-shaped port; all production launches are managed."""

    finished = Signal(int, QProcess.ExitStatus)
    errorOccurred = Signal(QProcess.ProcessError)

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        timeout: float = SETUP_TIMEOUT_SECONDS,
        max_output_bytes: int = SETUP_MAX_OUTPUT_BYTES,
    ) -> None:
        super().__init__(parent)
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("setup deadline must be finite and positive")
        if type(max_output_bytes) is not int or max_output_bytes <= 0:
            raise ValueError("setup output budget must be a positive integer")
        self._timeout = timeout
        self._max_output_bytes = max_output_bytes
        self._program = ""
        self._arguments: list[str] = []
        self._thread: _SetupThread | None = None
        self._started = False
        self._state = QProcess.ProcessState.NotRunning
        self._cancellation = OperationCancellation()
        self.last_error: str | None = None

    def setProcessChannelMode(self, mode: QProcess.ProcessChannelMode) -> None:
        # The managed runner drains both channels under one aggregate cap.
        if mode != QProcess.ProcessChannelMode.MergedChannels:
            raise ValueError("only bounded combined capture is supported")

    def setProgram(self, program: str) -> None:
        if self._started:
            raise RuntimeError("setup already started")
        self._program = program

    def program(self) -> str:
        return self._program

    def setArguments(self, arguments: list[str]) -> None:
        if self._started:
            raise RuntimeError("setup already started")
        self._arguments = list(arguments)

    def arguments(self) -> list[str]:
        return list(self._arguments)

    def state(self) -> QProcess.ProcessState:
        return self._state

    def request_cancel(self) -> bool:
        return self._cancellation.request_cancel()

    def start(self) -> None:
        if self._started or not self._program:
            raise RuntimeError("setup requires a program and a single start")
        self._started = True
        command = [self._program, *self._arguments]
        thread = _SetupThread(
            lambda: run_managed_command(
                command,
                cancellation=self._cancellation,
                timeout=self._timeout,
                max_output_bytes=self._max_output_bytes,
            ),
            self,
        )
        self._thread = thread
        self._state = QProcess.ProcessState.Running
        thread.finished.connect(self._finish)
        try:
            thread.start()
        except Exception:
            self._thread = None
            self._state = QProcess.ProcessState.NotRunning
            thread.deleteLater()
            raise

    @Slot()
    def _finish(self) -> None:
        thread = self._thread
        if thread is None:
            return
        # Qt queues finished after run() returns. The managed runner has
        # already confirmed process-tree/Job cleanup; use Qt's canonical
        # finished -> deleteLater lifecycle without blocking the GUI on wait.
        self._thread = None
        self._state = QProcess.ProcessState.NotRunning
        self._cancellation.complete()
        result, error = thread.result, thread.error
        thread.deleteLater()
        if error is not None or result is None:
            self.last_error = (
                type(error).__name__ if error is not None else "MissingResult"
            )
            self.finished.emit(1, QProcess.ExitStatus.CrashExit)
        else:
            self.finished.emit(result.returncode, QProcess.ExitStatus.NormalExit)
