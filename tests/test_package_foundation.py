from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tomllib
import venv
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_project_metadata_declares_dependencies_and_entry_points() -> None:
    metadata = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text("utf-8"))

    assert metadata["project"]["name"] == "video-chronicle"
    assert metadata["project"]["requires-python"] == ">=3.11"
    assert "PySide6>=6.8,<7" in metadata["project"]["dependencies"]
    assert "pytest>=8,<10" in metadata["project"]["optional-dependencies"]["dev"]
    assert metadata["project"]["scripts"]["video-chronicle"] == (
        "video_chronicle.cli:main"
    )
    assert metadata["project"]["gui-scripts"]["video-chronicle-gui"] == (
        "video_chronicle.gui:main"
    )


def test_source_package_imports_without_importing_gui_runtime() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import video_chronicle, sys; "
                "assert video_chronicle.__version__; "
                "assert 'PySide6' not in sys.modules"
            ),
        ],
        cwd=PROJECT_ROOT,
        env={"PYTHONPATH": str(PROJECT_ROOT / "src")},
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_cli_wrapper_delegates_to_application_service(monkeypatch: pytest.MonkeyPatch) -> None:
    from video_chronicle import cli

    input_dir = Path.cwd()
    monkeypatch.setattr(cli, "parse_args", lambda argv=None: type("Args", (), {
        "input_dir": input_dir,
        "output": input_dir / "result.mp4",
        "error_log": input_dir / "errors.log",
        "overlay": {
            "enabled": True,
            "format": "dd.MM.yy ddd",
            "position": "bottom-left",
            "horizontal_margin": 20,
            "vertical_margin": 20,
            "font_size": 72,
            "text_color": "#000000",
            "outline_color": "#FFFFFF",
            "outline_width": 4,
            "font_file": None,
        },
        "ffmpeg": "ffmpeg",
        "ffprobe": "ffprobe",
        "crf": 20,
        "preset": "medium",
        "overwrite": False,
        "keep_work": False,
    })())
    monkeypatch.setattr(cli.pipeline, "configure_logging", lambda path: object())
    monkeypatch.setattr(cli, "_build_request", lambda args: object())
    monkeypatch.setattr(cli, "execute_export", lambda request, logger: 17)

    assert cli.main() == 17


def test_gui_wrapper_delegates_lazily(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("PySide6")
    import video_chronicle_gui
    from video_chronicle import gui

    monkeypatch.setattr(video_chronicle_gui, "main", lambda: 23)

    assert gui.main() == 23


def test_current_checkout_wheel_installs_and_launchers_run(tmp_path: Path) -> None:
    source_tree = tmp_path / "source"
    source_tree.mkdir()
    for filename in (
        "README.md",
        "pyproject.toml",
        "join_media.py",
        "gui_contract.py",
        "video_chronicle_gui.py",
    ):
        shutil.copy2(PROJECT_ROOT / filename, source_tree / filename)
    shutil.copytree(PROJECT_ROOT / "src", source_tree / "src")

    wheel_dir = tmp_path / "wheel"
    wheel_dir.mkdir()
    build = subprocess.run(
        [
            sys._base_executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--no-build-isolation",
            "--no-cache-dir",
            "--wheel-dir",
            str(wheel_dir),
            ".",
        ],
        cwd=source_tree,
        check=False,
        capture_output=True,
        text=True,
    )
    assert build.returncode == 0, build.stdout + build.stderr
    wheel = next(wheel_dir.glob("video_chronicle-*.whl"))

    install_dir = tmp_path / "installed"
    venv.EnvBuilder(with_pip=True).create(install_dir)
    scripts_dir = install_dir / ("Scripts" if os.name == "nt" else "bin")
    python = scripts_dir / ("python.exe" if os.name == "nt" else "python")
    install = subprocess.run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--no-index",
            str(wheel),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert install.returncode == 0, install.stdout + install.stderr

    suffix = ".exe" if os.name == "nt" else ""
    cli = scripts_dir / f"video-chronicle{suffix}"
    cli_result = subprocess.run(
        [str(cli), "--help"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert cli_result.returncode == 0, cli_result.stderr
    assert "--input-dir" in cli_result.stdout

    gui_stub = tmp_path / "gui-stub"
    gui_stub.mkdir()
    (gui_stub / "video_chronicle_gui.py").write_text(
        "def main():\n    return 0\n",
        encoding="utf-8",
    )
    gui_env = os.environ.copy()
    gui_env["PYTHONPATH"] = str(gui_stub)
    gui = scripts_dir / f"video-chronicle-gui{suffix}"
    gui_result = subprocess.run(
        [str(gui)],
        env=gui_env,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert gui_result.returncode == 0, gui_result.stderr
