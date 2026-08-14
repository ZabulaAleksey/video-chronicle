from __future__ import annotations

import logging
import errno
import threading
from contextlib import nullcontext
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from video_chronicle.application import SourceChangedError, execute_plan, plan_export
from video_chronicle.domain import ExportPlan, ExportRequest, MediaItem, SourceFingerprint
from video_chronicle.execution import ExecutionContext, ExportCancelled, ProgressEvent
from video_chronicle.overlay import OverlayConfig
from video_chronicle.ports import PipelinePorts
from video_chronicle.project import JobState
from video_chronicle.process_control import ProcessTreeTerminationError


class _CacheStub:
    def __init__(self, restore_result=False, restore_error=None) -> None:
        self.restore_result = restore_result
        self.restore_error = restore_error
        self.hits = 0
        self.misses = 0
        self.stores = 0
        self.prunes = 0

    def operation(self):
        return nullcontext()

    def restore(self, item, request, destination, runner):
        if self.restore_error is not None:
            if callable(self.restore_error):
                self.restore_error()
            else:
                raise self.restore_error
        if self.restore_result:
            destination.write_bytes(b"cached")
        return self.restore_result

    def store(self, item, request, artifact, runner):
        self.stores += 1
        return True

    def prune(self):
        self.prunes += 1
        return 0


def _plan(tmp_path: Path, *, count: int = 1, keep_work: bool = False) -> ExportPlan:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    items = []
    for index in range(count):
        path = input_dir / f"2024010{index + 1}_000000.mp4"
        path.write_bytes(f"source-{index}".encode())
        items.append(
            MediaItem(path, datetime(2024, 1, index + 1), False, True, "fixture")
        )
    request = ExportRequest(
        input_dir=input_dir,
        output=tmp_path / "output.mp4",
        error_log=tmp_path / "errors.log",
        ffmpeg="ffmpeg",
        ffprobe="ffprobe",
        crf=20,
        preset="medium",
        overwrite=False,
        keep_work=keep_work,
        overlay=OverlayConfig(enabled=False),
    )
    return ExportPlan(request, tuple(items))


def _ports(
    tmp_path: Path,
    *,
    normalize=None,
    concatenate=None,
    publish=None,
) -> tuple[PipelinePorts, Path]:
    workspace = tmp_path / "work"

    def default_normalize(item, destination, *args):
        destination.write_bytes(b"clip")

    def default_concat(clips, manifest, temporary, *args):
        temporary.write_bytes(b"movie")

    def default_publish(temporary, output, overwrite):
        temporary.replace(output)

    return (
        PipelinePorts(
            command_runner=lambda *args, **kwargs: SimpleNamespace(
                returncode=0, stdout="", stderr=""
            ),
            probe_media=lambda *args: {},
            inspect_item=lambda *args: None,  # type: ignore[arg-type]
            normalize_item=normalize or default_normalize,
            concatenate=concatenate or default_concat,
            publish_output=publish or default_publish,
            collect_source_paths=lambda *args: [],
            create_workspace=lambda parent: (workspace.mkdir(), workspace)[1],
            cleanup_workspace=lambda path: __import__("shutil").rmtree(path),
            validate_source=lambda root, source: None,
        ),
        workspace,
    )


def _run_in_thread(plan, ports, context):
    result: list[object] = []

    def target():
        try:
            result.append(execute_plan(plan, logging.getLogger(__name__), ports, execution=context))
        except BaseException as exc:
            result.append(exc)

    thread = threading.Thread(target=target)
    thread.start()
    return thread, result


def test_success_progress_uses_items_plus_concat_and_publication(tmp_path: Path) -> None:
    plan = _plan(tmp_path, count=2)
    ports, workspace = _ports(tmp_path)
    events: list[ProgressEvent] = []
    context = ExecutionContext(events.append)

    assert execute_plan(plan, logging.getLogger(__name__), ports, execution=context) == 0

    assert context.state is JobState.SUCCEEDED
    assert [event.completed_units for event in events] == [0, 1, 2, 3, 4]
    assert all(event.total_units == 4 for event in events)
    assert events[-1].phase == "publication"
    assert plan.request.output.read_bytes() == b"movie"
    assert not workspace.exists()


