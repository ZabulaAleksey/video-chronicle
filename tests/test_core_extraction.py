from __future__ import annotations

import os
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_legacy_module_reexports_canonical_pipeline_objects() -> None:
    import join_media
    from video_chronicle import pipeline

    assert join_media is pipeline


def test_core_boundaries_import_without_qt() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "from video_chronicle.domain import ExportRequest, MediaItem; "
                "from video_chronicle.ports import CommandRunner, PipelinePorts; "
                "from video_chronicle.application import execute_export, plan_export; "
                "assert 'PySide6' not in sys.modules"
            ),
        ],
        cwd=PROJECT_ROOT,
        env={"PYTHONPATH": str(PROJECT_ROOT / "src")},
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_cli_and_legacy_script_share_the_same_help_contract() -> None:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(PROJECT_ROOT / "src")
    legacy = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "join_media.py"), "--help"],
        cwd=PROJECT_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    package = subprocess.run(
        [sys.executable, "-m", "video_chronicle", "--help"],
        cwd=PROJECT_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert legacy.returncode == package.returncode == 0
    assert legacy.stdout == package.stdout


def test_plan_and_execution_use_injected_workspace_and_process_ports(
    tmp_path: Path,
) -> None:
    from video_chronicle.application import execute_plan, plan_export
    from video_chronicle.domain import ExportRequest, MediaItem
    from video_chronicle.ports import PipelinePorts

    input_dir = tmp_path / "input"
    input_dir.mkdir()
    source = input_dir / "20240101_000000.mp4"
    source.write_bytes(b"source")
    output = tmp_path / "result.mp4"
    workspace = tmp_path / "injected-workspace"
    calls: list[str] = []

    request = ExportRequest(
        input_dir=input_dir,
        output=output,
        error_log=tmp_path / "errors.log",
        ffmpeg="ffmpeg",
        ffprobe="ffprobe",
        font_file=None,
        crf=20,
        preset="medium",
        overwrite=False,
        keep_work=False,
    )

    def runner(command, context, **kwargs):
        calls.append("runner")
        return subprocess.CompletedProcess(command, 0, "", "")

    def inspect(path, ffprobe, probe, command_runner):
        assert probe(path, ffprobe, command_runner)["streams"]
        return MediaItem(path, datetime(2024, 1, 1), False, True, "fixture")

    def normalize(item, destination, ffmpeg, font, crf, preset, command_runner):
        command_runner([ffmpeg], "normalize")
        destination.write_bytes(b"clip")

    def concatenate(clips, concat_file, temporary_output, ffmpeg, command_runner):
        command_runner([ffmpeg], "concat")
        temporary_output.write_bytes(b"movie")

    def create_workspace(parent):
        calls.append("create")
        workspace.mkdir()
        return workspace

    def cleanup_workspace(path):
        calls.append("cleanup")
        assert path == workspace

    ports = PipelinePorts(
        command_runner=runner,
        probe_media=lambda path, ffprobe, command_runner: {
            "streams": [{"codec_type": "video"}]
        },
        inspect_item=inspect,
        normalize_item=normalize,
        concatenate=concatenate,
        publish_output=lambda temporary, final, overwrite: temporary.replace(final),
        collect_source_paths=lambda input_dir, output, error_log: [source],
        create_workspace=create_workspace,
        cleanup_workspace=cleanup_workspace,
        validate_source=lambda input_dir, source: calls.append("validate"),
    )

    plan = plan_export(request, ports)
    assert plan.source_paths == (source,)
    assert execute_plan(plan, logging.getLogger("test.injected"), ports) == 0
    assert output.read_bytes() == b"movie"
    assert calls == [
        "validate",
        "create",
        "validate",
        "runner",
        "runner",
        "cleanup",
    ]


def test_error_log_cannot_alias_output_or_source(tmp_path: Path) -> None:
    from video_chronicle import pipeline

    input_dir = tmp_path / "input"
    input_dir.mkdir()
    source = input_dir / "source.mp4"
    source.write_bytes(b"do-not-truncate")
    output = tmp_path / "output.mp4"

    with pytest.raises(RuntimeError, match="different from the output"):
        pipeline.validate_error_log_path(input_dir, output, output)
    with pytest.raises(RuntimeError, match="source media"):
        pipeline.validate_error_log_path(input_dir, output, source)
    assert source.read_bytes() == b"do-not-truncate"


def test_symlink_log_and_source_are_rejected_or_skipped(tmp_path: Path) -> None:
    from video_chronicle import pipeline

    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"outside")
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    source_link = input_dir / "linked.mp4"
    log_link = tmp_path / "errors.log"
    try:
        source_link.symlink_to(outside)
        log_link.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")

    assert pipeline.collect_source_paths(
        input_dir, tmp_path / "output.mp4", tmp_path / "real.log"
    ) == []
    with pytest.raises(RuntimeError, match="symlink or reparse"):
        pipeline.validate_error_log_path(
            input_dir, tmp_path / "output.mp4", log_link
        )


def test_concat_manifest_rejects_control_characters(tmp_path: Path) -> None:
    from video_chronicle import pipeline

    with pytest.raises(RuntimeError, match="control characters"):
        pipeline.concatenate(
            [tmp_path / "clip\nfile 'outside.mp4'.mp4"],
            tmp_path / "concat.txt",
            tmp_path / "building.mp4",
            "ffmpeg",
            lambda *args, **kwargs: None,
        )


def test_command_runner_enforces_output_limit_while_process_runs() -> None:
    from video_chronicle import pipeline

    with pytest.raises(pipeline.MediaError, match="output exceeded 1024 bytes"):
        pipeline.run_command(
            [
                sys.executable,
                "-c",
                "import sys; sys.stdout.buffer.write(b'x' * 65536)",
            ],
            "noisy tool",
            timeout=10,
            max_output_bytes=1024,
        )
