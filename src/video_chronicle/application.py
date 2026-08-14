"""Application orchestration for the canonical media pipeline."""

from __future__ import annotations

import logging
from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path
from typing import Callable, TYPE_CHECKING

from .domain import ExportPlan, ExportRequest, MediaItem, SourceFingerprint
from .project import (
    EditingClipSnapshot,
    EditingExportSnapshot,
    ProjectState,
    TimelineItem,
)
from .execution import (
    ExecutionContext,
    ExportCancelled,
    ProgressEvent,
    bind_execution_context,
)
from .ports import CommandRunner, NormalizedClipCachePort, PipelinePorts
from .overlay import require_resolved_overlay_font
from .process_control import ProcessSafetyError

if TYPE_CHECKING:
    from .interchange import OptionalFeature
    from .scene import OptionalSceneFeature


def default_ports() -> PipelinePorts:
    """Bind production adapters late so tests can replace canonical functions."""

    from . import pipeline

    return PipelinePorts(
        command_runner=pipeline.run_command,
        probe_media=pipeline.probe_media,
        inspect_item=pipeline.inspect_item,
        normalize_item=pipeline.normalize_item,
        concatenate=pipeline.concatenate,
        publish_output=pipeline.publish_output,
        collect_source_paths=pipeline.collect_source_paths,
        create_workspace=pipeline.create_workspace,
        cleanup_workspace=pipeline.cleanup_workspace,
        validate_source=pipeline.validate_source_path,
    )


def plan_export(
    request: ExportRequest,
    ports: PipelinePorts | None = None,
    logger: logging.Logger | None = None,
    *,
    progress: Callable[[ProgressEvent], None] | None = None,
) -> ExportPlan:
    """Inspect sources into an immutable accepted timeline before encoding."""

    adapters = ports or default_ports()
    source_paths = tuple(
        adapters.collect_source_paths(
            request.input_dir, request.output, request.error_log
        )
    )
    if not source_paths:
        raise RuntimeError(
            f"no supported videos or photos found in {request.input_dir}"
        )
    if logger is not None:
        logger.info("Inspecting %d source files...", len(source_paths))
    if progress is not None:
        _notify_progress(
            progress, ProgressEvent("analysis", "inspection", 0, len(source_paths))
        )
    items: list[MediaItem] = []
    failures: list[tuple[Path, str]] = []
    for index, path in enumerate(source_paths, start=1):
        outcome = "completed"
        try:
            adapters.validate_source(request.input_dir, path)
            fingerprint_before = SourceFingerprint.capture(path)
            inspected = adapters.inspect_item(
                    path,
                    request.ffprobe,
                    adapters.probe_media,
                    adapters.command_runner,
                )
            fingerprint_after = SourceFingerprint.capture(path)
            if fingerprint_after != fingerprint_before:
                raise SourceChangedError(
                    f"source identity changed during inspection: {path}"
                )
            items.append(
                replace(
                    inspected,
                    source_fingerprint=fingerprint_after,
                )
            )
        except Exception as exc:
            outcome = "skipped"
            failures.append((path, str(exc)))
            if logger is not None:
                logger.warning("SKIPPED during inspection | %s | %s", path, exc)
        if progress is not None:
            _notify_progress(
                progress,
                ProgressEvent(
                    "analysis",
                    "inspection",
                    index,
                    len(source_paths),
                    item_index=index,
                    item_path=path,
                    outcome=outcome,
                )
            )
    items.sort(key=lambda item: (item.taken_at, item.path.name.casefold()))
    if not items:
        raise RuntimeError(
            f"none of the {len(source_paths)} files could be inspected"
        )
    if logger is not None:
        logger.info(
            "Ready: %d files, from %s to %s.",
            len(items),
            items[0].taken_at.strftime("%d.%m.%Y %H:%M:%S"),
            items[-1].taken_at.strftime("%d.%m.%Y %H:%M:%S"),
        )
    return ExportPlan(
        request=request,
        items=tuple(items),
        inspection_failures=tuple(failures),
    )


