from __future__ import annotations

import os
import logging
import shutil
import subprocess
from dataclasses import FrozenInstanceError
from datetime import datetime
from pathlib import Path

import pytest

from video_chronicle import pipeline
from video_chronicle import overlay as overlay_module
from video_chronicle.application import execute_plan
from video_chronicle.domain import ExportPlan, ExportRequest, MediaItem
from video_chronicle.overlay import (
    DEFAULT_OVERLAY_CONFIG,
    OVERLAY_FORMATS,
    OVERLAY_POSITIONS,
    OverlayConfig,
    require_resolved_overlay_font,
    resolve_overlay_font,
)
from video_chronicle.ports import PipelinePorts


def _item(tmp_path: Path) -> MediaItem:
    return MediaItem(
        path=tmp_path / "семейное ' видео.mp4",
        taken_at=datetime(2024, 2, 29, 23, 59),
        is_photo=False,
        has_audio=True,
        date_source="fixture",
    )


def test_overlay_defaults_are_frozen_and_match_legacy_behavior() -> None:
    assert DEFAULT_OVERLAY_CONFIG == OverlayConfig()
    assert DEFAULT_OVERLAY_CONFIG.enabled is True
    assert DEFAULT_OVERLAY_CONFIG.format == "dd.MM.yy ddd"
    assert DEFAULT_OVERLAY_CONFIG.position == "bottom-left"
    assert (
        DEFAULT_OVERLAY_CONFIG.horizontal_margin,
        DEFAULT_OVERLAY_CONFIG.vertical_margin,
        DEFAULT_OVERLAY_CONFIG.font_size,
        DEFAULT_OVERLAY_CONFIG.text_color,
        DEFAULT_OVERLAY_CONFIG.outline_color,
        DEFAULT_OVERLAY_CONFIG.outline_width,
    ) == (20, 20, 72, "#000000", "#FFFFFF", 4)
    with pytest.raises(FrozenInstanceError):
        DEFAULT_OVERLAY_CONFIG.font_size = 20  # type: ignore[misc]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"format": "strftime"},
        {"position": "center"},
        {"horizontal_margin": -1},
        {"vertical_margin": 301},
        {"font_size": 11},
        {"font_size": 201},
        {"outline_width": 21},
        {"text_color": "black"},
        {"outline_color": "#FFFFFG"},
    ],
)
def test_overlay_rejects_values_outside_approved_presets(kwargs) -> None:
    with pytest.raises(ValueError, match="overlay|unsupported"):
        OverlayConfig(**kwargs)


def test_font_policy_rejects_missing_or_unsupported_and_requires_fallback(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="does not exist"):
        OverlayConfig(font_file=tmp_path / "missing.ttf")
    unsupported = tmp_path / "font.woff"
    unsupported.write_bytes(b"font")
    with pytest.raises(ValueError, match="ttf or .otf"):
        OverlayConfig(font_file=unsupported)
    with pytest.raises(RuntimeError, match="No supported overlay font"):
        resolve_overlay_font(OverlayConfig(), None)
    assert resolve_overlay_font(OverlayConfig(enabled=False), None).font_file is None


def test_font_identity_is_rechecked_and_size_is_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    font = tmp_path / "trusted.ttf"
    font.write_bytes(b"font-v1")
    config = OverlayConfig(font_file=font)
    font.write_bytes(b"font-v2-with-different-size")
    with pytest.raises(RuntimeError, match="changed after validation"):
        require_resolved_overlay_font(config)

    oversized = tmp_path / "oversized.otf"
    oversized.write_bytes(b"12")
    monkeypatch.setattr(overlay_module, "MAX_FONT_BYTES", 1)
    with pytest.raises(ValueError, match="MiB limit"):
        OverlayConfig(font_file=oversized)


def test_font_policy_rejects_symlink_or_reparse_point(tmp_path: Path) -> None:
    target = tmp_path / "target.ttf"
    target.write_bytes(b"font")
    link = tmp_path / "alias.ttf"
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")
    with pytest.raises(ValueError, match="symlink or reparse"):
        OverlayConfig(font_file=link)


def test_font_policy_rejects_unc_paths_before_filesystem_access() -> None:
    with pytest.raises(ValueError, match="UNC"):
        OverlayConfig(font_file=Path(r"\\server\share\font.ttf"))