def test_cache_hit_skips_normalization_and_reports_hit(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    normalized = 0

    def normalize(*args):
        nonlocal normalized
        normalized += 1

    ports, _ = _ports(tmp_path, normalize=normalize)
    cache = _CacheStub(restore_result=True)
    events: list[ProgressEvent] = []
    assert execute_plan(plan, logging.getLogger(__name__), ports, progress=events.append, cache=cache) == 0
    assert normalized == 0
    assert next(event for event in events if event.phase == "normalize").cache_hit is True
    assert cache.stores == 0
    assert cache.prunes == 1


def test_cache_miss_normalizes_stores_and_reports_miss(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    ports, _ = _ports(tmp_path)
    cache = _CacheStub()
    events: list[ProgressEvent] = []
    assert execute_plan(plan, logging.getLogger(__name__), ports, progress=events.append, cache=cache) == 0
    assert next(event for event in events if event.phase == "normalize").cache_hit is False
    assert cache.stores == 1
    assert cache.prunes == 1


def test_cache_rejection_and_store_permission_error_warn_but_export_succeeds(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    from video_chronicle.cache import CacheEntryRejected

    plan = _plan(tmp_path)
    ports, _ = _ports(tmp_path)

    class FailingCache(_CacheStub):
        def restore(self, *args):
            raise CacheEntryRejected("tampered manifest")

        def store(self, *args):
            raise PermissionError("disk denied")

    with caplog.at_level(logging.WARNING):
        assert execute_plan(
            plan, logging.getLogger(__name__), ports, cache=FailingCache()
        ) == 0
    assert plan.request.output.is_file()
    assert "tampered manifest" in caplog.text
    assert "disk denied" in caplog.text


def test_cache_enospc_store_failure_is_clean_success(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    plan = _plan(tmp_path)
    ports, _ = _ports(tmp_path)

    class FullCache(_CacheStub):
        def store(self, *args):
            raise OSError(errno.ENOSPC, "cache disk full")

    with caplog.at_level(logging.WARNING):
        assert execute_plan(
            plan, logging.getLogger(__name__), ports, cache=FullCache()
        ) == 0
    assert plan.request.output.is_file()
    assert "cache disk full" in caplog.text


def test_cache_lookup_does_not_swallow_process_safety(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    ports, workspace = _ports(tmp_path)
    cache = _CacheStub(restore_error=ProcessTreeTerminationError("unsafe"))
    with pytest.raises(RuntimeError, match="safe ownership"):
        execute_plan(plan, logging.getLogger(__name__), ports, cache=cache)
    assert not workspace.exists()


def test_cache_lookup_propagates_confirmed_cancellation(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    ports, workspace = _ports(tmp_path)
    context = ExecutionContext()

    def cancel() -> None:
        assert context.request_cancel()
        raise ExportCancelled("cancelled")

    with pytest.raises(ExportCancelled):
        execute_plan(
            plan,
            logging.getLogger(__name__),
            ports,
            cache=_CacheStub(restore_error=cancel),
            execution=context,
        )
    assert context.state is JobState.CANCELLED
    assert not workspace.exists()


def test_source_changed_during_cache_lookup_is_rejected_before_normalize(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    item = replace(plan.items[0], source_fingerprint=SourceFingerprint.capture(plan.items[0].path))
    plan = replace(plan, items=(item,))
    normalized = False

    def mutate_source() -> None:
        item.path.write_bytes(b"changed-after-cache-lookup")
        raise OSError("lookup failed")

    def normalize(*args):
        nonlocal normalized
        normalized = True

    ports, workspace = _ports(tmp_path, normalize=normalize)
    with pytest.raises(SourceChangedError):
        execute_plan(
            plan,
            logging.getLogger(__name__),
            ports,
            cache=_CacheStub(restore_error=mutate_source),
        )
    assert normalized is False
    assert not workspace.exists()


def test_interrupted_export_resumes_completed_clip_from_filesystem_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import video_chronicle.cache as cache_module
    from video_chronicle.cache import NormalizedClipCache

    monkeypatch.setattr(cache_module, "_validate_normalized_stream", lambda *args: None)
    plan = _plan(tmp_path, count=2)
    ffmpeg = tmp_path / "ffmpeg.exe"
    ffprobe = tmp_path / "ffprobe.exe"
    ffmpeg.write_bytes(b"ffmpeg")
    ffprobe.write_bytes(b"ffprobe")
    plan = replace(
        plan,
        request=replace(plan.request, ffmpeg=str(ffmpeg), ffprobe=str(ffprobe)),
    )
    before = {item.path: item.path.read_bytes() for item in plan.items}
    context = ExecutionContext()
    calls = 0

    def interrupted_normalize(item, destination, *args):
        nonlocal calls
        calls += 1
        if calls == 2:
            assert context.request_cancel()
            raise ExportCancelled("cancelled during second clip")
        destination.write_bytes(b"clip-one")

    first_ports, first_workspace = _ports(tmp_path, normalize=interrupted_normalize)
    cache = NormalizedClipCache(tmp_path / "cache")
    with pytest.raises(ExportCancelled):
        execute_plan(
            plan,
            logging.getLogger(__name__),
            first_ports,
            execution=context,
            cache=cache,
        )
    assert not plan.request.output.exists()
    assert not first_workspace.exists()
    assert len(list(cache.root.glob("clip-v1-*"))) == 1

    normalized: list[Path] = []

    def resumed_normalize(item, destination, *args):
        normalized.append(item.path)
        destination.write_bytes(b"clip-two")

    second_ports, second_workspace = _ports(tmp_path, normalize=resumed_normalize)
    events: list[ProgressEvent] = []
    assert execute_plan(
        plan,
        logging.getLogger(__name__),
        second_ports,
        progress=events.append,
        cache=cache,
    ) == 0
    normalize_events = [event for event in events if event.phase == "normalize"]
    assert [event.cache_hit for event in normalize_events] == [True, False]
    assert normalized == [plan.items[1].path]
    assert plan.request.output.is_file()
    assert not second_workspace.exists()
    assert {item.path: item.path.read_bytes() for item in plan.items} == before


def test_skipped_item_progress_is_monotonic_and_failure_is_not_100_percent(
    tmp_path: Path,
) -> None:
    plan = _plan(tmp_path)

    def fail_normalize(*args):
        raise RuntimeError("bad media")

    ports, workspace = _ports(tmp_path, normalize=fail_normalize)
    events: list[ProgressEvent] = []
    context = ExecutionContext(events.append)

    with pytest.raises(RuntimeError, match="no files"):
        execute_plan(plan, logging.getLogger(__name__), ports, execution=context)

    assert context.state is JobState.FAILED
    assert [(event.completed_units, event.outcome) for event in events] == [
        (0, None),
        (1, "skipped"),
    ]
    assert events[-1].completed_units < events[-1].total_units
    assert not workspace.exists()


def test_cancel_before_workspace_is_created(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    ports, workspace = _ports(tmp_path)
    context: ExecutionContext

    def on_progress(event: ProgressEvent) -> None:
        if event.phase == "preflight":
            assert context.request_cancel() is True

    context = ExecutionContext(on_progress)
    with pytest.raises(ExportCancelled):
        execute_plan(plan, logging.getLogger(__name__), ports, execution=context)
    assert context.state is JobState.CANCELLED
    assert not workspace.exists()
    assert not plan.request.output.exists()


@pytest.mark.parametrize("point", ["normalize", "between-items", "concat"])
def test_cancel_at_export_checkpoints_cleans_workspace(
    tmp_path: Path, point: str
) -> None:
    plan = _plan(tmp_path, count=2)
    entered = threading.Event()
    release = threading.Event()

    def normalize(item, destination, *args):
        destination.write_bytes(b"clip")
        if point == "normalize" and item == plan.items[0]:
            entered.set()
            release.wait(2)

    def concat(clips, manifest, temporary, *args):
        temporary.write_bytes(b"movie")
        if point == "concat":
            entered.set()
            release.wait(2)

    context = ExecutionContext(
        lambda event: (
            entered.set()
            if point == "between-items"
            and event.phase == "normalize"
            and event.completed_units == 1
            else None
        )
    )
    ports, workspace = _ports(tmp_path, normalize=normalize, concatenate=concat)
    thread, result = _run_in_thread(plan, ports, context)
    assert entered.wait(2)
    assert context.request_cancel() is True
    release.set()
    thread.join(3)

    assert len(result) == 1 and isinstance(result[0], ExportCancelled)
    assert context.state is JobState.CANCELLED
    assert not plan.request.output.exists()
    assert not workspace.exists()


def test_publication_commit_wins_late_cancel_race(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    context = ExecutionContext()
    accepted: list[bool] = []

    def publish(temporary, output, overwrite):
        accepted.append(context.request_cancel())
        temporary.replace(output)

    ports, _ = _ports(tmp_path, publish=publish)
    assert execute_plan(plan, logging.getLogger(__name__), ports, execution=context) == 0
    assert accepted == [False]
    assert context.state is JobState.SUCCEEDED
    assert plan.request.output.read_bytes() == b"movie"


def test_cancel_preserves_existing_output_and_keep_work_is_diagnostic(
    tmp_path: Path,
) -> None:
    plan = _plan(tmp_path, keep_work=True)
    plan.request.output.write_bytes(b"existing")
    plan = ExportPlan(
        __import__("dataclasses").replace(plan.request, overwrite=True), plan.items
    )
    context: ExecutionContext

    def progress(event):
        if event.phase == "concat":
            context.request_cancel()

    context = ExecutionContext(progress)
    ports, workspace = _ports(tmp_path)
    with pytest.raises(ExportCancelled):
        execute_plan(plan, logging.getLogger(__name__), ports, execution=context)

    assert plan.request.output.read_bytes() == b"existing"
    assert workspace.is_dir()
    assert (workspace / "output.building.mp4").read_bytes() == b"movie"


def test_analysis_progress_counts_each_inspected_or_skipped_source(
    tmp_path: Path,
) -> None:
    plan = _plan(tmp_path, count=2)
    events: list[ProgressEvent] = []

    def inspect(path, *args):
        if path == plan.items[1].path:
            raise RuntimeError("corrupt")
        return plan.items[0]

    ports, _ = _ports(tmp_path)
    ports = __import__("dataclasses").replace(
        ports,
        collect_source_paths=lambda *args: [item.path for item in plan.items],
        inspect_item=inspect,
    )
    result = plan_export(plan.request, ports, progress=events.append)

    assert len(result.items) == 1
    assert [event.completed_units for event in events] == [0, 1, 2]
    assert [event.outcome for event in events] == [None, "completed", "skipped"]
    assert all(event.total_units == 2 for event in events)


def test_unconfirmed_cancel_failure_is_failed_not_cancelled(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    entered = threading.Event()
    release = threading.Event()

    def normalize(*args):
        entered.set()
        release.wait(2)
        raise RuntimeError("tree termination could not be confirmed")

    ports, workspace = _ports(tmp_path, normalize=normalize)
    context = ExecutionContext()
    thread, result = _run_in_thread(plan, ports, context)
    assert entered.wait(2)
    assert context.request_cancel() is True
    release.set()
    thread.join(3)

    assert len(result) == 1
    assert isinstance(result[0], RuntimeError)
    assert "could not be confirmed" in str(result[0])
    assert context.state is JobState.FAILED
    assert not workspace.exists()


def test_process_tree_safety_failure_is_fatal_not_a_skipped_item(
    tmp_path: Path,
) -> None:
    plan = _plan(tmp_path, count=2)

    def normalize(*args):
        raise ProcessTreeTerminationError("tree still active")

    ports, workspace = _ports(tmp_path, normalize=normalize)
    context = ExecutionContext()
    with pytest.raises(RuntimeError, match="safe ownership or termination"):
        execute_plan(plan, logging.getLogger(__name__), ports, execution=context)

    assert context.state is JobState.FAILED
    assert not workspace.exists()
    assert not plan.request.output.exists()


def test_source_swap_after_plan_is_rejected_before_workspace(tmp_path: Path) -> None:
    seed = _plan(tmp_path)
    source = seed.items[0].path
    ports, workspace = _ports(tmp_path)
    ports = __import__("dataclasses").replace(
        ports,
        collect_source_paths=lambda *args: [source],
        inspect_item=lambda *args: seed.items[0],
    )
    plan = plan_export(seed.request, ports)
    replacement = source.with_suffix(".replacement")
    replacement.write_bytes(b"different bytes")
    replacement.replace(source)
    context = ExecutionContext()

    with pytest.raises(SourceChangedError, match="identity changed after planning"):
        execute_plan(plan, logging.getLogger(__name__), ports, execution=context)

    assert context.state is JobState.FAILED
    assert not workspace.exists()
    assert not plan.request.output.exists()


def test_source_swap_during_inspection_is_skipped_with_coherent_snapshot(
    tmp_path: Path,
) -> None:
    seed = _plan(tmp_path, count=2)
    changing, stable = seed.items
    ports, _ = _ports(tmp_path)

    def inspect(path, *args):
        item = changing if path == changing.path else stable
        if path == changing.path:
            replacement = path.with_suffix(".replacement")
            replacement.write_bytes(b"replacement")
            replacement.replace(path)
        return item

    ports = __import__("dataclasses").replace(
        ports,
        collect_source_paths=lambda *args: [changing.path, stable.path],
        inspect_item=inspect,
    )
    plan = plan_export(seed.request, ports)

    assert tuple(item.path for item in plan.items) == (stable.path,)
    assert plan.items[0].source_fingerprint is not None
    assert plan.inspection_failures[0][0] == changing.path
    assert "changed during inspection" in plan.inspection_failures[0][1]


def test_cancel_cleanup_must_be_confirmed_or_job_is_failed(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    context: ExecutionContext

    def progress(event):
        if event.phase == "concat":
            context.request_cancel()

    context = ExecutionContext(progress)
    ports, workspace = _ports(tmp_path)
    ports = __import__("dataclasses").replace(
        ports, cleanup_workspace=lambda path: None
    )

    with pytest.raises(RuntimeError, match="cleanup was not confirmed"):
        execute_plan(plan, logging.getLogger(__name__), ports, execution=context)

    assert context.state is JobState.FAILED
    assert workspace.is_dir()
    assert not plan.request.output.exists()


def test_publication_success_wins_later_cleanup_failure(
    tmp_path: Path, caplog
) -> None:
    plan = _plan(tmp_path)
    ports, workspace = _ports(tmp_path)
    ports = __import__("dataclasses").replace(
        ports, cleanup_workspace=lambda path: None
    )
    context = ExecutionContext()

    with caplog.at_level(logging.WARNING):
        result = execute_plan(
            plan, logging.getLogger(__name__), ports, execution=context
        )

    assert result == 0
    assert context.state is JobState.SUCCEEDED
    assert plan.request.output.read_bytes() == b"movie"
    assert workspace.is_dir()
    assert "cleanup failed after successful publication" in caplog.text
