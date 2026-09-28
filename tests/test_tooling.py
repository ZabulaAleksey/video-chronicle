from __future__ import annotations

from pathlib import Path

import pytest

from video_chronicle import tooling


def test_resolve_encoding_tool_prefers_explicit_environment_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configured = tmp_path / "trusted ffmpeg.exe"
    configured.write_bytes(b"tool")
    monkeypatch.setattr(tooling.shutil, "which", lambda *args, **kwargs: None)

    resolved = tooling.resolve_encoding_tool(
        "ffmpeg",
        {
            "VIDEO_CHRONICLE_FFMPEG": str(configured),
            "PATH": "",
        },
    )

    assert resolved == str(configured.resolve())


def test_resolve_encoding_tool_returns_absolute_path_from_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    discovered = tmp_path / "ffprobe.exe"
    discovered.write_bytes(b"tool")
    monkeypatch.setattr(
        tooling.shutil, "which", lambda *args, **kwargs: str(discovered)
    )

    assert tooling.resolve_encoding_tool("ffprobe", {"PATH": "tools"}) == str(
        discovered.resolve()
    )


def test_portable_dev_pair_precedes_host_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bin_root = tmp_path / "tools" / "ffmpeg" / "bin"
    bin_root.mkdir(parents=True)
    for name in ("ffmpeg", "ffprobe"):
        (bin_root / f"{name}.exe").write_bytes(b"fixture")
    host = tmp_path / "host-ffmpeg.exe"
    host.write_bytes(b"host")
    monkeypatch.setattr(tooling.shutil, "which", lambda *args, **kwargs: str(host))

    assert tooling.resolve_encoding_tools({"DEV_TOOLS": str(tmp_path / "tools"), "PATH": "host"}) == (
        str((bin_root / "ffmpeg.exe").resolve()),
        str((bin_root / "ffprobe.exe").resolve()),
    )


def test_incomplete_portable_pair_does_not_mix_with_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bin_root = tmp_path / "tools" / "ffmpeg" / "bin"
    bin_root.mkdir(parents=True)
    (bin_root / "ffmpeg.exe").write_bytes(b"fixture")
    monkeypatch.setattr(tooling.shutil, "which", lambda *args, **kwargs: None)

    assert tooling.resolve_encoding_tools({"DEV_TOOLS": str(tmp_path / "tools"), "PATH": ""}) == (None, None)


def test_winget_ffmpeg_install_is_pinned_user_scope_list_argv() -> None:
    arguments = tooling.winget_ffmpeg_install_arguments()

    assert arguments[:4] == ["install", "--exact", "--id", "Gyan.FFmpeg"]
    assert arguments[arguments.index("--version") + 1] == "9.0.1"
    assert arguments[arguments.index("--scope") + 1] == "user"
    assert "--accept-package-agreements" in arguments
    assert "--accept-source-agreements" in arguments
    assert "--disable-interactivity" in arguments
