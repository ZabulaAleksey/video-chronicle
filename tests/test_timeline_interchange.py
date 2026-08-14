from __future__ import annotations

import builtins
from datetime import datetime
import json
from pathlib import Path
import subprocess
import sys

import pytest

from video_chronicle.application import experimental_timeline_interchange
from video_chronicle.interchange import (
    ImportResult,
    InterchangeClip,
    InterchangeTimeline,
    ProposedClip,
    apply_import_proposal,
    optional_otio_adapter,
)
from video_chronicle.project import (
    ProjectState,
    RenderPreset,
    RenderSettings,
    Timeline,
    TimelineItem,
    stable_item_id,
)


def _adapter():
    pytest.importorskip("opentimelineio")
    from video_chronicle.otio_adapter import NativeOtioAdapter

    return NativeOtioAdapter()


def _project(tmp_path: Path, count: int = 2) -> ProjectState:
    items = []
    for index in range(count):
        path = (tmp_path / f"source-{index}.mp4").resolve()
        path.write_bytes(bytes([index]) + b"media")
        items.append(
            TimelineItem(
                stable_item_id(path),
                path,
                datetime(2026, 1, 1, 12, index),
                "filename",
                media_kind="video",
                source_duration_us=2_000_000 + index,
            )
        )
    timeline = Timeline.build(items)
    preset = RenderPreset("default", 1, "Default", RenderSettings())
    return ProjectState(
        "project-interop",
        timeline,
        presets=(preset,),
        active_preset=preset.ref,
    )


@pytest.mark.parametrize("count", [0, 1, 4096])
def test_native_otio_golden_round_trip_preserves_order_ids_paths_and_microseconds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, count: int
) -> None:
    adapter = _adapter()
    root = tmp_path.resolve()
    clips = tuple(
        InterchangeClip(
            f"item-{index}", root / f"s{index}.mp4", index, index + 16_667
        )
        for index in range(count)
    )
    timeline = InterchangeTimeline("project-golden", 7, clips)
    if count == 4096:
        from video_chronicle import otio_adapter

        monkeypatch.setattr(
            otio_adapter,
            "_safe_existing_identity",
            lambda path: str(path).casefold(),
        )
    else:
        for clip in clips:
            clip.source_path.write_bytes(b"x")
    encoded = adapter.export_timeline(timeline)
    assert len(encoded) <= 32 * 1024 * 1024
    imported = adapter.import_timeline(encoded, timeline)
    assert imported.is_fully_mapped
    assert tuple(
        (clip.item_id, clip.source_path, clip.in_us, clip.out_us)
        for clip in imported.clips
    ) == tuple(
        (clip.item_id, clip.source_path, clip.in_us, clip.out_us)
        for clip in clips
    )
    reexport = adapter.export_timeline(
        InterchangeTimeline(
            imported.project_id,
            imported.project_revision,
            tuple(
                InterchangeClip(
                    clip.item_id or "", clip.source_path, clip.in_us, clip.out_us, clip.group_id
                )
                for clip in imported.clips
            ),
        )
    )
    assert json.loads(reexport) == json.loads(encoded)


@pytest.mark.parametrize("rate", [24, 25, 30000 / 1001, 60, 1_000_000])
def test_otio_import_has_explicit_rational_time_to_microsecond_contract(
    tmp_path: Path, rate: float
) -> None:
    adapter = _adapter()
    path = (tmp_path / "source.mp4").resolve()
    path.write_bytes(b"media")
    known = InterchangeTimeline(
        "project-timebase", 2, (InterchangeClip("item-1", path, 0, 1_000_000),)
    )
    document = json.loads(adapter.export_timeline(known))
    clip = document["tracks"]["children"][0]["children"][0]
    clip["source_range"]["start_time"] = {
        "OTIO_SCHEMA": "RationalTime.1",
        "rate": rate,
        "value": rate,
    }
    clip["source_range"]["duration"] = {
        "OTIO_SCHEMA": "RationalTime.1",
        "rate": rate,
        "value": rate * 2,
    }
    result = adapter.import_timeline(
        json.dumps(document, separators=(",", ":")).encode(), known
    )
    assert (result.clips[0].in_us, result.clips[0].out_us) == (1_000_000, 3_000_000)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.update({"unexpected": True}),
        lambda value: value["tracks"]["children"].append(value["tracks"]["children"][0]),
        lambda value: value["tracks"]["children"][0].update({"kind": "Audio"}),
        lambda value: value["tracks"]["children"][0]["children"][0].update({"effects": [{"OTIO_SCHEMA": "Effect.1"}]}),
        lambda value: value["tracks"]["children"][0]["children"][0]["source_range"]["duration"].update({"value": -1}),
    ],
)
def test_otio_forbidden_schema_fields_paths_and_bounds_fail_before_path_io(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation
) -> None:
    adapter = _adapter()
    path = (tmp_path / "source.mp4").resolve()
    path.write_bytes(b"media")
    known = InterchangeTimeline("project-negative", 0, (InterchangeClip("item-1", path, 0, 1_000_000),))
    document = json.loads(adapter.export_timeline(known))
    mutation(document)
    from video_chronicle import otio_adapter

    touched = False

    def forbidden_io(_path: Path) -> str:
        nonlocal touched
        touched = True
        raise AssertionError("path I/O occurred before structural rejection")

    monkeypatch.setattr(otio_adapter, "_safe_existing_identity", forbidden_io)
    with pytest.raises(otio_adapter.InterchangeError):
        adapter.import_timeline(json.dumps(document).encode(), known)
    assert not touched


