"""Canonical media inspection, normalization, and publication adapters."""

from __future__ import annotations

import json
import logging
import os
import shutil
import stat
import subprocess
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from .domain import MediaError, MediaItem
from .metadata import (
    DATE_TAGS,
    FILENAME_PATTERNS,
    decide_date,
    datetime_from_filename,
    datetime_from_metadata,
    iter_tag_pairs,
    parse_datetime_text,
)
from .ports import CommandRunner, ProbeMedia


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

def _is_symlink_or_reparse(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except FileNotFoundError:
        return False
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _same_file_identity(left: Path, right: Path) -> bool:
    if left.resolve(strict=False) == right.resolve(strict=False):
        return True
    try:
        return left.samefile(right)
    except (FileNotFoundError, OSError):
        return False


def validate_error_log_path(
    input_dir: Path, output: Path, error_log: Path
) -> None:
    """Reject log targets that could truncate media or an unrelated file."""

    if _is_symlink_or_reparse(error_log):
        raise RuntimeError(
            f"error log must not be a symlink or reparse point: {error_log}"
        )
    if _same_file_identity(error_log, output):
        raise RuntimeError("error log must be different from the output file")
    if input_dir.is_dir():
        for candidate in input_dir.iterdir():
            if candidate.suffix.casefold() in MEDIA_EXTENSIONS and _same_file_identity(
                error_log, candidate
            ):
                raise RuntimeError(
                    f"error log must not replace source media: {candidate}"
                )
    if error_log.exists() and error_log.suffix.casefold() != ".log":
        raise RuntimeError(
            f"refusing to replace an existing non-.log file: {error_log}"
        )


def _validate_manifest_path(path: Path) -> None:
    if any(ord(character) < 32 or ord(character) == 127 for character in str(path)):
        raise RuntimeError(
            f"concat manifest paths must not contain control characters: {path!s}"
        )


def expanded_path(value: str) -> Path:
    """Return a user-supplied path with `~` expanded."""
    return Path(value).expanduser()


def parse_args(argv: list[str] | None = None):
    """Compatibility export for callers that imported the legacy parser."""

    from .cli import parse_args as parse_cli_args

    return parse_cli_args(argv)


def configure_logging(log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if _is_symlink_or_reparse(log_path):
        raise RuntimeError(f"error log must not be a symlink or reparse point: {log_path}")
    logger = logging.getLogger("join_media")
    logger.setLevel(logging.INFO)
    for handler in logger.handlers[:]:
        handler.close()
        logger.removeHandler(handler)

    flags = os.O_CREAT | os.O_WRONLY | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(log_path, flags, 0o600)
    stream = os.fdopen(descriptor, "w", encoding="utf-8")
    file_handler = logging.StreamHandler(stream)
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


def run_command(
    command: list[str],
    context: str,
    *,
    timeout: float | None = None,
    max_output_bytes: int = 8 * 1024 * 1024,
) -> subprocess.CompletedProcess[str]:
    """Run list argv with bounded in-memory capture and optional timeout."""

    creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=creation_flags,
        shell=False,
    )
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    lock = threading.Lock()
    limit_exceeded = threading.Event()

    def drain(name: str, stream) -> None:
        while True:
            chunk = stream.read(64 * 1024)
            if not chunk:
                return
            with lock:
                used = len(buffers["stdout"]) + len(buffers["stderr"])
                remaining = max(0, max_output_bytes - used)
                buffers[name].extend(chunk[:remaining])
                if len(chunk) > remaining:
                    limit_exceeded.set()
                    process.kill()
                    return

    threads = [
        threading.Thread(target=drain, args=("stdout", process.stdout), daemon=True),
        threading.Thread(target=drain, args=("stderr", process.stderr), daemon=True),
    ]
    for thread in threads:
        thread.start()
    try:
        returncode = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        process.kill()
        process.wait()
        for thread in threads:
            thread.join()
        raise MediaError(f"{context}: timed out after {timeout:g} seconds") from exc
    for thread in threads:
        thread.join()
    if limit_exceeded.is_set():
        raise MediaError(f"{context}: tool output exceeded {max_output_bytes} bytes")
    stdout = bytes(buffers["stdout"]).decode("utf-8", errors="replace")
    stderr = bytes(buffers["stderr"]).decode("utf-8", errors="replace")
    result = subprocess.CompletedProcess(
        args=command,
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )
    if result.returncode != 0:
        details = result.stderr.strip() or result.stdout.strip() or "unknown error"
        if len(details) > 6000:
            details = details[-6000:]
        raise MediaError(f"{context} (exit code {result.returncode}):\n{details}")
    return result


def probe_media(
    path: Path,
    ffprobe: str,
    runner: CommandRunner | None = None,
) -> dict[str, Any]:
    runner = runner or run_command
    result = runner(
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
        timeout=30,
        max_output_bytes=8 * 1024 * 1024,
    )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise MediaError(f"ffprobe returned invalid JSON for {path}: {exc}") from exc


def inspect_item(
    path: Path,
    ffprobe: str,
    probe_adapter: ProbeMedia | None = None,
    runner: CommandRunner | None = None,
) -> MediaItem:
    probe_adapter = probe_adapter or probe_media
    runner = runner or run_command
    probe = probe_adapter(path, ffprobe, runner)
    streams = probe.get("streams", [])
    has_video = any(stream.get("codec_type") == "video" for stream in streams)
    if not has_video:
        raise MediaError(f"no video/image stream found in {path}")

    date_decision = decide_date(probe, path)
    if date_decision is None:
        raise MediaError(
            f"no supported creation date in metadata or filename: {path.name}"
        )
    selected = date_decision.selected
    return MediaItem(
        path=path,
        taken_at=selected.wall_time,
        is_photo=path.suffix.casefold() in PHOTO_EXTENSIONS,
        has_audio=any(stream.get("codec_type") == "audio" for stream in streams),
        date_source=selected.source,
        date_decision=date_decision,
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
    runner: CommandRunner | None = None,
) -> None:
    runner = runner or run_command
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
    runner(command, f"FFmpeg failed for {item.path}")


def concat_escape(path: Path) -> str:
    _validate_manifest_path(path)
    return str(path.resolve()).replace("\\", "/").replace("'", "'\\''")


def concatenate(
    clips: list[Path],
    concat_file: Path,
    temporary_output: Path,
    ffmpeg: str,
    runner: CommandRunner | None = None,
) -> None:
    runner = runner or run_command
    for path in [*clips, concat_file, temporary_output]:
        _validate_manifest_path(path)
    concat_file.write_text(
        "".join(f"file '{concat_escape(clip)}'\n" for clip in clips),
        encoding="utf-8",
    )
    runner(
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


def publish_output(temporary_output: Path, output: Path, overwrite: bool) -> None:
    """Publish a finished movie without an unauthorized replacement race."""

    if overwrite:
        os.replace(temporary_output, output)
        return

    used_hard_link = os.name != "nt"
    try:
        if used_hard_link:
            # The work directory is deliberately created next to the output,
            # so a hard link is an atomic create-if-absent operation on POSIX.
            os.link(temporary_output, output)
        else:
            # Unlike POSIX rename(), Windows rename fails if the destination
            # exists and works on FAT/exFAT without hard-link support.
            os.rename(temporary_output, output)
    except FileExistsError as exc:
        raise RuntimeError(
            f"output appeared during processing: {output}. "
            "Run again with --overwrite to replace it."
        ) from exc
    except OSError as exc:
        raise RuntimeError(
            "could not publish the output without replacing an existing file; "
            "the destination filesystem must support an atomic no-replace "
            "operation or the user must explicitly allow --overwrite"
        ) from exc
    if used_hard_link:
        try:
            temporary_output.unlink()
        except OSError:
            # The published hard link is already complete. The known work
            # directory cleanup will make a best effort to remove the old name.
            pass


def collect_source_paths(input_dir: Path, output: Path, error_log: Path) -> list[Path]:
    excluded = {output.resolve(), error_log.resolve()}
    return sorted(
        (
            path
            for path in input_dir.iterdir()
            if path.is_file()
            and not _is_symlink_or_reparse(path)
            and path.suffix.casefold() in MEDIA_EXTENSIONS
            and path.resolve() not in excluded
        ),
        key=lambda path: path.name.casefold(),
    )


def validate_source_path(input_dir: Path, source: Path) -> None:
    """Revalidate an untrusted source immediately before each tool boundary."""

    if _is_symlink_or_reparse(source):
        raise MediaError(f"source became a symlink or reparse point: {source}")
    try:
        root = input_dir.resolve(strict=True)
        resolved = source.resolve(strict=True)
    except FileNotFoundError as exc:
        raise MediaError(f"source disappeared before processing: {source}") from exc
    if not resolved.is_relative_to(root) or not source.is_file():
        raise MediaError(f"source is outside the selected input folder: {source}")


def create_workspace(output_parent: Path) -> Path:
    return Path(
        tempfile.mkdtemp(prefix="video_join_work_", dir=str(output_parent))
    )


def cleanup_workspace(workspace: Path) -> None:
    shutil.rmtree(workspace, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    """Compatibility export for the canonical package CLI."""

    from .cli import main as cli_main

    return cli_main(argv)
