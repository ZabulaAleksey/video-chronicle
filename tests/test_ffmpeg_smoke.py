from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


MINIMUM_FFMPEG_VERSION = (9, 0, 1)


def _resolve_tool(environment_name: str, command_name: str) -> str | None:
    configured = os.environ.get(environment_name)
    candidates = [configured, command_name] if configured else [command_name]
    for candidate in candidates:
        if candidate is None:
            continue
        path = Path(candidate).expanduser()
        if path.is_file():
            return str(path.resolve())
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return None


def _tool_version(executable: str) -> tuple[tuple[int, int, int], str]:
    result = subprocess.run(
        [executable, "-version"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    first_line = result.stdout.splitlines()[0] if result.stdout else ""
    match = re.search(r"\bversion\s+(?:n)?(\d+)\.(\d+)(?:\.(\d+))?", first_line)
    if result.returncode != 0 or match is None:
        pytest.fail(f"cannot read tool version from {executable!r}: {first_line!r}")
    return (
        int(match.group(1)),
        int(match.group(2)),
        int(match.group(3) or 0),
    ), first_line


def _run(command: list[str], context: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"{context} failed with exit code {result.returncode}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    return result


def _snapshot(path: Path) -> tuple[str, int, int]:
    stat = path.stat()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest, stat.st_size, stat.st_mtime_ns


def test_synthetic_photo_video_cli_smoke_preserves_sources(tmp_path: Path) -> None:
    ffmpeg = _resolve_tool("VIDEO_CHRONICLE_FFMPEG", "ffmpeg")
    ffprobe = _resolve_tool("VIDEO_CHRONICLE_FFPROBE", "ffprobe")
    missing = [
        name
        for name, executable in (("FFmpeg", ffmpeg), ("FFprobe", ffprobe))
        if executable is None
    ]
    if missing:
        pytest.skip(
            "synthetic media smoke skipped: "
            + ", ".join(missing)
            + " not found; set VIDEO_CHRONICLE_FFMPEG/VIDEO_CHRONICLE_FFPROBE "
            "or add the tools to PATH"
        )
    assert ffmpeg is not None
    assert ffprobe is not None

    ffmpeg_version, ffmpeg_line = _tool_version(ffmpeg)
    ffprobe_version, ffprobe_line = _tool_version(ffprobe)
    assert ffmpeg_version >= MINIMUM_FFMPEG_VERSION, ffmpeg_line
    assert ffprobe_version >= MINIMUM_FFMPEG_VERSION, ffprobe_line

    input_dir = tmp_path / "медиа ' smoke"
    input_dir.mkdir()
    photo = input_dir / "IMG_20240102_030405.bmp"
    video = input_dir / "VID_20240103_040506.mp4"
    output = tmp_path / "результат smoke.mp4"
    error_log = tmp_path / "ошибки smoke.log"

    _run(
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
            str(photo),
        ],
        "synthetic photo generation",
    )
    _run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=96x64:rate=10",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000",
            "-t",
            "0.3",
            "-c:v",
            "mpeg4",
            "-c:a",
            "aac",
            "-shortest",
            "-y",
            str(video),
        ],
        "synthetic video generation",
    )
    before = {path: _snapshot(path) for path in (photo, video)}

    project_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    result = subprocess.run(
        [
            sys.executable,
            str(project_root / "join_media.py"),
            "--input-dir",
            str(input_dir),
            "--output",
            str(output),
            "--error-log",
            str(error_log),
            "--ffmpeg",
            ffmpeg,
            "--ffprobe",
            ffprobe,
            "--crf",
            "35",
            "--preset",
            "ultrafast",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=180,
        env=env,
    )
    assert result.returncode == 0, (
        f"join_media CLI failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}\n"
        f"error log:\n{error_log.read_text(encoding='utf-8') if error_log.exists() else ''}"
    )
    assert output.is_file()
    assert output.stat().st_size > 0
    assert {path: _snapshot(path) for path in (photo, video)} == before

    probe = _run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_streams",
            "-of",
            "json",
            str(output),
        ],
        "result probing",
    )
    streams = json.loads(probe.stdout)["streams"]
    assert any(stream.get("codec_type") == "video" for stream in streams)
    assert any(stream.get("codec_type") == "audio" for stream in streams)
