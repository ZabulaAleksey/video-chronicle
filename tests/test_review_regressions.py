from __future__ import annotations

import stat
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytest

from video_chronicle import cli, pipeline
from video_chronicle.domain import ExportMode
from video_chronicle.overlay import OverlayConfig
from video_chronicle.project import (
    EditingClipSnapshot, EditingExportSnapshot, ExportPlanSnapshot, ProjectState,
    RenderPreset, RenderSettings, ResolvedTrim, Timeline, TimelineItem, stable_item_id,
)
from video_chronicle.repository import JsonProjectRepository
from video_chronicle.serialization import (
    ProjectSerializationError, project_from_mapping, project_to_mapping,
)


@pytest.mark.parametrize("boundary", ["output", "error-log", "default-error-log"])
def test_cli_reparse_rejected_before_resolve_or_log_open(tmp_path, monkeypatch, boundary):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    output = tmp_path / "out.mp4"
    log = tmp_path / "errors.log"
    victim = tmp_path / "victim"
    victim.write_bytes(b"must survive")
    guarded = output if boundary == "output" else log
    guarded.write_bytes(b"original")
    original_lstat = Path.lstat
    original_resolve = Path.resolve
    opened = []

    def fake_lstat(path):
        value = original_lstat(path)
        if path == guarded:
            class Reparse:
                st_mode = value.st_mode
                st_file_attributes = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024)
            return Reparse()
        return value

    def fake_resolve(path, *args, **kwargs):
        if path == guarded:
            return victim
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", fake_lstat)
    monkeypatch.setattr(Path, "resolve", fake_resolve)
    monkeypatch.setattr(pipeline, "configure_logging", lambda path: opened.append(path))
    args = ["--input-dir", str(inputs), "--output", str(output), "--mode", "join"]
    if boundary != "default-error-log":
        args += ["--error-log", str(log)]
    assert cli.main(args) == 1
    assert opened == []
    assert victim.read_bytes() == b"must survive"
    assert guarded.read_bytes() == b"original"


@pytest.mark.parametrize("project_id", ["CON", "nul", "COM1", "LPT1", "aux.txt", "project.", "project "])
def test_durable_project_ids_reject_device_and_normalization_aliases(tmp_path, project_id):
    repository = JsonProjectRepository(tmp_path / "projects")
    with pytest.raises(ValueError):
        repository.get(project_id)
    assert list(repository.root.iterdir()) == []


def state_with_snapshot(tmp_path, *, editing):
    source = (tmp_path / "source.mp4").absolute()
    source.write_bytes(b"source")
    item = TimelineItem(stable_item_id(source), source, datetime(2024, 1, 1), "filename", media_kind="video", source_duration_us=1_000_000)
    timeline = Timeline.build((item,))
    output = (tmp_path / "output.mp4").absolute()
    settings = RenderSettings(ExportMode.JOIN, OverlayConfig(enabled=False), 20, "fast")
    preset = RenderPreset("preset", 1, "Preset", settings)
    if not editing:
        plan = ExportPlanSnapshot.create(timeline, output, crf=20, preset="fast", overwrite=False)
        return ProjectState("project", timeline, current_plan=plan, presets=(preset,), active_preset=preset.ref)
    plan = EditingExportSnapshot.create(project_id="project", project_revision=0, clips=(EditingClipSnapshot(item.stable_id, ResolvedTrim(0, 1_000_000), None),), groups=(), preset_ref=preset.ref, settings=settings, output_path=output, overwrite=False)
    return ProjectState("project", timeline, current_plan=plan, presets=(preset,), active_preset=preset.ref)


@pytest.mark.parametrize("version", [True, False, 1.0, 2.0])
def test_snapshot_version_requires_integer(tmp_path, version):
    payload = project_to_mapping(state_with_snapshot(tmp_path, editing=False), force_v2=True)
    payload["project"]["current_plan"]["snapshot_version"] = version
    with pytest.raises(ProjectSerializationError):
        project_from_mapping(payload)


@pytest.mark.parametrize("mismatch", ["project", "future-revision"])
def test_editing_snapshot_cannot_belong_to_another_project_or_future(tmp_path, mismatch):
    payload = project_to_mapping(state_with_snapshot(tmp_path, editing=True), force_v2=True)
    snapshot = payload["project"]["current_plan"]["snapshot"]
    if mismatch == "project":
        snapshot["project_id"] = "another"
    else:
        snapshot["project_revision"] = 1
    # Recompute the content-derived ID, so rejection proves the outer binding.
    original = state_with_snapshot(tmp_path, editing=True).current_plan
    new_plan = EditingExportSnapshot.create(project_id=snapshot["project_id"], project_revision=snapshot["project_revision"], clips=original.clips, groups=original.groups, preset_ref=original.preset_ref, settings=original.settings, output_path=original.output_path, overwrite=original.overwrite)
    snapshot["plan_id"] = new_plan.plan_id
    with pytest.raises(ProjectSerializationError):
        project_from_mapping(payload)


def test_durable_save_preserves_earlier_immutable_snapshot_revision(tmp_path):
    state = state_with_snapshot(tmp_path, editing=True)
    repository = JsonProjectRepository(tmp_path / "projects")
    saved = repository.save(state, expected_revision=0)
    assert saved.revision == 1 and saved.current_plan.project_revision == 0
    assert repository.get(state.project_id) == saved
