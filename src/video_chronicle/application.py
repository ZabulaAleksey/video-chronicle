"""Application orchestration for the canonical media pipeline."""

from __future__ import annotations

import logging
from pathlib import Path

from .domain import ExportPlan, ExportRequest, MediaItem
from .ports import PipelinePorts


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
    items: list[MediaItem] = []
    failures: list[tuple[Path, str]] = []
    for path in source_paths:
        try:
            adapters.validate_source(request.input_dir, path)
            items.append(
                adapters.inspect_item(
                    path,
                    request.ffprobe,
                    adapters.probe_media,
                    adapters.command_runner,
                )
            )
        except Exception as exc:
            failures.append((path, str(exc)))
            if logger is not None:
                logger.warning("SKIPPED during inspection | %s | %s", path, exc)
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
) -> int:
    """Execute one validated export while preserving legacy partial-success rules."""

    adapters = ports or default_ports()
    return execute_plan(plan_export(request, adapters, logger), logger, adapters)


def execute_plan(
    plan: ExportPlan,
    logger: logging.Logger,
    ports: PipelinePorts,
) -> int:
    """Execute an already planned export through explicit external ports."""

    request = plan.request
    items = plan.items
    failed_count = len(plan.inspection_failures)

    work_dir_path = ports.create_workspace(request.output.parent)
    temporary_output = work_dir_path / "output.building.mp4"
    successful_clips: list[Path] = []
    try:
        for index, item in enumerate(items, start=1):
            destination = work_dir_path / f"clip_{index:06d}.mp4"
            logger.info(
                "[%d/%d] %s | %s | %s",
                index,
                len(items),
                item.taken_at.strftime("%d.%m.%Y %H:%M"),
                item.date_source,
                item.path.name,
            )
            try:
                ports.validate_source(request.input_dir, item.path)
                ports.normalize_item(
                    item,
                    destination,
                    request.ffmpeg,
                    request.font_file,
                    request.crf,
                    request.preset,
                    ports.command_runner,
                )
                successful_clips.append(destination)
            except Exception as exc:
                failed_count += 1
                logger.warning("SKIPPED during encoding | %s | %s", item.path, exc)

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
        ports.publish_output(
            temporary_output, request.output, request.overwrite
        )
        logger.info("Done: %s", request.output)
        logger.info("Files skipped with errors: %d", failed_count)
        logger.info("Error log: %s", request.error_log)
    finally:
        if request.keep_work:
            logger.info("Work files kept in: %s", work_dir_path)
        else:
            ports.cleanup_workspace(work_dir_path)
    return 0
