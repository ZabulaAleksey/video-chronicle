"""Lazy GUI entry point for the PySide6 application-service client."""

from __future__ import annotations


def main() -> int:
    """Run the canonical desktop application."""
    from video_chronicle_gui import main as gui_main

    return gui_main()
