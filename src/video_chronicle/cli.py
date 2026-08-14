"""Console parsing and validation for the canonical application service."""

from __future__ import annotations

import argparse
from pathlib import Path

from .application import execute_export
from .domain import ExportMode, ExportRequest
from .overlay import OverlayConfig, resolve_overlay_font
from . import pipeline


def _expanded_path(value: str) -> Path:
    return Path(value).expanduser()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="join_media.py",
        description=(
            "Sort videos/photos by creation time, add a timestamp, normalize "
            "to 1600x900/60 FPS/H.264, and concatenate them."
        )
    )
    parser.add_argument(
        "--input-dir",
        type=_expanded_path,
        default=Path.home() / "Input",
        help="folder containing source media (default: ~/Input)",
    )
    parser.add_argument(
        "--output",
        type=_expanded_path,
        default=None,
        help="final MP4 path (default: <input-dir>/output.mp4)",
    )
    parser.add_argument(
        "--error-log",
        type=_expanded_path,
        default=None,
        help="error log path (default: next to output as errors.log)",
    )
    parser.add_argument(
        "--font-file",
        type=_expanded_path,
        default=None,
        help="optional TrueType/OpenType font used for the timestamp",
    )
    parser.add_argument(
        "--mode",
        choices=tuple(mode.value for mode in ExportMode),
        default=ExportMode.CHRONICLE.value,
        help="export mode: chronicle with optional date overlay, or join without it",
    )
    parser.add_argument("--ffmpeg", default="ffmpeg", help="ffmpeg executable name or full path")
    parser.add_argument("--ffprobe", default="ffprobe", help="ffprobe executable name or full path")
    parser.add_argument("--crf", type=int, default=20, help="H.264 quality (lower is better; default: 20)")
    parser.add_argument("--preset", default="medium", help="libx264 preset (default: medium)")
    parser.add_argument("--overwrite", action="store_true", help="replace an existing output file")
    parser.add_argument(
        "--keep-work",
        action="store_true",
        help="keep normalized clips and concat list after completion",
    )
    return parser.parse_args(argv)


def _build_request(args: argparse.Namespace) -> ExportRequest:
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

    output.parent.mkdir(parents=True, exist_ok=True)
    pipeline.validate_error_log_path(input_dir, output, error_log)
    if not input_dir.is_dir():
        raise RuntimeError(f"input folder does not exist: {input_dir}")
    if output.exists() and not args.overwrite:
        raise RuntimeError(
            f"output already exists: {output}. Use --overwrite to replace it."
        )
    if output.suffix.casefold() != ".mp4":
        raise RuntimeError("the output filename must have an .mp4 extension")
    if not 0 <= args.crf <= 51:
        raise RuntimeError("--crf must be between 0 and 51")

    ffmpeg = pipeline.resolve_executable(args.ffmpeg, "FFmpeg")
    ffprobe = pipeline.resolve_executable(args.ffprobe, "FFprobe")
    mode = ExportMode(args.mode)
    if mode is ExportMode.JOIN and args.font_file is not None:
        raise RuntimeError("--font-file cannot be used with --mode join")
    if mode is ExportMode.JOIN:
        overlay = OverlayConfig(enabled=False)
    else:
        font_file = (
            args.font_file.expanduser().resolve()
            if args.font_file
            else pipeline.find_default_font()
        )
        if font_file is not None and not font_file.is_file():
            raise RuntimeError(f"font file does not exist: {font_file}")
        overlay = resolve_overlay_font(
            OverlayConfig(font_file=font_file), pipeline.find_default_font()
        )

    return ExportRequest(
        input_dir=input_dir,
        output=output,
        error_log=error_log,
        ffmpeg=ffmpeg,
        ffprobe=ffprobe,
        crf=args.crf,
        preset=args.preset,
        overwrite=args.overwrite,
        keep_work=args.keep_work,
        overlay=overlay,
        mode=mode,
    )


def main(argv: list[str] | None = None) -> int:
    """Run one export and preserve the legacy exit-code/message contract."""

    args = parse_args(argv)
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
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        pipeline.validate_error_log_path(input_dir, output, error_log)
        logger = pipeline.configure_logging(error_log)
        request = _build_request(args)
        return execute_export(request, logger)
    except Exception as exc:
        logger = locals().get("logger")
        if logger is None:
            import logging

            logger = logging.getLogger("join_media.bootstrap")
            if not logger.handlers:
                logger.addHandler(logging.StreamHandler())
            logger.setLevel(logging.INFO)
        logger.error("FATAL | %s", exc)
        logger.error("See log: %s", error_log)
        return 1
