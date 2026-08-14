"""Qt-free export lifecycle, progress events, and cooperative cancellation."""

from __future__ import annotations

import threading
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator, Literal

from .process_control import ProcessCancelled
from .project import JobState


ProgressOperation = Literal["analysis", "export"]
ProgressOutcome = Literal["completed", "skipped"]
ProgressCallback = Callable[["ProgressEvent"], None]


@dataclass(frozen=True, slots=True)
class ProgressEvent:
    operation: ProgressOperation
    phase: str
    completed_units: int
    total_units: int | None = None
    item_index: int | None = None
    item_path: Path | None = None
    outcome: ProgressOutcome | None = None
    cache_hit: bool | None = None

    def __post_init__(self) -> None:
        if self.operation not in {"analysis", "export"}:
            raise ValueError(f"unsupported progress operation: {self.operation}")
        if not isinstance(self.phase, str) or not self.phase:
            raise ValueError("phase must be a non-empty string")
        if self.completed_units < 0:
            raise ValueError("completed_units must be non-negative")
        if self.total_units is not None:
            if self.total_units < 0:
                raise ValueError("total_units must be non-negative")
            if self.completed_units > self.total_units:
                raise ValueError("completed_units cannot exceed total_units")
        if self.item_index is not None and self.item_index < 1:
            raise ValueError("item_index must be positive")
        if self.item_path is not None and not isinstance(self.item_path, Path):
            raise TypeError("item_path must be Path or None")
        if self.outcome not in {None, "completed", "skipped"}:
            raise ValueError(f"unsupported progress outcome: {self.outcome}")
        if self.cache_hit is not None and type(self.cache_hit) is not bool:
            raise ValueError("cache_hit must be boolean or None")


class ExportCancelled(RuntimeError):
    """Application-level cancellation after confirmed process-tree shutdown."""


class ExecutionContext:
    """Thread-safe state machine for one export invocation."""

    def __init__(self, progress: ProgressCallback | None = None) -> None:
        self._lock = threading.Lock()
        self._state = JobState.PLANNED
        self._publication_started = False
        self._progress = progress
        self._last_completed = {"analysis": 0, "export": 0}
        self._totals: dict[str, int | None] = {"analysis": None, "export": None}

    @property
    def state(self) -> JobState:
        with self._lock:
            return self._state

    @property
    def cancel_requested(self) -> bool:
        with self._lock:
            return self._state is JobState.CANCEL_REQUESTED

    def start(self) -> None:
        with self._lock:
            if self._state is not JobState.PLANNED:
                raise RuntimeError(f"cannot start execution in {self._state.value}")
            self._state = JobState.RUNNING

    def request_cancel(self) -> bool:
        """Accept cancellation only while running and before publication commit."""

        with self._lock:
            if self._state is JobState.CANCEL_REQUESTED:
                return True
            if self._state is not JobState.RUNNING or self._publication_started:
                return False
            self._state = JobState.CANCEL_REQUESTED
            return True

    def checkpoint(self) -> None:
        if self.cancel_requested:
            raise ExportCancelled("export cancelled")

    def begin_publication(self) -> bool:
        """Atomically cross the point after which cancellation is too late."""

        with self._lock:
            if self._state is JobState.CANCEL_REQUESTED:
                return False
            if self._state is not JobState.RUNNING:
                raise RuntimeError(
                    f"cannot publish execution in {self._state.value}"
                )
            self._publication_started = True
            return True

    def succeeded(self) -> None:
        with self._lock:
            if self._state is not JobState.RUNNING or not self._publication_started:
                raise RuntimeError("succeeded requires a committed publication")
            self._state = JobState.SUCCEEDED

    def cancelled(self) -> None:
        with self._lock:
            if self._state is not JobState.CANCEL_REQUESTED:
                raise RuntimeError("cancelled requires cancel-requested")
            self._state = JobState.CANCELLED

    def failed(self) -> None:
        with self._lock:
            if self._state not in {JobState.RUNNING, JobState.CANCEL_REQUESTED}:
                return
            self._state = JobState.FAILED

    def emit(self, event: ProgressEvent) -> None:
        with self._lock:
            last = self._last_completed[event.operation]
            if event.completed_units < last:
                raise RuntimeError("progress events must be monotonic")
            known_total = self._totals[event.operation]
            if known_total is not None and event.total_units != known_total:
                raise RuntimeError("progress total must remain stable")
            if event.total_units is not None:
                self._totals[event.operation] = event.total_units
            self._last_completed[event.operation] = event.completed_units
            callback = self._progress
        if callback is not None:
            try:
                callback(event)
            except Exception:
                # Progress is observational and must never change publication.
                pass


_CURRENT_EXECUTION: ContextVar[ExecutionContext | None] = ContextVar(
    "video_chronicle_execution", default=None
)


def current_execution_context() -> ExecutionContext | None:
    return _CURRENT_EXECUTION.get()


@contextmanager
def bind_execution_context(context: ExecutionContext) -> Iterator[None]:
    token = _CURRENT_EXECUTION.set(context)
    try:
        yield
    finally:
        _CURRENT_EXECUTION.reset(token)


def translate_process_cancel(exc: ProcessCancelled) -> ExportCancelled:
    return ExportCancelled(str(exc))
