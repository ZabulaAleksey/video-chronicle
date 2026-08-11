#!/usr/bin/env python3
"""Normalize dated videos/photos and concatenate them into one MP4.

The source files are only read.  Every intermediate file and the final movie are
created separately.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


VIDEO_EXTENSIONS = {
    ".3gp",
    ".avi",
    ".m2ts",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp4",
    ".mpeg",
    ".mpg",
    ".mts",
    ".webm",
}
PHOTO_EXTENSIONS = {
    ".bmp",
    ".heic",
    ".jpeg",
    ".jpg",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
}
MEDIA_EXTENSIONS = VIDEO_EXTENSIONS | PHOTO_EXTENSIONS

DATE_TAGS = (
    "creation_time",
    "com.apple.quicktime.creationdate",
    "date_time_original",
    "datetimeoriginal",
    "media_create_date",
    "create_date",
    "encoded_date",
    "date",
)


@dataclass(frozen=True)
class MediaItem:
    path: Path
    taken_at: datetime
    is_photo: bool
    has_audio: bool
    date_source: str


class MediaError(RuntimeError):
    """An error tied to one input media file."""


def expanded_path(value: str) -> Path:
    """Return a user-supplied path with `~` expanded."""
    return Path(value).expanduser()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Sort videos/photos by creation time, add a timestamp, normalize "
            "to 1600x900/60 FPS/H.264, and concatenate them."
        )
    )
    parser.add_argument(
        "--input-dir",
        type=expanded_path,
        default=Path.home() / "Input",
        help="folder containing source media (default: ~/Input)",
    )
    parser.add_argument(
        "--output",
        type=expanded_path,
        default=None,
        help="final MP4 path (default: <input-dir>/output.mp4)",
    )
    parser.add_argument(
        "--error-log",
        type=expanded_path,
        default=None,
        help="error log path (default: next to output as errors.log)",
    )
    parser.add_argument(
        "--font-file",
        type=expanded_path,
        default=None,
        help="optional TrueType/OpenType font used for the timestamp",
    )
    parser.add_argument(
        "--ffmpeg",
        default="ffmpeg",
        help="ffmpeg executable name or full path",
    )
    parser.add_argument(
        "--ffprobe",
        default="ffprobe",
        help="ffprobe executable name or full path",
    )
    parser.add_argument(
        "--crf",
        type=int,
        default=20,
        help="H.264 quality (lower is better; default: 20)",
    )
    parser.add_argument(
        "--preset",
        default="medium",
        help="libx264 preset (default: medium)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="replace an existing output file",
    )
    parser.add_argument(
        "--keep-work",
        action="store_true",
        help="keep normalized clips and concat list after completion",
    )
    return parser.parse_args()


def configure_logging(log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("join_media")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    file_handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    file_handler.setLevel(logging.WARNING)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    )
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter("%(message)s"))

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger


def resolve_executable(value: str, label: str) -> str:
    candidate = Path(value).expanduser()
    if candidate.parent != Path(".") or candidate.is_absolute():
        if candidate.is_file():
            return str(candidate.resolve())
        raise RuntimeError(f"{label} not found: {candidate}")
    resolved = shutil.which(value)
    if not resolved:
        raise RuntimeError(
            f"{label} is not installed or is missing from PATH. "
            f"Install FFmpeg or pass --{label.lower()} with a full path."
        )
    return resolved


def run_command(command: list[str], context: str) -> subprocess.CompletedProcess[str]:
    creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=creation_flags,
        check=False,
    )
    if result.returncode != 0:
        details = result.stderr.strip() or result.stdout.strip() or "unknown error"
        if len(details) > 6000:
            details = details[-6000:]
        raise MediaError(f"{context} (exit code {result.returncode}):\n{details}")
    return result


def probe_media(path: Path, ffprobe: str) -> dict[str, Any]:
    result = run_command(
        [
            ffprobe,
            "-v",
            "error",
            "-show_format",
            "-show_streams",
            "-of",
            "json",
            str(path),
        ],
        f"ffprobe failed for {path}",
    )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise MediaError(f"ffprobe returned invalid JSON for {path}: {exc}") from exc


def iter_tag_pairs(probe: dict[str, Any]) -> Iterable[tuple[str, Any]]:
    format_tags = probe.get("format", {}).get("tags", {})
    if isinstance(format_tags, dict):
        yield from format_tags.items()
    for stream in probe.get("streams", []):
        tags = stream.get("tags", {})
        if isinstance(tags, dict):
            yield from tags.items()


def parse_datetime_text(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    text = value.strip().replace("UTC ", "")
    if not text:
        return None

    # ISO 8601, including FFmpeg's common trailing Z form.  We deliberately
    # retain the recorded wall-clock fields: the requested overlay should show
    # the timestamp stored by the camera, without silently changing time zones.
    iso_candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(iso_candidate)
        return parsed.replace(tzinfo=None)
    except ValueError:
        pass

    formats = (
        "%Y:%m:%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%Y%m%d_%H%M%S",
        "%Y%m%d-%H%M%S",
        "%d.%m.%Y %H:%M:%S",
        "%d.%m.%Y %H:%M",
    )
    for date_format in formats:
        try:
            return datetime.strptime(text, date_format)
        except ValueError:
            continue
    return None


def datetime_from_metadata(probe: dict[str, Any]) -> tuple[datetime, str] | None:
    values: dict[str, Any] = {}
    for key, value in iter_tag_pairs(probe):
        values.setdefault(str(key).casefold(), value)
    for wanted_key in DATE_TAGS:
        actual_value = values.get(wanted_key.casefold())
        parsed = parse_datetime_text(actual_value)
        if parsed is not None:
            return parsed, f"metadata:{wanted_key}"
    return None


FILENAME_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?<!\d)(\d{8}[_-]\d{6})(?!\d)"), "%Y%m%d_%H%M%S"),
    (re.compile(r"(?<!\d)(\d{14})(?!\d)"), "%Y%m%d%H%M%S"),
    (
        re.compile(r"(?<!\d)(\d{4}[-.]\d{2}[-.]\d{2}[ _-]\d{2}[-.]\d{2}[-.]\d{2})(?!\d)"),
        "flexible",
    ),
    (
        re.compile(r"(?<!\d)(\d{2}[.]\d{2}[.]\d{4}[ _-]\d{2}[-.]\d{2}(?:[-.]\d{2})?)(?!\d)"),
        "day-first",
    ),
)


def datetime_from_filename(path: Path) -> tuple[datetime, str] | None:
    stem = path.stem
    for pattern, date_format in FILENAME_PATTERNS:
        match = pattern.search(stem)
        if not match:
            continue
        value = match.group(1)
        try:
            if date_format == "%Y%m%d_%H%M%S":
                normalized = value.replace("-", "_")
                parsed = datetime.strptime(normalized, date_format)
            elif date_format == "flexible":
                digits = re.sub(r"\D", "", value)
                parsed = datetime.strptime(digits, "%Y%m%d%H%M%S")
            elif date_format == "day-first":
                digits = re.sub(r"\D", "", value)
                fmt = "%d%m%Y%H%M%S" if len(digits) == 14 else "%d%m%Y%H%M"
                parsed = datetime.strptime(digits, fmt)
            else:
                parsed = datetime.strptime(value, date_format)
            return parsed, "filename"
        except ValueError:
            continue
    return None


def inspect_item(path: Path, ffprobe: str) -> MediaItem:
    probe = probe_media(path, ffprobe)
    streams = probe.get("streams", [])
    has_video = any(stream.get("codec_type") == "video" for stream in streams)
    if not has_video:
        raise MediaError(f"no video/image stream found in {path}")

    date_result = datetime_from_metadata(probe) or datetime_from_filename(path)
    if date_result is None:
        raise MediaError(
            f"no supported creation date in metadata or filename: {path.name}"
        )
    taken_at, source = date_result
    return MediaItem(
        path=path,
        taken_at=taken_at,
        is_photo=path.suffix.casefold() in PHOTO_EXTENSIONS,
        has_audio=any(stream.get("codec_type") == "audio" for stream in streams),
        date_source=source,
    )


def ffmpeg_filter_escape(value: str) -> str:
    return (
        value.replace("\\", "/")
        .replace(":", r"\:")
        .replace("'", r"\'")
        .replace("[", r"\[")
        .replace("]", r"\]")
        .replace(",", r"\,")
        .replace(";", r"\;")
    )


WEEKDAY_ABBREV_RU = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")


def russian_weekday_abbrev(dt: datetime) -> str:
    return WEEKDAY_ABBREV_RU[dt.weekday()]


def find_default_font() -> Path | None:
    home = Path.home()
    candidates = [
        home / "AppData/Local/Microsoft/Windows/Fonts/comic.ttf",
        home / "AppData/Local/Microsoft/Windows/Fonts/comicbd.ttf",
        home / "AppData/Local/Microsoft/Windows/Fonts/arial.ttf",
        home / ".local/share/fonts/DejaVuSans.ttf",
        home / "Library/Fonts/Arial.ttf",
    ]
    windows_dir = os.environ.get("WINDIR")
    if windows_dir:
        windows_fonts = Path(windows_dir) / "Fonts"
        candidates[:0] = [
            windows_fonts / "comic.ttf",
            windows_fonts / "comicbd.ttf",
            windows_fonts / "arial.ttf",
        ]
    return next((font for font in candidates if font.is_file()), None)


def make_video_filter(item: MediaItem, font_file: Path | None) -> str:
    # Portrait media remains upright and is fitted into the common landscape
    # canvas.  A common canvas is necessary for gapless stream concatenation.
    filters = [
        "setpts=PTS-STARTPTS",
        "scale=1600:900:force_original_aspect_ratio=decrease",
        "pad=1600:900:(ow-iw)/2:(oh-ih)/2:color=black",
        "setsar=1",
        "fps=60",
    ]
    timestamp = ffmpeg_filter_escape(
        f"{item.taken_at.strftime('%d.%m.%y')} {russian_weekday_abbrev(item.taken_at)}"
    )
    drawtext_options = [
        f"text='{timestamp}'",
        "fontcolor=black",
        "bordercolor=white",
        "borderw=4",
        "fontsize=72",
        "box=0",
        "x=20",
        "y=h-text_h-20",
    ]
    if font_file is not None:
        drawtext_options.insert(
            0, f"fontfile='{ffmpeg_filter_escape(str(font_file.resolve()))}'"
        )
    filters.append("drawtext=" + ":".join(drawtext_options))
    return ",".join(filters)


def normalize_item(
    item: MediaItem,
    destination: Path,
    ffmpeg: str,
    font_file: Path | None,
    crf: int,
    preset: str,
) -> None:
    command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y"]
    if item.is_photo:
        command += [
            "-loop",
            "1",
            "-framerate",
            "60",
            "-t",
            "2",
            "-i",
            str(item.path),
            "-f",
            "lavfi",
            "-i",
            "anullsrc=channel_layout=stereo:sample_rate=48000",
        ]
    else:
        command += ["-i", str(item.path)]
        if not item.has_audio:
            command += [
                "-f",
                "lavfi",
                "-i",
                "anullsrc=channel_layout=stereo:sample_rate=48000",
            ]

    video_filter = make_video_filter(item, font_file)
    if item.has_audio and not item.is_photo:
        filter_complex = (
            f"[0:v:0]{video_filter}[v];"
            "[0:a:0]aformat=sample_rates=48000:channel_layouts=stereo,"
            "asetpts=PTS-STARTPTS,apad[a]"
        )
        command += [
            "-filter_complex",
            filter_complex,
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-shortest",
        ]
    else:
        command += [
            "-filter_complex",
            f"[0:v:0]{video_filter}[v]",
            "-map",
            "[v]",
            "-map",
            "1:a:0",
            "-shortest",
        ]

    if item.is_photo:
        command += ["-t", "2"]
    command += [
        "-c:v",
        "libx264",
        "-preset",
        preset,
        "-crf",
        str(crf),
        "-pix_fmt",
        "yuv420p",
        "-profile:v",
        "high",
        "-level:v",
        "4.2",
        "-g",
        "120",
        "-video_track_timescale",
        "60000",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        "48000",
        "-ac",
        "2",
        "-map_metadata",
        "-1",
        "-sn",
        "-dn",
        str(destination),
    ]
    run_command(command, f"FFmpeg failed for {item.path}")


def concat_escape(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").replace("'", "'\\''")


def concatenate(
    clips: list[Path], concat_file: Path, temporary_output: Path, ffmpeg: str
) -> None:
    concat_file.write_text(
        "".join(f"file '{concat_escape(clip)}'\n" for clip in clips),
        encoding="utf-8",
    )
    run_command(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(temporary_output),
        ],
        "failed to concatenate normalized clips",
    )


def collect_source_paths(input_dir: Path, output: Path, error_log: Path) -> list[Path]:
    excluded = {output.resolve(), error_log.resolve()}
    return sorted(
        (
            path
            for path in input_dir.iterdir()
            if path.is_file()
            and path.suffix.casefold() in MEDIA_EXTENSIONS
            and path.resolve() not in excluded
        ),
        key=lambda path: path.name.casefold(),
    )


def main() -> int:
    args = parse_args()
    input_dir = args.input_dir.expanduser().resolve()
    output = (
        args.output.expanduser().resolve()
        if args.output is not None
        else input_dir / "output.mp4"
    )
    error_log = (
        args.error_log.expanduser().resolve()
        if args.error_log is not None
        else output.parent / "errors.log"
    )
    logger = configure_logging(error_log)

    try:
        if not input_dir.is_dir():
            raise RuntimeError(f"input folder does not exist: {input_dir}")
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists() and not args.overwrite:
            raise RuntimeError(
                f"output already exists: {output}. Use --overwrite to replace it."
            )
        if output.suffix.casefold() != ".mp4":
            raise RuntimeError("the output filename must have an .mp4 extension")
        if not 0 <= args.crf <= 51:
            raise RuntimeError("--crf must be between 0 and 51")

        ffmpeg = resolve_executable(args.ffmpeg, "FFmpeg")
        ffprobe = resolve_executable(args.ffprobe, "FFprobe")
        font_file = args.font_file.expanduser().resolve() if args.font_file else find_default_font()
        if font_file is not None and not font_file.is_file():
            raise RuntimeError(f"font file does not exist: {font_file}")

        source_paths = collect_source_paths(input_dir, output, error_log)
        if not source_paths:
            raise RuntimeError(f"no supported videos or photos found in {input_dir}")

        logger.info("Inspecting %d source files...", len(source_paths))
        items: list[MediaItem] = []
        failed_count = 0
        for path in source_paths:
            try:
                items.append(inspect_item(path, ffprobe))
            except Exception as exc:
                failed_count += 1
                logger.warning("SKIPPED during inspection | %s | %s", path, exc)

        items.sort(key=lambda item: (item.taken_at, item.path.name.casefold()))
        if not items:
            raise RuntimeError(f"none of the {len(source_paths)} files could be inspected")

        logger.info(
            "Ready: %d files, from %s to %s.",
            len(items),
            items[0].taken_at.strftime("%d.%m.%Y %H:%M:%S"),
            items[-1].taken_at.strftime("%d.%m.%Y %H:%M:%S"),
        )

        work_dir_path = Path(
            tempfile.mkdtemp(prefix="video_join_work_", dir=str(output.parent))
        )
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
                    normalize_item(
                        item,
                        destination,
                        ffmpeg,
                        font_file,
                        args.crf,
                        args.preset,
                    )
                    successful_clips.append(destination)
                except Exception as exc:
                    failed_count += 1
                    logger.warning("SKIPPED during encoding | %s | %s", item.path, exc)

            if not successful_clips:
                raise RuntimeError("no files were successfully encoded")

            logger.info("Concatenating %d normalized clips...", len(successful_clips))
            concatenate(
                successful_clips,
                work_dir_path / "concat.txt",
                temporary_output,
                ffmpeg,
            )
            os.replace(temporary_output, output)
            logger.info("Done: %s", output)
            logger.info("Files skipped with errors: %d", failed_count)
            logger.info("Error log: %s", error_log)
        finally:
            if args.keep_work:
                logger.info("Work files kept in: %s", work_dir_path)
            else:
                shutil.rmtree(work_dir_path, ignore_errors=True)
        return 0
    except Exception as exc:
        logger.error("FATAL | %s", exc)
        logger.error("See log: %s", error_log)
        return 1


if __name__ == "__main__":
    sys.exit(main())
