"""Discovery and bounded Windows bootstrap for external encoding tools."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Mapping, MutableMapping


FFMPEG_WINGET_ID = "Gyan.FFmpeg"
FFMPEG_WINGET_VERSION = "9.0.1"
_TOOL_ENVIRONMENT = {
    "ffmpeg": "VIDEO_CHRONICLE_FFMPEG",
    "ffprobe": "VIDEO_CHRONICLE_FFPROBE",
}


def resolve_encoding_tool(
    tool_name: str,
    environ: Mapping[str, str] | None = None,
) -> str | None:
    """Resolve a configured or PATH tool to an absolute regular-file path."""

    if tool_name not in _TOOL_ENVIRONMENT:
        raise ValueError(f"unsupported encoding tool: {tool_name}")
    values = os.environ if environ is None else environ
    configured = values.get(_TOOL_ENVIRONMENT[tool_name])
    candidates = [configured] if configured else []
    discovered = shutil.which(tool_name, path=values.get("PATH"))
    if discovered:
        candidates.append(discovered)
    for candidate in candidates:
        path = Path(candidate).expanduser()
        try:
            if path.is_file():
                return str(path.resolve())
        except OSError:
            continue
    return None


def resolve_encoding_tools(
    environ: Mapping[str, str] | None = None,
) -> tuple[str | None, str | None]:
    return (
        resolve_encoding_tool("ffmpeg", environ),
        resolve_encoding_tool("ffprobe", environ),
    )


def winget_ffmpeg_install_arguments() -> list[str]:
    """Return the pinned, non-interactive user-scope WinGet argv."""

    return [
        "install",
        "--exact",
        "--id",
        FFMPEG_WINGET_ID,
        "--version",
        FFMPEG_WINGET_VERSION,
        "--source",
        "winget",
        "--scope",
        "user",
        "--accept-package-agreements",
        "--accept-source-agreements",
        "--disable-interactivity",
    ]


def resolve_winget(environ: Mapping[str, str] | None = None) -> str | None:
    values = os.environ if environ is None else environ
    discovered = shutil.which("winget", path=values.get("PATH"))
    if discovered:
        return str(Path(discovered).resolve())
    local = values.get("LOCALAPPDATA")
    if not local:
        return None
    candidate = Path(local) / "Microsoft" / "WindowsApps" / "winget.exe"
    return str(candidate.resolve()) if candidate.is_file() else None


def refresh_windows_process_path(
    environ: MutableMapping[str, str] | None = None,
) -> str:
    """Refresh PATH from the Windows registry after a package install."""

    target = os.environ if environ is None else environ
    if sys.platform != "win32":
        return target.get("PATH", "")

    import winreg

    paths: list[str] = []
    locations = (
        (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
        (winreg.HKEY_CURRENT_USER, r"Environment"),
    )
    for hive, key_name in locations:
        try:
            with winreg.OpenKey(hive, key_name) as key:
                value, _ = winreg.QueryValueEx(key, "Path")
        except OSError:
            continue
        if value:
            paths.append(os.path.expandvars(str(value)))
    if paths:
        target["PATH"] = os.pathsep.join(paths)
    return target.get("PATH", "")
