from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytest
import video_chronicle.repository as repository_module

from video_chronicle.application import apply_project_state
from video_chronicle.cache import build_clip_identity, cache_key
from video_chronicle.domain import ExportMode, ExportPlan, ExportRequest, MediaItem, SourceFingerprint
from video_chronicle.overlay import OverlayConfig
from video_chronicle.pipeline import make_video_filter, normalize_item, render_overlay_preview, source_duration_us
from video_chronicle.project import (
    PHOTO_DURATION_US,
    ProjectState,
    RenderPreset,
    RenderSettings,
    Timeline,
    TimelineItem,
    TimelineLayout,
    TrimRange,
    stable_item_id,
)
from video_chronicle.repository import JsonProjectRepository, RevisionConflictError
from video_chronicle.gui_services import ApplicationServiceAdapter, replace_plan_overlay
from video_chronicle_gui import ChronicleWindow
from video_chronicle.serialization import (
    ProjectSerializationError,
    migrate_v1_state,
    project_from_mapping,
    project_to_mapping,
)


def _timeline(tmp_path: Path) -> Timeline:
    values = []
    for index, kind in enumerate(("video", "video", "photo")):
        path = (tmp_path / f"{index}.{ 'jpg' if kind == 'photo' else 'mp4'}").absolute()
        path.write_bytes(b"source")
        values.append(TimelineItem(stable_item_id(path), path, datetime(2024, 1, index + 1), "filename", media_kind=kind, source_duration_us=PHOTO_DURATION_US if kind == "photo" else 5_000_000))
    return Timeline.build(values)


def _state(tmp_path: Path) -> ProjectState:
    timeline = _timeline(tmp_path)
    settings = RenderSettings(ExportMode.JOIN, OverlayConfig(enabled=False), 20, "fast")
    preset = RenderPreset("preset-main", 1, "Main", settings)
    return ProjectState("project-edit", timeline, revision=0, layout=TimelineLayout.identity(timeline), presets=(preset,), active_preset=preset.ref)


def _request(tmp_path: Path) -> ExportRequest:
    return ExportRequest(tmp_path, (tmp_path / "out.mp4").absolute(), (tmp_path / "errors.log").absolute(), "ffmpeg", "ffprobe", 23, "medium", False, False, OverlayConfig(enabled=False), ExportMode.JOIN)


def test_layout_move_group_trim_and_revision_are_immutable(tmp_path: Path) -> None:
    state = _state(tmp_path)
    ids = state.timeline.item_ids
    moved = state.move_items((ids[2],), ids[0])
    assert tuple(entry.item_id for entry in moved.layout.entries) == (ids[2], ids[0], ids[1])  # type: ignore[union-attr]
    assert state.revision == 0 and moved.revision == 1
    grouped = moved.create_group("group-one", "First", (ids[2], ids[0]))
    with pytest.raises(ValueError, match="complete block"):
        grouped.move_items((ids[2],), None)
    trimmed = grouped.set_trim(ids[0], TrimRange(1_000_000, 3_000_000))
    assert trimmed.revision == 3
    assert grouped.layout.entries[1].trim.is_full_source  # type: ignore[union-attr]
    assert trimmed.layout.entries[1].trim == TrimRange(1_000_000, 3_000_000)  # type: ignore[union-attr]


@pytest.mark.parametrize(
    ("kind", "duration", "trim"),
    [
        ("video", 1_000_000, TrimRange(0, 16_666)),
        ("video", 1_000_000, TrimRange(0, 1_000_001)),
        ("photo", PHOTO_DURATION_US, TrimRange(1, 1_000_000)),
        ("photo", PHOTO_DURATION_US, TrimRange(0, PHOTO_DURATION_US + 1)),
    ],
)
def test_trim_bounds_reject_invalid_media_specific_ranges(tmp_path: Path, kind: str, duration: int, trim: TrimRange) -> None:
    suffix = ".jpg" if kind == "photo" else ".mp4"
    path = (tmp_path / f"one{suffix}").absolute(); path.write_bytes(b"x")
    item = TimelineItem(stable_item_id(path), path, datetime(2024, 1, 1), "filename", media_kind=kind, source_duration_us=duration)
    timeline = Timeline.build((item,))
    with pytest.raises(ValueError):
        TimelineLayout.identity(timeline).set_trim(item.stable_id, trim, timeline)


