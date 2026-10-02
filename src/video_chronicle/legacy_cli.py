"""Qt worker for the bounded legacy CLI diagnostic path."""

from __future__ import annotations
import math
import os
import subprocess
from pathlib import Path
from PySide6.QtCore import QObject, QThread, Signal, Slot
from video_chronicle.execution import OperationCancellation
from video_chronicle.process_control import ProcessCancelled, run_managed_command


class _LegacyThread(QThread):
    def __init__(self, task, cancellation, parent):
        super().__init__(parent)
        self.task = task
        self.cancellation = cancellation
        self.result: subprocess.CompletedProcess[str] | None = None
        self.error: BaseException | None = None

    def run(self):
        try:
            self.result = self.task()
        except BaseException as error:
            self.error = error
        finally:
            # Decide terminal-vs-cancel under the token lock in the worker,
            # before Qt queues finished. GUI delivery cannot reopen the race.
            if not self.cancellation.complete() and self.error is None:
                self.result = None
                self.error = ProcessCancelled("operation cancelled at completion")


class ManagedLegacyCli(QObject):
    output_received = Signal(str)
    finished = Signal(object, object)

    def __init__(self, parent=None, *, timeout=1800.0, max_output_bytes=1024 * 1024):
        super().__init__(parent)
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("legacy deadline must be finite and positive")
        if type(max_output_bytes) is not int or max_output_bytes <= 0:
            raise ValueError("legacy output budget must be a positive integer")
        self.timeout = timeout
        self.max_output_bytes = max_output_bytes
        self._thread = None
        self._cancellation = None

    def start(self, command: list[str], cwd: Path):
        if self._thread is not None:
            raise RuntimeError("legacy CLI already running")
        command_snapshot = tuple(command)
        environment = dict(os.environ)
        environment.update(PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        cancellation = OperationCancellation()
        thread = _LegacyThread(
            lambda: run_managed_command(
                list(command_snapshot),
                cwd=cwd,
                env=environment,
                cancellation=cancellation,
                timeout=self.timeout,
                max_output_bytes=self.max_output_bytes,
                output_received=self.output_received.emit,
                cooperative_stdin=False,
            ),
            cancellation,
            self,
        )
        self._thread = thread
        self._cancellation = cancellation
        thread.finished.connect(self._finish)
        try:
            thread.start()
        except BaseException:
            self._thread = None
            self._cancellation = None
            thread.deleteLater()
            raise

    def request_cancel(self):
        return self._cancellation.request_cancel() if self._cancellation else False

    @Slot()
    def _finish(self):
        thread = self._thread
        if thread is None:
            return
        result, error = thread.result, thread.error
        self._thread = None
        self._cancellation = None
        thread.deleteLater()
        self.finished.emit(result, error)
