"""Explicit command-line entry point for optional local transcription."""

from __future__ import annotations

import argparse
from pathlib import Path

from .pipeline import run_command
from .transcription import (
    ModelManifest,
    TranscriptionRequest,
    WhisperCppAdapter,
    write_transcript,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="video-chronicle-transcribe",
        description="Create a local timestamped transcript with explicit whisper.cpp/model paths.",
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("--item-id", required=True)
    parser.add_argument("--duration-us", required=True, type=int)
    parser.add_argument("--language", default="auto")
    parser.add_argument("--whisper-cli", required=True, type=Path)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--model-manifest", required=True, type=Path)
    parser.add_argument("--ffmpeg", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        source = args.source.expanduser().resolve(strict=True)
        adapter = WhisperCppAdapter(
            args.whisper_cli.expanduser(),
            args.model.expanduser(),
            ModelManifest.from_json_file(args.model_manifest.expanduser()),
            args.ffmpeg.expanduser(),
            runner=run_command,
        )
        transcript = adapter.transcribe(
            TranscriptionRequest(
                args.item_id, source, args.duration_us, args.language
            )
        )
        write_transcript(args.output, transcript, overwrite=args.overwrite)
    except Exception as exc:
        print(f"Transcription failed: {exc}")
        return 1
    print(f"Transcript written: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