def test_duration_prefers_video_duration_ts_and_falls_back_with_decimal_floor() -> None:
    assert source_duration_us({"streams": [{"codec_type": "audio"}, {"codec_type": "video", "duration_ts": 3003, "time_base": "1/30000"}], "format": {"duration": "9.9"}}) == 100_100
    assert source_duration_us({"streams": [{"codec_type": "video"}], "format": {"duration": "1.2345679"}}) == 1_234_567
    assert source_duration_us({}, is_photo=True) == PHOTO_DURATION_US


def test_v2_round_trip_is_strict_and_repository_revision_backup_rollback(tmp_path: Path) -> None:
    state = _state(tmp_path)
    payload = project_to_mapping(state, force_v2=True)
    assert payload["version"] == 2
    assert project_from_mapping(json.loads(json.dumps(payload))) == state
    invalid = json.loads(json.dumps(payload)); invalid["project"]["layout"]["entries"][0]["extra"] = True
    with pytest.raises(ProjectSerializationError):
        project_from_mapping(invalid)
    repository = JsonProjectRepository(tmp_path / "projects")
    first = repository.save(state, expected_revision=0)
    second = repository.save(first.move_items((first.timeline.item_ids[-1],), first.timeline.item_ids[0]), expected_revision=1)
    assert second.revision == 2
    with pytest.raises(RevisionConflictError):
        repository.save(second, expected_revision=1)
    restored = repository.restore_backup(state.project_id, expected_revision=2)
    assert restored.revision == 3
    assert tuple(entry.item_id for entry in restored.layout.entries) == state.timeline.item_ids  # type: ignore[union-attr]


def test_repository_fault_before_commit_preserves_current_bytes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repository = JsonProjectRepository(tmp_path / "projects")
    first = repository.save(_state(tmp_path), expected_revision=0)
    project_path = repository.root / f"{first.project_id}.json"
    before = project_path.read_bytes()
    real_replace = repository_module.os.replace
    def fail_project_commit(source: str | Path, destination: str | Path) -> None:
        if Path(destination) == project_path:
            raise OSError("injected commit failure")
        real_replace(source, destination)
    monkeypatch.setattr(repository_module.os, "replace", fail_project_commit)
    with pytest.raises(OSError, match="injected"):
        repository.save(first.move_items((first.timeline.item_ids[-1],), first.timeline.item_ids[0]), expected_revision=1)
    assert project_path.read_bytes() == before


def test_repository_never_decreases_batched_edit_revision(tmp_path: Path) -> None:
    repository = JsonProjectRepository(tmp_path / "projects")
    state = _state(tmp_path)
    ids = state.timeline.item_ids
    edited = state.move_items((ids[-1],), ids[0]).set_trim(ids[0], TrimRange(100_000, 900_000))
    assert edited.revision == 2
    published = repository.save(edited, expected_revision=0)
    assert published.revision == 2