@pytest.mark.parametrize(
    ("format_name", "expected_text"),
    tuple(zip(
        OVERLAY_FORMATS,
        ("29.02.24 Чт", "29.02.2024", r"29.02.2024 23\:59"),
        strict=True,
    )),
)
@pytest.mark.parametrize(
    ("position", "expected_xy"),
    [
        ("top-left", ("x=13", "y=17")),
        ("top-right", ("x=w-text_w-13", "y=17")),
        ("bottom-left", ("x=13", "y=h-text_h-17")),
        ("bottom-right", ("x=w-text_w-13", "y=h-text_h-17")),
    ],
)
def test_filter_golden_formats_positions_and_unicode_font_path(
    tmp_path: Path, format_name: str, expected_text: str, position: str, expected_xy
) -> None:
    font = tmp_path / "шрифт ' test.ttf"
    font.write_bytes(b"fixture")
    config = OverlayConfig(
        format=format_name,  # type: ignore[arg-type]
        position=position,  # type: ignore[arg-type]
        horizontal_margin=13,
        vertical_margin=17,
        font_size=48,
        text_color="#102030",
        outline_color="#F0E0D0",
        outline_width=3,
        font_file=font,
    )

    result = pipeline.make_video_filter(_item(tmp_path), config)

    assert result.count("drawtext=") == 1
    assert f"text='{expected_text}'" in result
    assert all(fragment in result for fragment in expected_xy)
    assert "fontcolor=#102030:bordercolor=#F0E0D0:borderw=3:fontsize=48" in result
    assert r"шрифт \\\' test.ttf" in result


def test_disabled_overlay_removes_drawtext_without_changing_base_pipeline(
    tmp_path: Path,
) -> None:
    result = pipeline.make_video_filter(_item(tmp_path), OverlayConfig(enabled=False))
    assert "drawtext" not in result
    assert "scale=1600:900" in result
    assert "fps=60" in result


def test_preview_adapter_uses_list_argv_and_the_same_config(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "preview.png"
    config = OverlayConfig(enabled=False)
    calls: list[tuple[list[str], str, dict[str, object]]] = []

    def runner(command, context, **kwargs):
        calls.append((command, context, kwargs))
        destination.write_bytes(b"png")
        return subprocess.CompletedProcess(command, 0, "", "")

    pipeline.render_overlay_preview(
        _item(tmp_path), config, "trusted ffmpeg", destination, runner
    )

    command, context, kwargs = calls[0]
    assert isinstance(command, list)
    assert command[0] == "trusted ffmpeg"
    assert str(_item(tmp_path).path) in command
    assert command[-1] == str(destination)
    assert "drawtext" not in command[command.index("-vf") + 1]
    assert kwargs == {"timeout": 60}
    assert "FFmpeg preview failed" in context


def test_synthetic_multi_item_export_uses_the_exact_previewed_config(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    sources = [input_dir / "first.mp4", input_dir / "second.mp4"]
    for source in sources:
        source.write_bytes(b"source")
    output = tmp_path / "result.mp4"
    workspace = tmp_path / "work"
    workspace.mkdir()
    overlay = OverlayConfig(enabled=False, position="top-right")
    request = ExportRequest(
        input_dir=input_dir,
        output=output,
        error_log=tmp_path / "errors.log",
        ffmpeg="ffmpeg",
        ffprobe="ffprobe",
        crf=20,
        preset="medium",
        overwrite=False,
        keep_work=False,
        overlay=overlay,
    )
    items = tuple(
        MediaItem(path, datetime(2024, 1, index), False, True, "fixture")
        for index, path in enumerate(sources, start=1)
    )
    received: list[OverlayConfig] = []

    def normalize(item, destination, ffmpeg, config, crf, preset, runner):
        received.append(config)
        destination.write_bytes(b"clip")

    def concatenate(clips, concat_file, temporary_output, ffmpeg, runner):
        temporary_output.write_bytes(b"movie")

    def publish(temporary_output, destination, overwrite):
        destination.write_bytes(temporary_output.read_bytes())

    ports = PipelinePorts(
        command_runner=lambda *args, **kwargs: None,
        probe_media=lambda *args, **kwargs: {},
        inspect_item=lambda *args, **kwargs: items[0],
        normalize_item=normalize,
        concatenate=concatenate,
        publish_output=publish,
        collect_source_paths=lambda *args: list(sources),
        create_workspace=lambda parent: workspace,
        cleanup_workspace=lambda path: __import__("shutil").rmtree(path),
        validate_source=lambda input_path, source: None,
    )

    result = execute_plan(ExportPlan(request=request, items=items), logging.getLogger(__name__), ports)

    assert result == 0
    assert output.read_bytes() == b"movie"
    assert received == [overlay, overlay]
    assert all(config is overlay for config in received)


def test_photo_tool_boundaries_disable_image_sequence_expansion(tmp_path: Path) -> None:
    source = tmp_path / "album%03d" / "frame%03d.jpg"
    source.parent.mkdir()
    source.write_bytes(b"literal")
    destination = tmp_path / "preview.png"
    commands: list[list[str]] = []

    def probe_runner(command, context, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, '{"streams": []}', "")

    pipeline.probe_media(source, "ffprobe", probe_runner)

    def media_runner(command, context, **kwargs):
        commands.append(command)
        if command[-1] == str(destination):
            destination.write_bytes(b"png")
        return subprocess.CompletedProcess(command, 0, "", "")

    item = MediaItem(source, datetime(2024, 2, 29), True, False, "fixture")
    disabled = OverlayConfig(enabled=False)
    pipeline.normalize_item(
        item, tmp_path / "clip.mp4", "ffmpeg", disabled, 20, "medium", media_runner
    )
    pipeline.render_overlay_preview(
        item, disabled, "ffmpeg", destination, media_runner
    )

    assert len(commands) == 3
    assert commands[0][-1] == str(source)
    assert commands[0][-5:-1] == ["-f", "image2", "-pattern_type", "none"]
    for command in commands[1:]:
        input_index = command.index("-i")
        format_index = command.index("-f")
        assert command[format_index : format_index + 4] == [
            "-f",
            "image2",
            "-pattern_type",
            "none",
        ]
        assert format_index < input_index
        assert command[input_index + 1] == str(source)


def _resolve_smoke_tool(environment_name: str, command: str) -> str | None:
    configured = os.environ.get(environment_name)
    if configured and Path(configured).is_file():
        return str(Path(configured).resolve())
    return shutil.which(command)


def test_real_ffmpeg_preview_overlay_on_and_off(tmp_path: Path) -> None:
    ffmpeg = _resolve_smoke_tool("VIDEO_CHRONICLE_FFMPEG", "ffmpeg")
    font = pipeline.find_default_font()
    if ffmpeg is None or font is None:
        pytest.skip("FFmpeg or verified system font is unavailable")
    source = tmp_path / "IMG_20240229_235900.bmp"
    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=64x48",
            "-frames:v",
            "1",
            "-y",
            str(source),
        ],
        check=True,
        timeout=60,
    )
    item = MediaItem(source, datetime(2024, 2, 29, 23, 59), True, False, "fixture")
    enabled_png = tmp_path / "enabled.png"
    disabled_png = tmp_path / "disabled.png"
    pipeline.render_overlay_preview(
        item, OverlayConfig(font_file=font), ffmpeg, enabled_png
    )
    pipeline.render_overlay_preview(
        item, OverlayConfig(enabled=False), ffmpeg, disabled_png
    )
    assert enabled_png.read_bytes() != disabled_png.read_bytes()


