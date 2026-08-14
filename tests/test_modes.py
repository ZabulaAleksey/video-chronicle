from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import pytest

from video_chronicle import cli, pipeline
from video_chronicle.application import execute_plan, plan_export
from video_chronicle.domain import ExportMode, ExportPlan, ExportRequest, MediaItem
from video_chronicle.overlay import OverlayConfig
from video_chronicle.ports import PipelinePorts


def _request(tmp_path: Path, mode: ExportMode, overlay: OverlayConfig) -> ExportRequest:
    source = tmp_path / "input"
    source.mkdir(parents=True, exist_ok=True)
    return ExportRequest(
        input_dir=source,
        output=tmp_path / "output.mp4",
        error_log=tmp_path / "errors.log",
        ffmpeg="ffmpeg",
        ffprobe="ffprobe",
        crf=20,
        preset="medium",
        overwrite=False,
        keep_work=False,
        overlay=overlay,
        mode=mode,
    )


@pytest.mark.parametrize("is_photo", [False, True], ids=["video", "photo"])
@pytest.mark.parametrize("enabled", [False, True], ids=["overlay-off", "overlay-on"])
@pytest.mark.parametrize("mode", list(ExportMode), ids=lambda mode: mode.value)
def test_mode_overlay_media_matrix(
    tmp_path: Path, mode: ExportMode, enabled: bool, is_photo: bool
) -> None:
    overlay = OverlayConfig(enabled=enabled)
    if mode is ExportMode.JOIN and enabled:
        with pytest.raises(ValueError, match="Join mode"):
            _request(tmp_path, mode, overlay)
        return

    request = _request(tmp_path, mode, overlay)
    item = MediaItem(
        path=request.input_dir / ("photo.jpg" if is_photo else "video.mp4"),
        taken_at=datetime(2024, 1, 2, 3, 4, 5),
        is_photo=is_photo,
        has_audio=not is_photo,
        date_source="filename",
    )
    filtergraph = pipeline.make_video_filter(item, request.overlay)
    assert ("drawtext=" in filtergraph) is enabled


def test_mode_is_part_of_request_and_plan_determinism(tmp_path: Path) -> None:
    disabled = OverlayConfig(enabled=False)
    chronicle = _request(tmp_path, ExportMode.CHRONICLE, disabled)
    joined = _request(tmp_path, ExportMode.JOIN, disabled)
    item = MediaItem(
        path=chronicle.input_dir / "clip.mp4",
        taken_at=datetime(2024, 1, 1),
        is_photo=False,
        has_audio=True,
        date_source="filename",
    )
    assert chronicle != joined
    assert ExportPlan(chronicle, (item,)) == ExportPlan(chronicle, (item,))
    assert ExportPlan(chronicle, (item,)) != ExportPlan(joined, (item,))


def test_both_modes_execute_the_same_mixed_media_ports(tmp_path: Path) -> None:
    calls: dict[ExportMode, list[tuple[bool, bool]]] = {}
    for mode in ExportMode:
        request = _request(tmp_path / mode.value, mode, OverlayConfig(enabled=False))
        items = tuple(
            MediaItem(
                path=request.input_dir / name,
                taken_at=datetime(2024, 1, index),
                is_photo=is_photo,
                has_audio=not is_photo,
                date_source="filename",
            )
            for index, (name, is_photo) in enumerate(
                (("photo.jpg", True), ("video.mp4", False)), start=1
            )
        )
        work = tmp_path / f"work-{mode.value}"
        normalized: list[tuple[bool, bool]] = []

        def normalize(item, destination, ffmpeg, overlay, crf, preset, runner):
            normalized.append((item.is_photo, overlay.enabled))

        ports = PipelinePorts(
            command_runner=lambda *args, **kwargs: None,
            probe_media=lambda *args: {},
            inspect_item=lambda *args: items[0],
            normalize_item=normalize,
            concatenate=lambda *args: None,
            publish_output=lambda *args: None,
            collect_source_paths=lambda *args: [],
            create_workspace=lambda parent: work,
            cleanup_workspace=lambda path: None,
            validate_source=lambda *args: None,
        )
        execute_plan(ExportPlan(request, items), logging.getLogger(__name__), ports)
        calls[mode] = normalized

    assert calls[ExportMode.JOIN] == calls[ExportMode.CHRONICLE] == [
        (True, False),
        (False, False),
    ]


def test_cli_default_and_explicit_chronicle_are_equal(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "input"
    source.mkdir()
    font = tmp_path / "font.ttf"
    font.write_bytes(b"font")
    monkeypatch.setattr(pipeline, "resolve_executable", lambda value, label: value)
    monkeypatch.setattr(pipeline, "find_default_font", lambda: font)
    base = ["--input-dir", str(source), "--output", str(tmp_path / "out.mp4")]

    implicit = cli._build_request(cli.parse_args(base))
    explicit = cli._build_request(cli.parse_args([*base, "--mode", "chronicle"]))

    assert implicit == explicit
    assert implicit.mode is ExportMode.CHRONICLE
    assert implicit.overlay.enabled is True


def test_cli_join_disables_overlay_and_rejects_explicit_font(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "input"
    source.mkdir()
    font = tmp_path / "font.ttf"
    font.write_bytes(b"font")
    monkeypatch.setattr(pipeline, "resolve_executable", lambda value, label: value)
    monkeypatch.setattr(pipeline, "find_default_font", lambda: font)
    base = [
        "--input-dir", str(source), "--output", str(tmp_path / "out.mp4"),
        "--mode", "join",
    ]

    request = cli._build_request(cli.parse_args(base))
    assert request.mode is ExportMode.JOIN
    assert request.overlay.enabled is False
    with pytest.raises(RuntimeError, match="--font-file"):
        cli._build_request(cli.parse_args([*base, "--font-file", str(font)]))