def test_repository_rejects_swapped_backup_project_id_without_publication(tmp_path: Path) -> None:
    repository = JsonProjectRepository(tmp_path / "projects")
    first = repository.save(_state(tmp_path), expected_revision=0)
    second = repository.save(first.move_items((first.timeline.item_ids[-1],), first.timeline.item_ids[0]), expected_revision=1)
    project_path = repository.root / f"{second.project_id}.json"
    before = project_path.read_bytes()
    other = replace(_state(tmp_path), project_id="other-project")
    project_path.with_suffix(".json.bak").write_bytes(json.dumps(project_to_mapping(other, force_v2=True), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    with pytest.raises(Exception, match="ID does not match"):
        repository.restore_backup(second.project_id, expected_revision=second.revision)
    assert project_path.read_bytes() == before


def test_existing_private_repository_root_permissions_are_not_mutated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "projects"
    JsonProjectRepository(root)
    real_chmod = repository_module.os.chmod
    def reject_root_chmod(path: str | Path, mode: int) -> None:
        if Path(path) == root:
            pytest.fail("existing repository root permissions must not be mutated")
        real_chmod(path, mode)
    monkeypatch.setattr(repository_module.os, "chmod", reject_root_chmod)
    JsonProjectRepository(root)


def test_v1_migration_adds_identity_layout_and_immutable_legacy_preset(tmp_path: Path) -> None:
    timeline = _timeline(tmp_path)
    legacy = ProjectState("legacy-project", timeline)
    migrated = migrate_v1_state(project_from_mapping(project_to_mapping(legacy)))
    assert migrated.migrated_from_v1 and migrated.revision == 0
    assert tuple(entry.item_id for entry in migrated.layout.entries) == timeline.item_ids  # type: ignore[union-attr]
    assert migrated.active_preset.preset_id == "legacy-default"  # type: ignore[union-attr]


def test_full_source_cache_v1_and_trim_cache_v2_keys_coexist(tmp_path: Path) -> None:
    source = (tmp_path / "cache.mp4").absolute(); source.write_bytes(b"unchanged")
    item = MediaItem(source, datetime(2024, 1, 1), False, False, "filename", source_duration_us=2_000_000)
    request = _request(tmp_path)
    tools = {"ffmpeg": {"version_sha256": "a" * 64}, "ffprobe": {"version_sha256": "b" * 64}}
    identity_v1 = build_clip_identity(item, request, lambda *_a, **_k: None, tool_identities=tools)
    identity_v2 = build_clip_identity(replace(item, trim_in_us=100_000, trim_out_us=900_000, trim_applied=True), request, lambda *_a, **_k: None, tool_identities=tools)
    assert cache_key(identity_v1).startswith("clip-v1-")
    assert cache_key(identity_v2).startswith("clip-v2-")
    assert identity_v2["trim"] == {"in_us": 100_000, "out_us": 900_000}


def test_apply_project_state_builds_one_deterministic_snapshot_and_exact_filters(tmp_path: Path) -> None:
    state = _state(tmp_path)
    ids = state.timeline.item_ids
    state = state.move_items((ids[1],), ids[0]).set_trim(ids[1], TrimRange(1_000_000, 3_000_000))
    inspected = tuple(MediaItem(item.source_path, item.taken_at, item.media_kind == "photo", False, item.date_source, source_duration_us=item.source_duration_us) for item in state.timeline.items)
    plan = apply_project_state(ExportPlan(_request(tmp_path), inspected), state)
    again = apply_project_state(ExportPlan(_request(tmp_path), inspected), state)
    assert plan.plan_id == again.plan_id and plan.items[0].path == state.timeline.items[1].source_path
    assert "trim=start=1:end=3,setpts=PTS-STARTPTS" in make_video_filter(plan.items[0], OverlayConfig(enabled=False))
    commands: list[list[str]] = []
    normalize_item(plan.items[0], tmp_path / "clip.mp4", "ffmpeg", OverlayConfig(enabled=False), 20, "fast", lambda argv, _context, **_kwargs: commands.append(argv))
    graph = commands[0][commands[0].index("-filter_complex") + 1]
    assert "atrim=start=1:end=3" not in graph  # no-audio source uses generated silence and -shortest
    with pytest.raises(ValueError, match="project preset snapshot"):
        replace_plan_overlay(plan, OverlayConfig(enabled=True))


def test_trimmed_preview_applies_in_point_once_in_filtergraph(tmp_path: Path) -> None:
    source = tmp_path / "preview.mp4"; source.write_bytes(b"source")
    destination = tmp_path / "preview.png"
    item = MediaItem(source, datetime(2024, 1, 1), False, False, "filename", trim_in_us=1_000_000, trim_out_us=3_000_000, trim_applied=True)
    commands: list[list[str]] = []
    def runner(argv: list[str], _context: str, **_kwargs: object):
        commands.append(argv); destination.write_bytes(b"png")
    render_overlay_preview(item, OverlayConfig(enabled=False), "ffmpeg", destination, runner)
    assert "-ss" not in commands[0]
    assert "trim=start=1:end=3,setpts=PTS-STARTPTS" in commands[0][commands[0].index("-vf") + 1]


def test_real_ffmpeg_trim_duration_within_one_target_frame_and_source_immutable(tmp_path: Path) -> None:
    ffmpeg = os.environ.get("VIDEO_CHRONICLE_FFMPEG") or shutil.which("ffmpeg")
    ffprobe = os.environ.get("VIDEO_CHRONICLE_FFPROBE") or shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("FFmpeg/FFprobe are not available")
    source = tmp_path / "trim source.mp4"; output = tmp_path / "trim output.mp4"
    subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=64x48:rate=60", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000", "-t", "1", "-c:v", "libx264", "-c:a", "aac", "-y", str(source)], check=True, timeout=60)
    before = (source.read_bytes(), source.stat().st_mtime_ns)
    item = MediaItem(source, datetime(2024, 1, 1), False, True, "filename", source_duration_us=1_000_000, trim_in_us=200_000, trim_out_us=700_000, trim_applied=True)
    def runner(argv: list[str], context: str, **kwargs: object):
        result = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        if result.returncode: raise RuntimeError(f"{context}: {result.stderr}")
        return result
    normalize_item(item, output, ffmpeg, OverlayConfig(enabled=False), 35, "ultrafast", runner)
    probe = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(output)], capture_output=True, text=True, check=True, timeout=30)
    actual_us = int(float(json.loads(probe.stdout)["format"]["duration"]) * 1_000_000)
    assert abs(actual_us - 500_000) <= 16_667
    assert (source.read_bytes(), source.stat().st_mtime_ns) == before


