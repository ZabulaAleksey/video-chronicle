#!/usr/bin/env python3
"""Legacy module alias and direct-source entry point for Video Chronicle."""

from __future__ import annotations

import sys
from pathlib import Path


def _load_pipeline():
    try:
        from video_chronicle import pipeline
    except ModuleNotFoundError as exc:
        if exc.name != "video_chronicle":
            raise
        source_root = Path(__file__).resolve().parent / "src"
        marker = source_root / "video_chronicle" / "__init__.py"
        if not marker.is_file():
            raise
        sys.path.insert(0, str(source_root))
        from video_chronicle import pipeline
    return pipeline


_pipeline = _load_pipeline()

if __name__ == "__main__":
    raise SystemExit(_pipeline.main())

# Importers receive the canonical module itself, so legacy monkeypatching and
# every historical public helper continue to target the single production path.
sys.modules[__name__] = _pipeline
