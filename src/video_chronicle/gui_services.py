"""Qt worker boundary for the canonical application services.

This module contains no widgets.  It translates the validated GUI form into the
existing application request and owns the lifetime of one worker thread at a
time.  The media pipeline itself remains in :mod:`video_chronicle.application`.
"""

from __future__ import annotations

import inspect
import logging
import os
import tempfile
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot

from gui_contract import GuiRunRequest

from .domain import ExportPlan, ExportRequest
from .execution import ExecutionContext, ProgressEvent
from .ports import PipelinePorts
from .overlay import OverlayConfig, require_resolved_overlay_font, resolve_overlay_font


def build_application_request(request: GuiRunRequest) -> ExportRequest:
    """Resolve a GUI form into the canonical request without doing media work.

    Existing output is intentionally allowed during planning.  The GUI asks for
    overwrite consent immediately before execution and the publication adapter
    still performs the final collision check.
    """

    from . import pipeline

    input_dir = request.input_dir.expanduser().resolve()
    output = request.output.expanduser().resolve()
    error_log = output.parent / "errors.log"
    pipeline.validate_error_log_path(input_dir, output, error_log)
    ffmpeg = pipeline.resolve_executable(request.ffmpeg, "FFmpeg")
    ffprobe = pipeline.resolve_executable(request.ffprobe, "FFprobe")
    overlay = resolve_overlay_font(request.overlay, pipeline.find_default_font())
    return ExportRequest(
        input_dir=input_dir,
        output=output,
        error_log=error_log,
        ffmpeg=ffmpeg,
        ffprobe=ffprobe,
        crf=request.crf,
        preset=request.preset,
        overwrite=False,
        keep_work=False,
        overlay=overlay,
        mode=request.mode,
    )


def replace_plan_overlay(plan: ExportPlan, overlay: OverlayConfig) -> ExportPlan:
    """Replace only overlay settings while preserving inspected media/order."""

    return replace(plan, request=replace(plan.request, overlay=overlay))


