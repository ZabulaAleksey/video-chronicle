"""Installed-wheel CLI and real FFmpeg export on authored synthetic media."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _tool(environment: str, name: str) -> str | None:
    supplied = os.environ.get(environment)
    if supplied and Path(supplied).is_file():
        return supplied
    return shutil.which(name)


def _run(argv: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        argv, cwd=cwd, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=180, check=False,
    )
    assert result.returncode == 0, result.stdout[-1000:] + result.stderr[-1000:]
    return result


def test_installed_wheel_cli_exports_two_synthetic_sources(tmp_path: Path) -> None:
    ffmpeg = _tool("VIDEO_CHRONICLE_FFMPEG", "ffmpeg")
    ffprobe = _tool("VIDEO_CHRONICLE_FFPROBE", "ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("real FFmpeg tools are required for installed-wheel export")

    wheel_dir = tmp_path / "wheel"
    wheel_dir.mkdir()
    _run([
        sys._base_executable, "-m", "pip", "wheel", "--no-deps",
        "--no-build-isolation", "--no-cache-dir", "--wheel-dir", str(wheel_dir), ".",
    ], cwd=ROOT)
    wheel = next(wheel_dir.glob("video_chronicle-*.whl"))
    installed = tmp_path / "installed"
    venv.EnvBuilder(with_pip=True).create(installed)
    scripts = installed / ("Scripts" if os.name == "nt" else "bin")
    python = scripts / ("python.exe" if os.name == "nt" else "python")
    cli = scripts / ("video-chronicle.exe" if os.name == "nt" else "video-chronicle")
    _run([str(python), "-m", "pip", "install", "--no-deps", "--no-index", str(wheel)])

    inputs = tmp_path / "input"
    inputs.mkdir()
    for name, color in (
        ("VID_20240102_030405.mp4", "red"),
        ("VID_20240103_040506.mp4", "blue"),
    ):
        _run([
            ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
            f"color=c={color}:s=160x90:r=10:d=1", "-f", "lavfi", "-i",
            "sine=frequency=440:sample_rate=48000:duration=1", "-c:v", "libx264",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(inputs / name),
        ])
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs.iterdir()}
    output = tmp_path / "output.mp4"
    _run([
        str(cli), "--input-dir", str(inputs), "--output", str(output), "--mode", "join",
        "--ffmpeg", ffmpeg, "--ffprobe", ffprobe, "--preset", "ultrafast",
    ])
    assert output.is_file() and output.stat().st_size > 0
    assert before == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs.iterdir()}
    result = _run([
        ffprobe, "-v", "error", "-show_entries", "format=duration",
        "-show_entries", "stream=codec_type,codec_name", "-of", "json", str(output),
    ])
    probe = json.loads(result.stdout)
    assert {row["codec_type"]: row["codec_name"] for row in probe["streams"]} == {
        "video": "h264", "audio": "aac",
    }
    assert 1.8 <= float(probe["format"]["duration"]) <= 2.3
