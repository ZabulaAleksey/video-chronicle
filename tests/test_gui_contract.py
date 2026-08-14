from __future__ import annotations

from pathlib import Path

import pytest

from gui_contract import (
    RequestValidationError,
    build_cli_arguments,
    create_run_request,
)
from video_chronicle.domain import ExportMode
from video_chronicle.overlay import OverlayConfig


def test_build_cli_arguments_keeps_unicode_paths_as_single_values(tmp_path: Path) -> None:
    input_dir = tmp_path / "медиа folder"
    input_dir.mkdir()
    output = tmp_path / "итоговый фильм.mp4"
    request = create_run_request(
        input_dir_text=str(input_dir),
        output_text=str(output),
        ffmpeg_text=str(tmp_path / "tools folder" / "ffmpeg.exe"),
        ffprobe_text="ffprobe",
        crf=19,
        preset_text="slow",
        overwrite=True,
    )

    arguments = build_cli_arguments(request, tmp_path / "join_media.py")

    assert arguments[arguments.index("--input-dir") + 1] == str(input_dir.resolve())
    assert arguments[arguments.index("--output") + 1] == str(output.resolve())
    assert arguments[arguments.index("--ffmpeg") + 1] == str(
        tmp_path / "tools folder" / "ffmpeg.exe"
    )
    assert arguments[-1] == "--overwrite"
    assert '"' not in arguments[arguments.index("--input-dir") + 1]


def test_join_request_is_explicit_in_cli_arguments(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    request = create_run_request(
        input_dir_text=str(input_dir),
        output_text=str(tmp_path / "output.mp4"),
        ffmpeg_text="ffmpeg",
        ffprobe_text="ffprobe",
        crf=20,
        preset_text="medium",
        mode=ExportMode.JOIN,
        overlay=OverlayConfig(enabled=False),
    )
    arguments = build_cli_arguments(request, tmp_path / "join_media.py")
    assert arguments[-2:] == ["--mode", "join"]


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"input_dir_text": ""}, "Выберите папку"),
        ({"output_text": "result.avi"}, ".mp4"),
        ({"ffmpeg_text": ""}, "FFmpeg"),
        ({"ffprobe_text": ""}, "FFprobe"),
        ({"crf": 52}, "CRF"),
        ({"preset_text": ""}, "preset"),
    ],
)
def test_request_validation_reports_user_correctable_errors(
    tmp_path: Path, overrides: dict[str, object], message: str
) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    values: dict[str, object] = {
        "input_dir_text": str(input_dir),
        "output_text": str(tmp_path / "output.mp4"),
        "ffmpeg_text": "ffmpeg",
        "ffprobe_text": "ffprobe",
        "crf": 20,
        "preset_text": "medium",
    }
    values.update(overrides)

    with pytest.raises(RequestValidationError, match=message):
        create_run_request(**values)  # type: ignore[arg-type]