def test_otio_remote_reference_is_rejected_without_project_mutation(tmp_path: Path) -> None:
    adapter = _adapter()
    path = (tmp_path / "source.mp4").resolve()
    path.write_bytes(b"media")
    known = InterchangeTimeline("project-remote", 0, (InterchangeClip("item-1", path, 0, 1_000_000),))
    document = json.loads(adapter.export_timeline(known))
    document["tracks"]["children"][0]["children"][0]["media_references"]["DEFAULT_MEDIA"]["target_url"] = "https://example.invalid/a.mp4"
    with pytest.raises(ValueError, match="local file"):
        adapter.import_timeline(json.dumps(document).encode(), known)
    assert known.clips[0].source_path.read_bytes() == b"media"


def test_otio_absolute_file_reference_with_traversal_is_rejected(tmp_path: Path) -> None:
    adapter = _adapter()
    path = (tmp_path / "source.mp4").resolve()
    path.write_bytes(b"media")
    known = InterchangeTimeline("project-traversal", 0, (InterchangeClip("item-1", path, 0, 1_000_000),))
    document = json.loads(adapter.export_timeline(known))
    reference = document["tracks"]["children"][0]["children"][0]["media_references"]["DEFAULT_MEDIA"]
    reference["target_url"] = (tmp_path / "unused" / ".." / path.name).as_uri()
    with pytest.raises(ValueError, match="traversal"):
        adapter.import_timeline(json.dumps(document).encode(), known)


def test_otio_double_encoded_traversal_is_not_decoded_twice(tmp_path: Path) -> None:
    adapter = _adapter()
    path = (tmp_path / "secret.mp4").resolve()
    path.write_bytes(b"media")
    known = InterchangeTimeline("project-double-encoded", 0, (InterchangeClip("item-1", path, 0, 1_000_000),))
    document = json.loads(adapter.export_timeline(known))
    reference = document["tracks"]["children"][0]["children"][0]["media_references"]["DEFAULT_MEDIA"]
    reference["target_url"] = (tmp_path / "safe").as_uri() + "/%252e%252e/secret.mp4"
    with pytest.raises(ValueError, match="encoded traversal"):
        adapter.import_timeline(json.dumps(document).encode(), known)


def test_otio_native_core_codec_bypasses_ambient_adapter_manifest_and_hooks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = _adapter()
    path = (tmp_path / "source.mp4").resolve()
    path.write_bytes(b"media")
    known = InterchangeTimeline("project-no-plugins", 0, (InterchangeClip("item-1", path, 0, 1_000_000),))
    otio = adapter._otio

    def hostile(*_args, **_kwargs):
        raise AssertionError("ambient OTIO adapter/plugin dispatch executed")

    monkeypatch.setattr(otio.adapters, "write_to_string", hostile)
    monkeypatch.setattr(otio.adapters, "read_from_string", hostile)
    monkeypatch.setattr(otio.plugins, "ActiveManifest", hostile)
    encoded = adapter.export_timeline(known)
    imported = adapter.import_timeline(encoded, known)
    assert imported.clips[0].item_id == "item-1"


