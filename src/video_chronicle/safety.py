"""Bounded local write-path and media admission policy."""

from __future__ import annotations

import os
import stat
from pathlib import Path, PureWindowsPath

MAX_SOURCE_ITEMS = 4096
MAX_SOURCE_BYTES = 64 * 1024**3
MAX_TOTAL_SOURCE_BYTES = 256 * 1024**3
MAX_SOURCE_DURATION_US = 7 * 24 * 60 * 60 * 1_000_000
MAX_DERIVED_BYTES = 64 * 1024**3
DEFAULT_TOOL_TIMEOUT_SECONDS = 30 * 60.0


def validate_windows_write_name(value: str) -> None:
    """Reject Windows device names, ADS and normalization aliases lexically."""
    windows = PureWindowsPath(value)
    if windows.drive and not windows.root:
        raise RuntimeError("write path must not be drive-relative")
    reserved = {"con", "prn", "aux", "nul"}
    reserved.update(f"{prefix}{suffix}" for prefix in ("com", "lpt") for suffix in "123456789¹²³")
    for component in windows.parts:
        if component == windows.anchor:
            continue
        basename = component.rstrip(" .").split(".", 1)[0].casefold()
        if ":" in component or basename in reserved or component.endswith((" ", ".")):
            raise RuntimeError(
                "write path contains a reserved Windows name or alternate data stream"
            )


def validate_local_write_path(path: Path) -> None:
    expanded = path.expanduser()
    text = str(expanded)
    if text.startswith(("\\\\", "//")) or "\x00" in text:
        raise RuntimeError("write path must not be UNC or a device path")
    if os.name == "nt":
        validate_windows_write_name(text)
    absolute = expanded.absolute()
    for candidate in (absolute, *absolute.parents):
        try:
            info = candidate.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(
            stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0
        ):
            raise RuntimeError("write path traverses a symlink or reparse point")
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetDriveTypeW.argtypes = (wintypes.LPCWSTR,)
        kernel32.GetDriveTypeW.restype = wintypes.UINT
        if kernel32.GetDriveTypeW(absolute.anchor) not in {2, 3}:
            raise RuntimeError("write path must use a local fixed or removable drive")


def validate_source_size(path: Path) -> int:
    size = path.stat().st_size
    if size > MAX_SOURCE_BYTES:
        raise ValueError("source exceeds the 64 GiB file budget")
    return size


def validate_source_duration(duration_us: int | None) -> None:
    if duration_us is not None and duration_us > MAX_SOURCE_DURATION_US:
        raise ValueError("source exceeds the seven-day duration budget")
