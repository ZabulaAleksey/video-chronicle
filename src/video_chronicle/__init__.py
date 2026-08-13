"""Installable entry-point package for Video Chronicle."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version


try:
    __version__ = version("video-chronicle")
except PackageNotFoundError:
    # Source-tree imports before installation still expose useful metadata.
    __version__ = "0.2.0"


__all__ = ["__version__"]
