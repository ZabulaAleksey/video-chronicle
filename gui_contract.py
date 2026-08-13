"""Pure configuration contract shared by the Video Chronicle GUI and tests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class RequestValidationError(ValueError):
    """A user-correctable GUI launch configuration error."""


@dataclass(frozen=True)
class GuiRunRequest:
    """Validated arguments for one legacy CLI export."""

    input_dir: Path
    output: Path
    ffmpeg: str
    ffprobe: str
    crf: int = 20
    preset: str = "medium"
    overwrite: bool = False


def create_run_request(
    *,
    input_dir_text: str,
    output_text: str,
    ffmpeg_text: str,
    ffprobe_text: str,
    crf: int,
    preset_text: str,
    overwrite: bool = False,
) -> GuiRunRequest:
    """Validate editable form values without invoking Qt or the media pipeline."""

    input_value = input_dir_text.strip()
    output_value = output_text.strip()
    ffmpeg = ffmpeg_text.strip()
    ffprobe = ffprobe_text.strip()
    preset = preset_text.strip()

    if not input_value:
        raise RequestValidationError("Выберите папку с исходными медиафайлами.")
    input_dir = Path(input_value).expanduser()
    if not input_dir.is_dir():
        raise RequestValidationError(f"Входная папка не существует: {input_dir}")

    if not output_value:
        raise RequestValidationError("Укажите путь итогового MP4-файла.")
    output = Path(output_value).expanduser()
    if output.suffix.casefold() != ".mp4":
        raise RequestValidationError("Итоговый файл должен иметь расширение .mp4.")

    if not ffmpeg:
        raise RequestValidationError("Укажите команду или путь к FFmpeg.")
    if not ffprobe:
        raise RequestValidationError("Укажите команду или путь к FFprobe.")
    if not 0 <= crf <= 51:
        raise RequestValidationError("CRF должен быть в диапазоне от 0 до 51.")
    if not preset:
        raise RequestValidationError("Укажите preset кодировщика.")

    return GuiRunRequest(
        input_dir=input_dir.resolve(),
        output=output.resolve(),
        ffmpeg=ffmpeg,
        ffprobe=ffprobe,
        crf=crf,
        preset=preset,
        overwrite=overwrite,
    )


def build_cli_arguments(request: GuiRunRequest, cli_script: Path) -> list[str]:
    """Build argv for ``join_media.py`` without quoting or shell expansion."""

    arguments = [
        str(cli_script.resolve()),
        "--input-dir",
        str(request.input_dir),
        "--output",
        str(request.output),
        "--ffmpeg",
        request.ffmpeg,
        "--ffprobe",
        request.ffprobe,
        "--crf",
        str(request.crf),
        "--preset",
        request.preset,
    ]
    if request.overwrite:
        arguments.append("--overwrite")
    return arguments