def test_gui_editor_mutation_invalidates_preview_and_export(qapp, tmp_path: Path) -> None:
    state = _state(tmp_path)
    items = tuple(MediaItem(item.source_path, item.taken_at, item.media_kind == "photo", False, item.date_source, source_duration_us=item.source_duration_us) for item in state.timeline.items)
    plan = ExportPlan(_request(tmp_path), items)
    adapter = ApplicationServiceAdapter(ports_factory=lambda: object())  # type: ignore[arg-type]
    window = ChronicleWindow(application_adapter=adapter)
    window._analyzed_plan = plan
    window._plan = plan
    window._populate_preview(plan)
    window._visual_preview_current = True
    window.run_button.setEnabled(True)
    window.preview_tree.topLevelItem(0).setSelected(True)
    window.trim_in_spin.setValue(100)
    window.trim_out_spin.setValue(900)
    window.trim_apply_button.click()
    qapp.processEvents()
    assert window._project_state is not None
    assert window._plan is not None and window._plan.plan_id is not None
    assert window._visual_preview_current is False
    assert window.run_button.isEnabled() is False
    assert "изменён" in window.preview_state_label.text().casefold()
    window.close()


def test_gui_partial_success_row_keeps_stable_project_item_binding(qapp, tmp_path: Path) -> None:
    state = _state(tmp_path)
    usable = state.timeline.items[1:]
    analyzed = ExportPlan(_request(tmp_path), tuple(MediaItem(item.source_path, item.taken_at, item.media_kind == "photo", False, item.date_source, source_duration_us=item.source_duration_us) for item in usable))
    edited = apply_project_state(analyzed, state)
    window = ChronicleWindow(application_adapter=ApplicationServiceAdapter(ports_factory=lambda: object()))  # type: ignore[arg-type]
    window._project_state = state
    window._analyzed_plan = analyzed
    window._plan = edited
    window._populate_preview(edited)
    window.preview_tree.topLevelItem(0).setSelected(True)
    qapp.processEvents()
    assert window._selected_item_ids() == (state.timeline.item_ids[1],)
    window.close()


def test_preview_rejects_source_replaced_after_analysis(qapp, tmp_path: Path) -> None:
    source = (tmp_path / "preview.mp4").absolute(); source.write_bytes(b"before")
    item = MediaItem(source, datetime(2024, 1, 1), False, False, "filename", source_fingerprint=SourceFingerprint.capture(source), source_duration_us=1_000_000)
    source.write_bytes(b"after!")
    ports = type("Ports", (), {"validate_source": staticmethod(lambda *_a: None), "command_runner": staticmethod(lambda *_a, **_k: None)})()
    adapter = ApplicationServiceAdapter(ports_factory=lambda: ports, preview_service=lambda *_a: pytest.fail("preview tool must not run"))
    outcomes: list[tuple[bool, str]] = []
    adapter.completed.connect(lambda _operation, success, message: outcomes.append((success, message)))
    adapter.start_preview(ExportPlan(_request(tmp_path), (item,)))
    deadline = time.monotonic() + 5
    while adapter.is_running and time.monotonic() < deadline:
        qapp.processEvents(); time.sleep(0.005)
    assert outcomes and outcomes[-1][0] is False
    assert "identity changed" in outcomes[-1][1]
