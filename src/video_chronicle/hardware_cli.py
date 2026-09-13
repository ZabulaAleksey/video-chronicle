"""CLI for deterministic FFmpeg capability reports."""

from __future__ import annotations

import argparse
from pathlib import Path
import tempfile

from .hardware import probe_ffmpeg
from .pipeline import publish_output, run_command


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="video-chronicle-hardware")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        report = probe_ffmpeg(args.ffmpeg, run_command)
        payload = report.to_json()
        if args.output is None:
            print(payload, end="")
        else:
            output = args.output.expanduser().resolve(strict=False)
            if output.exists():
                raise FileExistsError(f"output already exists: {output}")
            output.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(
                prefix="video_chronicle_hardware_", dir=output.parent
            ) as temporary_directory:
                temporary = Path(temporary_directory) / "capabilities.json"
                temporary.write_text(payload, encoding="utf-8")
                publish_output(temporary, output, overwrite=False)
    except Exception as exc:
        print(f"Hardware probe failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