def execute_export(
    request: ExportRequest,
    logger: logging.Logger,
    ports: PipelinePorts | None = None,
    *,
    execution: ExecutionContext | None = None,
    progress: Callable[[ProgressEvent], None] | None = None,
    cache: NormalizedClipCachePort | None = None,
) -> int:
    """Execute one validated export while preserving legacy partial-success rules."""

    adapters = ports or default_ports()
    progress_callback = progress or (execution.emit if execution is not None else None)
    plan = plan_export(request, adapters, logger, progress=progress_callback)
    return execute_plan(
        plan,
        logger,
        adapters,
        execution=execution,
        progress=progress,
        cache=cache,
    )


def apply_project_state(analyzed_plan: ExportPlan, project_state: ProjectState) -> ExportPlan:
    """Bind persisted EDIT-001 IDs/edits to a fresh inspection result."""

    if not isinstance(project_state, ProjectState):
        raise TypeError("project_state must be ProjectState")
    layout = project_state.layout
    if layout is None:
        raise ValueError("project layout is missing")
    layout.validate_for(project_state.timeline)
    inspected_by_id = {
        TimelineItem.from_media_item(item).stable_id: item for item in analyzed_plan.items
    }
    timeline_by_id = {item.stable_id: item for item in project_state.timeline.items}
    effective: list[MediaItem] = []
    clips: list[EditingClipSnapshot] = []
    failures = list(analyzed_plan.inspection_failures)
    for entry in layout.entries:
        inspected = inspected_by_id.get(entry.item_id)
        if inspected is None:
            failures.append((timeline_by_id[entry.item_id].source_path, "known project source is missing or failed inspection"))
            continue
        rebound = replace(
            timeline_by_id[entry.item_id],
            media_kind="photo" if inspected.is_photo else "video",
            source_duration_us=inspected.source_duration_us,
        )
        resolved = entry.trim.resolve(rebound)
        effective.append(
            replace(
                inspected,
                trim_in_us=resolved.in_us,
                trim_out_us=resolved.out_us,
                trim_applied=not entry.trim.is_full_source,
            )
        )
        clips.append(EditingClipSnapshot(entry.item_id, resolved, entry.group_id))
    known_ids = set(timeline_by_id)
    for item_id, inspected in inspected_by_id.items():
        if item_id not in known_ids:
            failures.append(
                (inspected.path, "new source is not part of the saved project")
            )
    if not effective:
        raise ValueError("project contains no currently usable media")
    preset = project_state.resolve_active_preset()
    settings = preset.settings
    request = replace(
        analyzed_plan.request,
        mode=settings.mode,
        overlay=settings.overlay,
        crf=settings.crf,
        preset=settings.encoder_preset,
    )
    snapshot = EditingExportSnapshot.create(
        project_id=project_state.project_id,
        project_revision=project_state.revision,
        clips=tuple(clips),
        groups=layout.groups,
        preset_ref=preset.ref,
        settings=settings,
        output_path=request.output,
        overwrite=request.overwrite,
    )
    return ExportPlan(request, tuple(effective), tuple(failures), snapshot)


