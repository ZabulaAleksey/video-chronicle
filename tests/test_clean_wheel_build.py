"""Real installed consumers without pip/global setuptools/source imports."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import venv
import zipfile
from pathlib import Path

import pytest
from test_wheel_cli_export import _tool

from video_chronicle.process_control import ProcessOutputLimitExceeded, ProcessTimedOut

ROOT = Path(__file__).resolve().parents[1]


def _run(argv, *, cwd):
    environment = os.environ.copy()
    for name in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT"):
        environment.pop(name, None)
    result = subprocess.run(
        argv,
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
        check=False,
    )
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
    return result


def test_locked_build_and_clean_no_pip_installed_consumers(tmp_path: Path):
    uv = shutil.which("uv")
    assert uv, "canonical uv executable is required for the project build gate"
    ffmpeg = _tool("VIDEO_CHRONICLE_FFMPEG", "ffmpeg")
    ffprobe = _tool("VIDEO_CHRONICLE_FFPROBE", "ffprobe")
    assert ffmpeg and ffprobe, "real FFmpeg pair is required for clean installed export"
    wheel_dir = tmp_path / "build-artifacts"
    _run(
        [
            sys.executable,
            str(ROOT / "scripts/build_wheel.py"),
            "--offline",
            "--out-dir",
            str(wheel_dir),
        ],
        cwd=tmp_path,
    )
    wheel = next(wheel_dir.glob("video_chronicle-*.whl"))
    installed = tmp_path / "clean-installed"
    venv.EnvBuilder(with_pip=False, system_site_packages=False).create(installed)
    scripts = installed / ("Scripts" if os.name == "nt" else "bin")
    python = scripts / ("python.exe" if os.name == "nt" else "python")
    no_global = _run(
        [
            str(python),
            "-I",
            "-c",
            "import importlib.util; assert all(importlib.util.find_spec(n) is None for n in ('pip','setuptools','wheel')); print('NO_GLOBAL_BUILD_PACKAGES')",
        ],
        cwd=tmp_path,
    )
    assert "NO_GLOBAL_BUILD_PACKAGES" in no_global.stdout
    requirements = tmp_path / "locked-runtime.txt"
    _run(
        [
            uv,
            "export",
            "--project",
            str(ROOT),
            "--locked",
            "--no-dev",
            "--no-emit-project",
            "--no-header",
            "--format",
            "requirements.txt",
            "--output-file",
            str(requirements),
        ],
        cwd=tmp_path,
    )
    _run(
        [
            uv,
            "pip",
            "install",
            "--python",
            str(python),
            "--offline",
            "--require-hashes",
            "--no-deps",
            "-r",
            str(requirements),
        ],
        cwd=tmp_path,
    )
    _run(
        [
            uv,
            "pip",
            "install",
            "--python",
            str(python),
            "--offline",
            "--no-deps",
            "--no-index",
            str(wheel),
        ],
        cwd=tmp_path,
    )
    _run(
        [
            str(python),
            "-I",
            "-c",
            "import importlib.util,sys,pathlib,video_chronicle; assert all(importlib.util.find_spec(n) is None for n in ('pip','setuptools','wheel')); assert pathlib.Path(video_chronicle.__file__).is_relative_to(pathlib.Path(sys.prefix)); print('CLEAN_ORIGIN')",
        ],
        cwd=tmp_path,
    )
    cli = scripts / ("video-chronicle.exe" if os.name == "nt" else "video-chronicle")
    assert "--input-dir" in _run([str(cli), "--help"], cwd=tmp_path).stdout
    gui = _run(
        [
            str(python),
            "-I",
            "-c",
            "from PySide6.QtWidgets import QApplication; from video_chronicle_gui import build_main_window; from video_chronicle.tool_setup import ManagedToolSetupProcess; app=QApplication([]); window=build_main_window(); assert window._tool_setup_factory is ManagedToolSetupProcess; window.close(); app.processEvents(); print('REAL_INSTALLED_GUI')",
        ],
        cwd=tmp_path,
    )
    assert "REAL_INSTALLED_GUI" in gui.stdout
    inputs = tmp_path / "input"
    inputs.mkdir()
    for name, color in (
        ("VID_20240102_030405.mp4", "red"),
        ("VID_20240103_040506.mp4", "blue"),
    ):
        _run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                f"color=c={color}:s=160x90:r=10:d=1",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:sample_rate=48000:duration=1",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-shortest",
                str(inputs / name),
            ],
            cwd=tmp_path,
        )
    before = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs.iterdir()
    }
    output = tmp_path / "output.mp4"
    _run(
        [
            str(cli),
            "--input-dir",
            str(inputs),
            "--output",
            str(output),
            "--mode",
            "join",
            "--ffmpeg",
            ffmpeg,
            "--ffprobe",
            ffprobe,
            "--preset",
            "ultrafast",
        ],
        cwd=tmp_path,
    )
    assert output.is_file() and output.stat().st_size > 0
    assert before == {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs.iterdir()
    }
    probe = json.loads(
        _run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-show_entries",
                "stream=codec_type,codec_name",
                "-of",
                "json",
                str(output),
            ],
            cwd=tmp_path,
        ).stdout
    )
    assert {row["codec_type"]: row["codec_name"] for row in probe["streams"]} == {
        "video": "h264",
        "audio": "aac",
    }
    assert 1.8 <= float(probe["format"]["duration"]) <= 2.3


def test_existing_wheel_is_preserved_by_build_guard(tmp_path: Path):
    out = tmp_path / "existing"
    out.mkdir()
    wheel = out / "video_chronicle-0.2.0-py3-none-any.whl"
    wheel.write_bytes(b"preserve authored existing artifact")
    before = wheel.read_bytes()
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/build_wheel.py"),
            "--offline",
            "--out-dir",
            str(out),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 2
    assert "already contains" in result.stderr
    assert wheel.read_bytes() == before


def test_build_version_drift_fails_before_wheel_output(tmp_path: Path):
    source = tmp_path / "project"
    script = source / "scripts/build_wheel.py"
    script.parent.mkdir(parents=True)
    shutil.copy2(ROOT / "scripts/build_wheel.py", script)
    lock = (ROOT / "uv.lock").read_text(encoding="utf-8")
    current = 'name = "setuptools"\nversion = "84.0.0"'
    assert lock.count(current) == 1
    (source / "uv.lock").write_text(
        lock.replace(current, 'name = "setuptools"\nversion = "99.0.0"'),
        encoding="utf-8",
    )
    out = tmp_path / "must-not-be-created"
    result = subprocess.run(
        [sys.executable, str(script), "--offline", "--out-dir", str(out)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 2
    assert "must match uv.lock" in result.stderr
    assert not out.exists()


def _build_module():
    spec = importlib.util.spec_from_file_location(
        "reviewed_build_wheel", ROOT / "scripts/build_wheel.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "failure", ["timeout", "output_limit", "nonzero", "invalid_zip"]
)
def test_failed_build_leaves_no_published_wheel_and_retry_succeeds(
    tmp_path, monkeypatch, failure
):
    module = _build_module()
    out = tmp_path / "atomic-output"
    failed = False

    def runner(command, **kwargs):
        nonlocal failed
        if command[1] == "lock":
            return subprocess.CompletedProcess(command, 0, "", "")
        stage = Path(command[command.index("--out-dir") + 1])
        wheel = stage / "video_chronicle-0.2.0-py3-none-any.whl"
        if not failed:
            failed = True
            wheel.write_bytes(b"incomplete archive from interrupted builder")
            if failure == "timeout":
                raise ProcessTimedOut("controlled deadline")
            if failure == "output_limit":
                raise ProcessOutputLimitExceeded("controlled output cap")
            return subprocess.CompletedProcess(
                command, 1 if failure == "nonzero" else 0, "", "controlled error"
            )
        with zipfile.ZipFile(wheel, "w") as archive:
            archive.writestr(
                "video_chronicle/__init__.py", "# complete controlled artifact"
            )
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(module, "run_managed_command", runner)
    with pytest.raises((ValueError, ProcessTimedOut, ProcessOutputLimitExceeded)):
        module.build(out, offline=True)
    assert out.is_dir() and list(out.iterdir()) == []
    completed = module.build(out, offline=True)
    assert completed.is_file() and zipfile.is_zipfile(completed)
    assert list(out.iterdir()) == [completed]


def test_atomic_promotion_preserves_racing_existing_wheel(tmp_path, monkeypatch):
    module = _build_module()
    out = tmp_path / "atomic-output"
    name = "video_chronicle-0.2.0-py3-none-any.whl"
    existing = b"another writer owns this artifact"

    def runner(command, **kwargs):
        if command[1] == "lock":
            return subprocess.CompletedProcess(command, 0, "", "")
        stage = Path(command[command.index("--out-dir") + 1])
        with zipfile.ZipFile(stage / name, "w") as archive:
            archive.writestr(
                "video_chronicle/__init__.py", "# complete controlled artifact"
            )
        (out / name).write_bytes(existing)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(module, "run_managed_command", runner)
    with pytest.raises(FileExistsError):
        module.build(out, offline=True)
    assert (out / name).read_bytes() == existing
    assert list(out.iterdir()) == [out / name]


def test_manifest_lock_mismatch_fails_before_output_creation(tmp_path):
    source = tmp_path / "manifest-project"
    script = source / "scripts/build_wheel.py"
    script.parent.mkdir(parents=True)
    for name in ("pyproject.toml", "uv.lock"):
        shutil.copy2(ROOT / name, source / name)
    shutil.copy2(ROOT / "scripts/build_wheel.py", script)
    uv = shutil.which("uv")
    assert uv
    # Establish that this exact private unmodified project passes the real check.
    _run([uv, "lock", "--check", "--offline", "--project", str(source)], cwd=tmp_path)
    manifest = source / "pyproject.toml"
    content = manifest.read_text(encoding="utf-8")
    assert content.count('    "PySide6>=6.8,<7",') == 1
    manifest.write_text(
        content.replace(
            '    "PySide6>=6.8,<7",', '    "PySide6>=6.8,<7",\n    "idna==3.11",'
        ),
        encoding="utf-8",
    )
    out = tmp_path / "must-not-be-created"
    result = subprocess.run(
        [sys.executable, str(script), "--offline", "--out-dir", str(out)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 2
    assert "manifest and uv.lock are inconsistent" in result.stderr
    assert not out.exists()
