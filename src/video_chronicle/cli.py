"""Console entry point delegating to the characterized legacy CLI."""

from __future__ import annotations


def main() -> int:
    """Run the canonical media pipeline without duplicating its behavior."""
    from join_media import main as legacy_main

    return legacy_main()