def execute_plan(
    plan: ExportPlan,
    logger: logging.Logger,
    ports: PipelinePorts,
    *,
    execution: ExecutionContext | None = None,
    progress: Callable[[ProgressEvent], None] | None = None,
    cache: NormalizedClipCachePort | None = None,
) -> int:
    """Execute an already planned export through explicit external ports."""

    context = execution or ExecutionContext(progress)
    if execution is not None and progress is not None:
        raise ValueError("pass either execution or progress, not both")
    request = plan.request
    items = plan.items
    total_units = len(items) + 2
    completed_units = 0
    work_dir_path: Path | None = None
    context.start()
    try:
        with bind_execution_context(context), (
            cache.operation() if cache is not None else nullcontext()
        ):
            context.emit(ProgressEvent("export", "preflight", 0, total_units))
            context.checkpoint()
            _preflight_plan(plan, ports)
            context.checkpoint()
            work_dir_path = ports.create_workspace(request.output.parent)
            temporary_output = work_dir_path / "output.building.mp4"
            successful_clips: list[Path] = []
            failed_count = len(plan.inspection_failures)
            for index, item in enumerate(items, start=1):
                context.checkpoint()
                destination = work_dir_path / f"clip_{index:06d}.mp4"
                logger.info(
                    "[%d/%d] %s | %s | %s",
                    index,
                    len(items),
                    item.taken_at.strftime("%d.%m.%Y %H:%M"),
                    item.date_source,
                    item.path.name,
                )
                outcome = "completed"
                cache_hit: bool | None = None
                try:
                    ports.validate_source(request.input_dir, item.path)
                    _require_source_fingerprint(item)
                    require_resolved_overlay_font(request.overlay)
                    if cache is not None:
                        try:
                            cache_hit = cache.restore(
                                item, request, destination, ports.command_runner
                            )
                        except (ExportCancelled, ProcessSafetyError):
                            raise
                        except Exception as exc:
                            cache_hit = False
                            logger.warning(
                                "Cache lookup failed; normalizing cleanly | %s | %s",
                                item.path,
                                exc,
                            )
                    if not cache_hit:
                        # A failed lookup may have hashed a large untrusted
                        # source. Revalidate the accepted identity immediately
                        # before handing it to FFmpeg.
                        if cache is not None:
                            ports.validate_source(request.input_dir, item.path)
                            _require_source_fingerprint(item)
                        ports.normalize_item(
                            item,
                            destination,
                            request.ffmpeg,
                            request.overlay,
                            request.crf,
                            request.preset,
                            ports.command_runner,
                        )
                        if cache is not None:
                            try:
                                cache.store(
                                    item, request, destination, ports.command_runner
                                )
                            except (ExportCancelled, ProcessSafetyError):
                                raise
                            except Exception as exc:
                                logger.warning(
                                    "Cache store failed; export continues cleanly | %s | %s",
                                    item.path,
                                    exc,
                                )
                    successful_clips.append(destination)
                except ExportCancelled:
                    raise
                except ProcessSafetyError as exc:
                    raise RuntimeError(
                        "safe ownership or termination of the tool process tree failed"
                    ) from exc
                except SourceChangedError:
                    raise
                except Exception as exc:
                    if context.cancel_requested:
                        raise RuntimeError(
                            "cancellation could not be confirmed at the active tool boundary"
                        ) from exc
                    outcome = "skipped"
                    failed_count += 1
                    logger.warning(
                        "SKIPPED during encoding | %s | %s", item.path, exc
                    )
                completed_units += 1
                context.emit(
                    ProgressEvent(
                        "export",
                        "normalize",
                        completed_units,
                        total_units,
                        item_index=index,
                        item_path=item.path,
                        outcome=outcome,
                        cache_hit=cache_hit,
                    )
                )

            context.checkpoint()
            if not successful_clips:
                raise RuntimeError("no files were successfully encoded")

            logger.info("Concatenating %d normalized clips...", len(successful_clips))
            ports.concatenate(
                successful_clips,
                work_dir_path / "concat.txt",
                temporary_output,
                request.ffmpeg,
                ports.command_runner,
            )
            completed_units += 1
            context.emit(
                ProgressEvent(
                    "export",
                    "concat",
                    completed_units,
                    total_units,
                    outcome="completed",
                )
            )
            context.checkpoint()
            if not context.begin_publication():
                raise ExportCancelled("export cancelled before publication")
            ports.publish_output(
                temporary_output, request.output, request.overwrite
            )
            completed_units += 1
            context.emit(
                ProgressEvent(
                    "export",
                    "publication",
                    completed_units,
                    total_units,
                    outcome="completed",
                )
            )
            logger.info("Done: %s", request.output)
            logger.info("Files skipped with errors: %d", failed_count)
            logger.info("Error log: %s", request.error_log)
            if cache is not None:
                try:
                    removed = cache.prune()
                    if removed:
                        logger.info("Cache pruned: %d entries.", removed)
                except Exception as exc:
                    logger.warning("Cache prune failed after successful export | %s", exc)
    except ExportCancelled:
        try:
            _cleanup_workspace(work_dir_path, request.keep_work, ports, logger)
        except Exception:
            context.failed()
            raise
        context.cancelled()
        raise
    except Exception:
        try:
            _cleanup_workspace(work_dir_path, request.keep_work, ports, logger)
        finally:
            context.failed()
        raise
    else:
        context.succeeded()
        try:
            _cleanup_workspace(work_dir_path, request.keep_work, ports, logger)
        except Exception as exc:
            logger.warning(
                "Workspace cleanup failed after successful publication | %s | %s",
                work_dir_path,
                exc,
            )
    return 0