def test_real_ffmpeg_preview_accepts_apostrophe_in_font_path(tmp_path: Path) -> None:
    ffmpeg = _resolve_smoke_tool("VIDEO_CHRONICLE_FFMPEG", "ffmpeg")
    system_font = pipeline.find_default_font()
    if ffmpeg is None or system_font is None:
        pytest.skip("FFmpeg or verified system font is unavailable")
    font = tmp_path / "font's test.ttf"
    shutil.copy2(system_font, font)
    source = tmp_path / "IMG_20240229_235900.bmp"
    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=64x48",
            "-frames:v",
            "1",
            "-y",
            str(source),
        ],
        check=True,
        timeout=60,
    )
    destination = tmp_path / "apostrophe-font.png"
    item = MediaItem(source, datetime(2024, 2, 29, 23, 59), True, False, "fixture")

    pipeline.render_overlay_preview(
        item, OverlayConfig(font_file=font), ffmpeg, destination
    )

    assert destination.stat().st_size > 0


def test_real_ffmpeg_normalize_uses_overlay_on_and_off(tmp_path: Path) -> None:
    ffmpeg = _resolve_smoke_tool("VIDEO_CHRONICLE_FFMPEG", "ffmpeg")
    system_font = pipeline.find_default_font()
    if ffmpeg is None or system_font is None:
        pytest.skip("FFmpeg or verified system font is unavailable")
    font = tmp_path / "export font's copy.ttf"
    shutil.copy2(system_font, font)
    source = tmp_path / "IMG_20240229_235900.bmp"
    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=320x180",
            "-frames:v",
            "1",
            "-y",
            str(source),
        ],
        check=True,
        timeout=60,
    )
    item = MediaItem(source, datetime(2024, 2, 29, 23, 59), True, False, "fixture")
    enabled_mp4 = tmp_path / "enabled.mp4"
    disabled_mp4 = tmp_path / "disabled.mp4"
    pipeline.normalize_item(
        item,
        enabled_mp4,
        ffmpeg,
        OverlayConfig(font_file=font),
        28,
        "ultrafast",
    )
    pipeline.normalize_item(
        item,
        disabled_mp4,
        ffmpeg,
        OverlayConfig(enabled=False),
        28,
        "ultrafast",
    )
    enabled_png = tmp_path / "enabled-frame.png"
    disabled_png = tmp_path / "disabled-frame.png"
    for media, frame in ((enabled_mp4, enabled_png), (disabled_mp4, disabled_png)):
        subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(media),
                "-frames:v",
                "1",
                "-y",
                str(frame),
            ],
            check=True,
            timeout=60,
        )
    assert enabled_png.read_bytes() != disabled_png.read_bytes()
