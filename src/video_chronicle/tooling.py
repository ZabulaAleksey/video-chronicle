"""Discovery and bounded Windows bootstrap for external encoding tools."""

from __future__ import annotations

import os
import ctypes
import ntpath
import shutil
import sys
import uuid
import subprocess
from pathlib import Path
from typing import Callable, Mapping, MutableMapping


FFMPEG_WINGET_ID = "Gyan.FFmpeg"
FFMPEG_WINGET_VERSION = "9.0.1"
_APP_EXEC_LINK_REPARSE_TAG = 0x8000001B
_WINGET_PACKAGE_FAMILY = "Microsoft.DesktopAppInstaller_8wekyb3d8bbwe"
_MAX_PACKAGE_ID_CHARS = 1024
_MAX_PROCESS_IMAGE_CHARS = 32768
_TOOL_ENVIRONMENT = {
    "ffmpeg": "VIDEO_CHRONICLE_FFMPEG",
    "ffprobe": "VIDEO_CHRONICLE_FFPROBE",
}


def _portable_encoding_bundle(values: Mapping[str, str]) -> dict[str, str]:
    """Resolve the global DEV pair only when both canonical files exist."""

    tools_root = values.get("DEV_TOOLS")
    if not tools_root and values.get("DEV_ROOT"):
        tools_root = str(Path(values["DEV_ROOT"]) / "tools")
    if not tools_root:
        return {}
    bin_root = Path(tools_root) / "ffmpeg" / "bin"
    pair = {name: bin_root / f"{name}.exe" for name in _TOOL_ENVIRONMENT}
    try:
        if all(path.is_file() for path in pair.values()):
            return {name: str(path.resolve()) for name, path in pair.items()}
    except OSError:
        pass
    return {}


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
    portable = _portable_encoding_bundle(values)
    if portable:
        candidates.append(portable[tool_name])
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
    """Return only the OS-known per-user WinGet app-execution alias path.

    ``environ`` is retained for source compatibility, but its PATH and
    LOCALAPPDATA values are intentionally not authority for an installer.
    """

    del environ
    if os.name != "nt":
        return None
    try:
        candidate = _known_local_app_data() / "Microsoft" / "WindowsApps" / "winget.exe"
        info = candidate.lstat()
    except (OSError, RuntimeError, ValueError):
        return None
    attributes = getattr(info, "st_file_attributes", 0)
    reparse_tag = getattr(info, "st_reparse_tag", None)
    if not attributes & 0x400 or reparse_tag != _APP_EXEC_LINK_REPARSE_TAG:
        return None
    # Keep the lexical alias path. Resolving it would follow the app alias and
    # discard the exact candidate whose actual process identity is gated below.
    return str(candidate)


def _known_local_app_data() -> Path:
    """Read FOLDERID_LocalAppData from the Windows shell, without env input."""

    if os.name != "nt":
        raise OSError("Windows known folders are unavailable")

    class GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", ctypes.c_uint32),
            ("Data2", ctypes.c_uint16),
            ("Data3", ctypes.c_uint16),
            ("Data4", ctypes.c_ubyte * 8),
        ]

    folder_id = uuid.UUID("F1B32785-6FBA-4FCF-9D55-7B8E7F157091")
    guid = GUID.from_buffer_copy(folder_id.bytes_le)
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    ole32 = ctypes.WinDLL("ole32", use_last_error=True)
    shell32.SHGetKnownFolderPath.argtypes = (
        ctypes.POINTER(GUID),
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_wchar_p),
    )
    shell32.SHGetKnownFolderPath.restype = ctypes.c_long
    ole32.CoTaskMemFree.argtypes = (ctypes.c_void_p,)
    ole32.CoTaskMemFree.restype = None
    result = ctypes.c_wchar_p()
    status = shell32.SHGetKnownFolderPath(
        ctypes.byref(guid), 0, None, ctypes.byref(result)
    )
    if status != 0 or not result.value:
        raise OSError("LocalAppData known-folder lookup failed")
    try:
        return Path(result.value)
    finally:
        ole32.CoTaskMemFree(ctypes.cast(result, ctypes.c_void_p))


def admit_winget_process(process: subprocess.Popen[bytes]) -> None:
    """Admit WinGet only after checking package and image identity by handle."""

    if os.name != "nt":
        raise OSError("WinGet process admission is Windows-only")
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    uint_ptr = ctypes.POINTER(wintypes.UINT)
    wchar_ptr = ctypes.POINTER(wintypes.WCHAR)
    get_package_full_name = kernel32.GetPackageFullName
    get_package_full_name.argtypes = (wintypes.HANDLE, uint_ptr, wchar_ptr)
    get_package_full_name.restype = wintypes.LONG
    family_from_full_name = kernel32.PackageFamilyNameFromFullName
    family_from_full_name.argtypes = (wintypes.LPCWSTR, uint_ptr, wchar_ptr)
    family_from_full_name.restype = wintypes.LONG
    get_package_path = kernel32.GetPackagePathByFullName
    get_package_path.argtypes = (wintypes.LPCWSTR, uint_ptr, wchar_ptr)
    get_package_path.restype = wintypes.LONG
    query_image = kernel32.QueryFullProcessImageNameW
    query_image.argtypes = (
        wintypes.HANDLE,
        wintypes.DWORD,
        wchar_ptr,
        uint_ptr,
    )
    query_image.restype = wintypes.BOOL

    handle = wintypes.HANDLE(int(process._handle))  # type: ignore[attr-defined]
    package_full_name = _read_package_string(
        lambda length, buffer: get_package_full_name(handle, length, buffer)
    )
    package_family = _read_package_string(
        lambda length, buffer: family_from_full_name(
            package_full_name, length, buffer
        )
    )
    if package_family.casefold() != _WINGET_PACKAGE_FAMILY.casefold():
        raise OSError("WinGet package family is not admitted")
    package_root = _read_package_string(
        lambda length, buffer: get_package_path(package_full_name, length, buffer)
    )
    image_buffer = ctypes.create_unicode_buffer(_MAX_PROCESS_IMAGE_CHARS)
    image_length = wintypes.DWORD(_MAX_PROCESS_IMAGE_CHARS)
    if not query_image(handle, 0, image_buffer, ctypes.byref(image_length)):
        raise OSError("WinGet process image lookup failed")
    image_path = image_buffer.value
    if image_length.value <= 0 or image_length.value >= _MAX_PROCESS_IMAGE_CHARS:
        raise OSError("WinGet process image path is outside the accepted bound")

    root = ntpath.normcase(ntpath.normpath(package_root)).rstrip("\\")
    image = ntpath.normcase(ntpath.normpath(image_path))
    if (
        not root
        or ntpath.basename(image) != "winget.exe"
        or not image.startswith(root + "\\")
    ):
        raise OSError("WinGet process image is outside its registered package root")


def _read_package_string(call: Callable[..., int]) -> str:
    from ctypes import wintypes

    length = wintypes.UINT(0)
    status = call(ctypes.byref(length), None)
    if status != 122 or length.value <= 1 or length.value > _MAX_PACKAGE_ID_CHARS:
        raise OSError("Windows package identity lookup returned an invalid size")
    buffer = ctypes.create_unicode_buffer(length.value)
    status = call(ctypes.byref(length), buffer)
    if status != 0 or length.value <= 1 or length.value > len(buffer):
        raise OSError("Windows package identity lookup failed")
    value = buffer.value
    if not value or len(value) >= _MAX_PACKAGE_ID_CHARS:
        raise OSError("Windows package identity lookup returned malformed text")
    return value


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
