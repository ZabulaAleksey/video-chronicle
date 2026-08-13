"""GUI entry point delegating to the existing PySide6 application."""

from __future__ import annotations


def main() -> int:
    """Run the canonical desktop application."""
    from video_chronicle_gui import main as legacy_main

    return legacy_main()
