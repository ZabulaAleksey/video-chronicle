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


def test_winget_ffmpeg_install_is_pinned_user_scope_list_argv() -> None:
    arguments = tooling.winget_ffmpeg_install_arguments()

    assert arguments[:4] == ["install", "--exact", "--id", "Gyan.FFmpeg"]
    assert arguments[arguments.index("--version") + 1] == "9.0.1"
    assert arguments[arguments.index("--scope") + 1] == "user"
    assert "--accept-package-agreements" in arguments
    assert "--accept-source-agreements" in arguments
    assert "--disable-interactivity" in arguments
