from __future__ import annotations

import importlib.metadata
import subprocess
import sys
import tomllib
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


def test_cli_wrapper_delegates_to_legacy_main(monkeypatch: pytest.MonkeyPatch) -> None:
    import join_media
    from video_chronicle import cli

    monkeypatch.setattr(join_media, "main", lambda: 17)

    assert cli.main() == 17


def test_gui_wrapper_delegates_lazily(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("PySide6")
    import video_chronicle_gui
    from video_chronicle import gui

    monkeypatch.setattr(video_chronicle_gui, "main", lambda: 23)

    assert gui.main() == 23


def test_installed_distribution_exposes_both_entry_points() -> None:
    try:
        distribution = importlib.metadata.distribution("video-chronicle")
    except importlib.metadata.PackageNotFoundError:
        pytest.skip("run after editable or wheel installation")

    entry_points = {
        (entry_point.group, entry_point.name): entry_point.value
        for entry_point in distribution.entry_points
    }
    assert entry_points[("console_scripts", "video-chronicle")] == (
        "video_chronicle.cli:main"
    )
    assert entry_points[("gui_scripts", "video-chronicle-gui")] == (
        "video_chronicle.gui:main"
    )