class _SignalLogHandler(logging.Handler):
    """Forward formatted application logs through a thread-safe Qt signal."""

    def __init__(self, emit_text: Callable[[str], None]) -> None:
        super().__init__(logging.INFO)
        self._emit_text = emit_text
        self.setFormatter(logging.Formatter("%(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._emit_text(self.format(record) + "\n")
        except Exception:
            self.handleError(record)


class _TaskWorker(QObject):
    """Run one Python callable after being moved to a dedicated ``QThread``."""

    outcome = Signal(object, object)
    finished = Signal()

    def __init__(self, task: Callable[[], object]) -> None:
        super().__init__()
        self._task = task

    @Slot()
    def run(self) -> None:
        try:
            result = self._task()
        except Exception as exc:  # application errors become user-visible state
            self.outcome.emit(None, exc)
        else:
            self.outcome.emit(result, None)
        finally:
            self.finished.emit()


PlanService = Callable[[ExportRequest, PipelinePorts, logging.Logger | None], ExportPlan]
ExecuteService = Callable[[ExportPlan, logging.Logger, PipelinePorts], int]


class ApplicationServiceAdapter(QObject):
    """Asynchronous GUI boundary around ``plan_export`` and ``execute_plan``."""

    started = Signal(str)
    output_received = Signal(str)
    plan_ready = Signal(object)
    preview_ready = Signal(object)
    completed = Signal(str, bool, str)
    progress_received = Signal(object)
    execution_state_changed = Signal(str)

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        plan_service: PlanService | None = None,
        execute_service: ExecuteService | None = None,
        ports_factory: Callable[[], PipelinePorts] | None = None,
        request_factory: Callable[[GuiRunRequest], ExportRequest] = build_application_request,
        preview_service: Callable[..., None] | None = None,
        cancel_capable: bool | None = None,
    ) -> None:
        super().__init__(parent)
        from . import application

        self._plan_service = plan_service or application.plan_export
        self._execute_service = execute_service or application.execute_plan
        self._ports_factory = ports_factory or application.default_ports
        self._cancel_capable = (
            execute_service is None and ports_factory is None
            if cancel_capable is None
            else cancel_capable
        )
        self._request_factory = request_factory
        if preview_service is None:
            from . import pipeline

            preview_service = pipeline.render_overlay_preview
        self._preview_service = preview_service
        self._thread: QThread | None = None
        self._worker: _TaskWorker | None = None
        self._operation: str | None = None
        self._outcome: tuple[object | None, BaseException | None] = (None, None)
        self._output_path: Path | None = None
        self._output_before: tuple[int, int, int, int] | None = None
        self._preview_path: Path | None = None
        self._execution_context: ExecutionContext | None = None
        self._last_terminal_state: str | None = None

    @property
    def is_running(self) -> bool:
        """Return true through worker teardown, not merely task completion."""

        return self._thread is not None

    @property
    def current_operation(self) -> str | None:
        return self._operation

    @property
    def last_terminal_state(self) -> str | None:
        return self._last_terminal_state

    @property
    def supports_cancel(self) -> bool:
        from .process_control import safe_cancel_supported

        return self._cancel_capable and safe_cancel_supported() and _declares_keyword(
            self._execute_service, "execution"
        )

    def start_analysis(self, request: GuiRunRequest) -> None:
        """Resolve tools and create an immutable export plan off the UI thread."""

        def task() -> ExportPlan:
            canonical = self._request_factory(request)
            ports = self._ports_factory()
            logger = self._memory_logger("analysis")
            try:
                if _accepts_keyword(self._plan_service, "progress"):
                    return self._plan_service(
                        canonical,
                        ports,
                        logger,
                        progress=self.progress_received.emit,
                    )
                return self._plan_service(canonical, ports, logger)
            finally:
                self._close_logger(logger)

        self._start("analysis", task)

    def start_export(
        self,
        plan: ExportPlan,
        *,
        overwrite: bool,
        cache_enabled: bool = False,
        cache_dir: Path | None = None,
    ) -> None:
        """Execute the exact previewed plan with an explicit overwrite decision."""

        if self.is_running:
            raise RuntimeError("Другая операция уже выполняется.")
        executable_plan = replace(
            plan,
            request=replace(plan.request, overwrite=overwrite),
        )
        self._output_path = executable_plan.request.output
        self._output_before = _file_identity(self._output_path)
        self._last_terminal_state = None
        execution = (
            ExecutionContext(self.progress_received.emit)
            if self.supports_cancel
            else None
        )
        self._execution_context = execution

        def task() -> int:
            from . import pipeline
            from .cache import NormalizedClipCache

            pipeline.validate_error_log_path(
                executable_plan.request.input_dir,
                executable_plan.request.output,
                executable_plan.request.error_log,
            )
            logger = pipeline.configure_logging(executable_plan.request.error_log)
            handler = _SignalLogHandler(self.output_received.emit)
            logger.addHandler(handler)
            try:
                kwargs: dict[str, object] = {}
                if execution is not None:
                    kwargs["execution"] = execution
                if cache_enabled and _accepts_keyword(self._execute_service, "cache"):
                    kwargs["cache"] = NormalizedClipCache(cache_dir)
                return self._execute_service(
                    executable_plan, logger, self._ports_factory(), **kwargs
                )
            finally:
                logger.removeHandler(handler)
                handler.close()

        self._start("export", task)

    def start_cache_purge(
        self,
        cache_dir: Path | None = None,
        *,
        protected_input: Path | None = None,
        protected_output: Path | None = None,
    ) -> None:
        """Purge only verified cache entries off the UI thread."""

        def task() -> int:
            from .cache import NormalizedClipCache

            return NormalizedClipCache(cache_dir).purge(
                protected_input=protected_input,
                protected_output=protected_output,
            )

        self._start("cache-purge", task)

    def cancel_export(self) -> bool:
        """Request cancellation of the active application-service export."""

        context = self._execution_context
        if self._operation != "export" or context is None:
            return False
        accepted = context.request_cancel()
        if accepted:
            self.execution_state_changed.emit(context.state.value)
        return accepted

    def start_preview(self, plan: ExportPlan) -> None:
        """Render a representative 640x360 PNG for the first accepted item."""

        if self.is_running:
            raise RuntimeError("Другая операция уже выполняется.")
        if not plan.items:
            raise RuntimeError("В плане нет принятого media item для preview.")

        def task() -> Path:
            descriptor, raw_path = tempfile.mkstemp(
                prefix="video_chronicle_preview_", suffix=".png"
            )
            os.close(descriptor)
            path = Path(raw_path)
            try:
                require_resolved_overlay_font(plan.request.overlay)
                ports = self._ports_factory()
                ports.validate_source(plan.request.input_dir, plan.items[0].path)
                self._preview_service(
                    plan.items[0],
                    plan.request.overlay,
                    plan.request.ffmpeg,
                    path,
                    ports.command_runner,
                )
                return path
            except Exception:
                path.unlink(missing_ok=True)
                raise

        self._start("preview", task)

    def _memory_logger(self, suffix: str) -> logging.Logger:
        logger = logging.getLogger(f"video_chronicle.gui.{suffix}.{id(self)}")
        logger.setLevel(logging.INFO)
        logger.propagate = False
        for existing in logger.handlers[:]:
            logger.removeHandler(existing)
            existing.close()
        logger.addHandler(_SignalLogHandler(self.output_received.emit))
        return logger

    @staticmethod
    def _close_logger(logger: logging.Logger) -> None:
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
            handler.close()

    def _start(self, operation: str, task: Callable[[], object]) -> None:
        if self.is_running:
            raise RuntimeError("Другая операция уже выполняется.")
        self._operation = operation
        self._outcome = (None, None)
        thread = QThread(self)
        worker = _TaskWorker(task)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.outcome.connect(
            self._capture_outcome,
            Qt.ConnectionType.DirectConnection,
        )
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._finish_task)
        thread.finished.connect(thread.deleteLater)
        self._thread = thread
        self._worker = worker
        self.started.emit(operation)
        thread.start()

    @Slot(object, object)
    def _capture_outcome(
        self, result: object | None, error: BaseException | None
    ) -> None:
        # Direct connection: only immutable references are handed back.  The UI
        # is notified later from ``_finish_task`` on its owning thread.
        self._outcome = (result, error)

    @Slot()
    def _finish_task(self) -> None:
        operation = self._operation or "operation"
        result, error = self._outcome
        execution = self._execution_context if operation == "export" else None
        if execution is not None:
            self._last_terminal_state = execution.state.value
            self.execution_state_changed.emit(execution.state.value)
        self._thread = None
        self._worker = None
        self._operation = None
        self._execution_context = None

        if error is not None:
            if operation == "export" and self._last_terminal_state == "cancelled":
                self.completed.emit(
                    operation, False, "Экспорт отменён; итоговый файл не опубликован."
                )
                return
            self.completed.emit(operation, False, str(error))
            return
        if operation == "analysis":
            if not isinstance(result, ExportPlan):
                self.completed.emit(operation, False, "Анализ не вернул export plan.")
                return
            self.plan_ready.emit(result)
            self.completed.emit(operation, True, "План анализа готов.")
            return
        if operation == "preview":
            if not isinstance(result, Path) or not result.is_file():
                self.completed.emit(
                    operation, False, "Предпросмотр не создал временный PNG."
                )
                return
            self._preview_path = result
            self.preview_ready.emit(result)
            # The GUI slot loads QPixmap synchronously before this queued
            # completion and removes the file. This fallback prevents a leak
            # for headless/non-widget consumers.
            result.unlink(missing_ok=True)
            self._preview_path = None
            self.completed.emit(operation, True, "Предпросмотр обновлён.")
            return
        if operation == "cache-purge":
            self.completed.emit(
                operation, True, f"Кэш очищен: {int(result or 0)} entries."
            )
            return

        output_after = (
            _file_identity(self._output_path)
            if self._output_path is not None
            else None
        )
        published = output_after is not None and output_after != self._output_before
        if result == 0 and published:
            self.completed.emit(operation, True, f"Готово: {self._output_path}")
        elif result == 0:
            self.completed.emit(
                operation,
                False,
                "Экспорт завершился без ошибки, но новый итоговый файл не подтверждён.",
            )
        else:
            self.completed.emit(operation, False, f"Экспорт завершился с кодом {result}.")


def _file_identity(path: Path) -> tuple[int, int, int, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)


def _accepts_keyword(callable_value: Callable[..., object], keyword: str) -> bool:
    """Keep injected legacy callables compatible while enabling new options."""

    try:
        parameters = inspect.signature(callable_value).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(
        parameter.name == keyword
        or parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in parameters
    )


def _declares_keyword(callable_value: Callable[..., object], keyword: str) -> bool:
    """Require explicit opt-in before advertising a safety capability."""

    try:
        parameter = inspect.signature(callable_value).parameters.get(keyword)
    except (TypeError, ValueError):
        return False
    return parameter is not None and parameter.kind in {
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        inspect.Parameter.KEYWORD_ONLY,
    }