def _cleanup_workspace(
    workspace: Path | None,
    keep_work: bool,
    ports: PipelinePorts,
    logger: logging.Logger,
) -> None:
    if workspace is None:
        return
    if keep_work:
        logger.info("Work files kept in: %s", workspace)
    else:
        ports.cleanup_workspace(workspace)
        if workspace.exists():
            raise RuntimeError(
                f"workspace cleanup was not confirmed: {workspace}"
            )


def _notify_progress(
    callback: Callable[[ProgressEvent], None], event: ProgressEvent
) -> None:
    try:
        callback(event)
    except Exception:
        # Progress is observational and cannot change planning/publication.
        pass


def _preflight_plan(plan: ExportPlan, ports: PipelinePorts) -> None:
    """Repeat cheap plan/tool/output checks before creating a workspace."""

    request = plan.request
    if not plan.items:
        raise RuntimeError("export plan contains no accepted media")
    if request.output.exists() and not request.overwrite:
        raise RuntimeError(
            f"output already exists: {request.output}. Use --overwrite to replace it."
        )
    from . import pipeline

    pipeline.validate_error_log_path(
        request.input_dir, request.output, request.error_log
    )
    require_resolved_overlay_font(request.overlay)
    for item in plan.items:
        _require_source_fingerprint(item)
    for label, value in (("FFmpeg", request.ffmpeg), ("FFprobe", request.ffprobe)):
        candidate = Path(value)
        if (candidate.is_absolute() or candidate.parent != Path(".")) and not candidate.is_file():
            raise RuntimeError(f"{label} not found: {candidate}")
    if ports.command_runner is pipeline.run_command:
        for label, value in (("FFmpeg", request.ffmpeg), ("FFprobe", request.ffprobe)):
            if not Path(value).is_file():
                # Compatibility seam for tests/embedders that intentionally
                # inject a symbolic tool name. Production request factories
                # resolve trusted binaries to existing paths before planning.
                continue
            ports.command_runner(
                [value, "-version"],
                f"{label} preflight failed",
                timeout=15,
                max_output_bytes=1024 * 1024,
            )


class SourceChangedError(RuntimeError):
    """A previewed source no longer has its inspected file identity."""


def require_source_fingerprint(item: MediaItem) -> None:
    expected = item.source_fingerprint
    if expected is None:
        # Compatibility for manually assembled legacy plans. Canonical
        # ``plan_export`` always records a fingerprint.
        return
    try:
        actual = SourceFingerprint.capture(item.path)
    except OSError as exc:
        raise SourceChangedError(
            f"source changed or disappeared after planning: {item.path}"
        ) from exc
    if actual != expected:
        raise SourceChangedError(
            f"source identity changed after planning: {item.path}"
        )


# Compatibility for internal callers and tests that patched the former helper.
_require_source_fingerprint = require_source_fingerprint


def experimental_timeline_interchange(
    environ: dict[str, str] | None = None,
) -> "OptionalFeature":
    """Return explicit OTIO availability without affecting the default path."""

    from .interchange import optional_otio_adapter

    return optional_otio_adapter(environ)


def experimental_scene_suggestions(
    ffmpeg: str,
    environ: dict[str, str] | None = None,
    *,
    runner: CommandRunner | None = None,
) -> "OptionalSceneFeature":
    """Return explicit scene-detector availability without starting a tool."""

    from .scene import optional_scene_adapter

    return optional_scene_adapter(ffmpeg, environ, runner=runner)