def test_otio_json_resource_limits_and_non_finite_numbers_are_rejected(tmp_path: Path) -> None:
    adapter = _adapter()
    path = (tmp_path / "source.mp4").resolve()
    path.write_bytes(b"media")
    known = InterchangeTimeline("project-limits", 0, (InterchangeClip("item-1", path, 0, 1_000_000),))
    valid = adapter.export_timeline(known)
    with pytest.raises(ValueError, match="32 MiB"):
        adapter.import_timeline(b" " * (32 * 1024 * 1024 + 1), known)
    with pytest.raises(ValueError, match="non-finite"):
        adapter.import_timeline(valid.replace(b'"value":0.0', b'"value":NaN', 1), known)
    document = json.loads(valid)
    document["metadata"] = {"foreign": {"x": "y" * (64 * 1024)}}
    with pytest.raises(ValueError, match="exceeds"):
        adapter.import_timeline(json.dumps(document).encode(), known)
    document = json.loads(valid)
    nested: object = "leaf"
    for _ in range(33):
        nested = {"nested": nested}
    document["metadata"] = {"foreign": nested}
    with pytest.raises(ValueError, match="depth"):
        adapter.import_timeline(json.dumps(document).encode(), known)
    document = json.loads(valid)
    original_clip = document["tracks"]["children"][0]["children"][0]
    clips = []
    for clip_index in range(300):
        clip = json.loads(json.dumps(original_clip))
        clip["name"] = f"clip-{clip_index}"
        clip["metadata"] = {
            "foreign": {f"key-{entry}": entry for entry in range(1023)}
        }
        clips.append(clip)
    document["tracks"]["children"][0]["children"] = clips
    with pytest.raises(ValueError, match="262144 nodes"):
        adapter.import_timeline(json.dumps(document).encode(), known)


def test_foreign_otio_exact_path_binding_and_ambiguous_identity_warning(tmp_path: Path) -> None:
    adapter = _adapter()
    path = (tmp_path / "source.mp4").resolve()
    path.write_bytes(b"media")
    original = InterchangeTimeline("foreign", 99, (InterchangeClip("foreign-item", path, 0, 1_000_000),))
    document = json.loads(adapter.export_timeline(original))
    document["metadata"] = {}
    document["tracks"]["children"][0]["children"][0]["metadata"] = {"foreign": {"kept": False}}
    known = InterchangeTimeline("local", 3, (InterchangeClip("local-item", path, 0, 1_000_000),))
    result = adapter.import_timeline(json.dumps(document).encode(), known)
    assert result.clips[0].item_id == "local-item"
    assert any("foreign metadata" in warning for warning in result.warnings)
    duplicate = InterchangeTimeline(
        "local",
        3,
        (
            InterchangeClip("local-a", path, 0, 1_000_000),
            InterchangeClip("local-b", path, 0, 1_000_000),
        ),
    )
    ambiguous = adapter.import_timeline(json.dumps(document).encode(), duplicate)
    assert ambiguous.clips[0].item_id is None
    assert any("ambiguous" in warning for warning in ambiguous.warnings)


def test_import_is_proposal_only_and_explicit_apply_invalidates_plan(tmp_path: Path) -> None:
    project = _project(tmp_path)
    assert project.layout is not None
    original = project
    ordered = tuple(reversed(project.layout.entries))
    proposal = ImportResult(
        project.project_id,
        project.revision,
        tuple(
            ProposedClip(
                next(item.source_path for item in project.timeline.items if item.stable_id == entry.item_id),
                0,
                next(item.source_duration_us for item in project.timeline.items if item.stable_id == entry.item_id) or 0,
                entry.item_id,
            )
            for entry in ordered
        ),
    )
    assert project == original
    applied = apply_import_proposal(project, proposal)
    assert applied.revision == project.revision + 1
    assert tuple(entry.item_id for entry in applied.layout.entries) == tuple(entry.item_id for entry in ordered)
    assert applied.current_plan is None
    assert project == original
    with pytest.raises(ValueError, match="stale"):
        apply_import_proposal(applied, proposal)
    partial = ImportResult(project.project_id, project.revision, (ProposedClip(project.timeline.items[0].source_path, 0, 1_000_000),))
    with pytest.raises(ValueError, match="unmapped"):
        apply_import_proposal(project, partial)
    assert project == original


def test_optional_flag_default_and_missing_dependency_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    assert optional_otio_adapter({}).available is False
    assert experimental_timeline_interchange({}).available is False
    real_import = builtins.__import__

    def missing(name, *args, **kwargs):
        if name == "opentimelineio":
            raise ModuleNotFoundError("missing", name="opentimelineio")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", missing)
    feature = optional_otio_adapter({"VIDEO_CHRONICLE_EXPERIMENTAL_OTIO": "1"})
    assert feature.available is False
    assert "not installed" in feature.reason


def test_core_import_graph_does_not_load_otio() -> None:
    command = [
        sys.executable,
        "-c",
        "import sys; sys.path.insert(0, 'src'); import video_chronicle.project, video_chronicle.interchange; assert 'opentimelineio' not in sys.modules",
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


def test_optional_extra_is_exactly_pinned_and_not_a_default_dependency() -> None:
    import tomllib

    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["optional-dependencies"]["otio"] == ["opentimelineio==0.18.1"]
    assert all("opentimelineio" not in dependency for dependency in project["dependencies"])
