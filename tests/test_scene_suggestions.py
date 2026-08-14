from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess

import pytest

from video_chronicle.pipeline import run_command
from video_chronicle.application import experimental_scene_suggestions
from video_chronicle.execution import ExecutionContext, ExportCancelled, bind_execution_context
from video_chronicle.project import ResolvedTrim
from video_chronicle.scene import (
    FfmpegScdetAdapter,
    SceneDetectionError,
    SceneSource,
    _parse_scdet_output,
    optional_scene_adapter,
)
from video_chronicle.scene_benchmark import (
    BenchmarkReport,
    _maximum_match,
    generate_corpus,
    run_benchmark,
)


class _Runner:
    def __init__(self, output: str) -> None:
        self.output = output
        self.commands: list[list[str]] = []

    def __call__(self, command, context, *, timeout=None, max_output_bytes=0):
        self.commands.append(command)
        if command[-1] == "-version":
            return subprocess.CompletedProcess(command, 0, "ffmpeg version 9.0.1-test\n", "")
        return subprocess.CompletedProcess(command, 0, "", self.output)


def _source(tmp_path: Path) -> SceneSource:
    path = (tmp_path / "source.mp4").resolve()
    path.write_bytes(b"not decoded by the stub")
    return SceneSource("item-scene", path)


def _tool(tmp_path: Path) -> str:
    path = (tmp_path / "ffmpeg-test.exe").resolve()
    path.write_bytes(b"trusted test executable identity")
    return str(path)


def test_scdet_nonzero_trim_maps_to_source_relative_time_and_rejects_endpoints(tmp_path: Path) -> None:
    runner = _Runner(
        "noise\n"
        "[Parsed_scdet_0 @ abc] lavfi.scd.score: 42.5, lavfi.scd.time: 0\n"
        "[Parsed_scdet_0 @ abc] lavfi.scd.score: 50, lavfi.scd.time: 0.25\n"
        "[Parsed_scdet_0 @ abc] lavfi.scd.score: 55, lavfi.scd.time: 1\n"
    )
    adapter = FfmpegScdetAdapter(_tool(tmp_path), runner=runner)
    suggestions = adapter.detect(_source(tmp_path), ResolvedTrim(2_000_000, 3_000_000))
    assert [(value.timestamp_us, value.score) for value in suggestions] == [(2_250_000, 50.0)]
    detect_command = runner.commands[1]
    assert detect_command[detect_command.index("-ss") + 1] == "2"
    assert detect_command[detect_command.index("-t") + 1] == "1"
    assert "scdet=threshold=10.0" in detect_command
    assert all(value.detector == "ffmpeg-scdet-v1" for value in suggestions)


def test_scene_settings_digest_changes_with_trim_threshold_source_and_tool(tmp_path: Path) -> None:
    source = _source(tmp_path)
    runner = _Runner("[scdet @ x] lavfi.scd.score: 20, lavfi.scd.time: 0.5\n")
    tool = _tool(tmp_path)
    first = FfmpegScdetAdapter(tool, runner=runner).detect(source, ResolvedTrim(0, 1_000_000))[0]
    second = FfmpegScdetAdapter(tool, runner=runner, threshold=11).detect(source, ResolvedTrim(0, 1_000_000))[0]
    third = FfmpegScdetAdapter(tool, runner=runner).detect(source, ResolvedTrim(100_000, 1_100_000))[0]
    source.source_path.write_bytes(b"changed")
    fourth = FfmpegScdetAdapter(tool, runner=runner).detect(source, ResolvedTrim(0, 1_000_000))[0]
    assert len({first.settings_digest, second.settings_digest, third.settings_digest, fourth.settings_digest}) == 4


@pytest.mark.parametrize(
    "output",
    [
        "[scdet @ x] lavfi.scd.score: nope, lavfi.scd.time: 1",
        "[scdet @ x] lavfi.scd.score: nan, lavfi.scd.time: 1",
        "[scdet @ x] lavfi.scd.score: 20",
        "[scdet @ x] lavfi.scd.time: 1",
    ],
)
def test_malformed_or_nonfinite_scdet_output_is_rejected(output: str) -> None:
    with pytest.raises(SceneDetectionError):
        _parse_scdet_output(output)


def test_benchmark_matching_is_maximum_cardinality_not_nearest_pair_greedy() -> None:
    assert _maximum_match((0, 10), (9, 20), 10)[:3] == (2, 0, 0)


def test_scene_flag_is_default_off_and_missing_tool_is_cleanly_unavailable() -> None:
    assert optional_scene_adapter("missing-ffmpeg", {}).available is False
    assert experimental_scene_suggestions("missing-ffmpeg", {}).available is False
    feature = optional_scene_adapter(
        "definitely-missing-video-chronicle-ffmpeg",
        {"VIDEO_CHRONICLE_EXPERIMENTAL_SCENE": "ffmpeg-scdet"},
    )
    assert feature.available is False
    assert "unavailable" in feature.reason


def test_scene_fingerprinting_honors_existing_cancellation_before_tool_start(tmp_path: Path) -> None:
    runner = _Runner("[scdet @ x] lavfi.scd.score: 20, lavfi.scd.time: 0.5\n")
    adapter = FfmpegScdetAdapter(_tool(tmp_path), runner=runner)
    context = ExecutionContext()
    context.start()
    assert context.request_cancel()
    with bind_execution_context(context), pytest.raises(ExportCancelled):
        adapter.detect(_source(tmp_path), ResolvedTrim(0, 1_000_000))
    assert runner.commands == []


def _local_ffmpeg() -> str | None:
    configured = os.environ.get("VIDEO_CHRONICLE_FFMPEG")
    candidates = [configured, "ffmpeg1/bin/ffmpeg.exe", "ffmpeg"]
    for value in candidates:
        if not value:
            continue
        candidate = Path(value)
        if candidate.is_file():
            resolved = str(candidate.resolve())
        else:
            resolved = shutil.which(value)
        if not resolved:
            continue
        identity = subprocess.run([resolved, "-version"], capture_output=True, text=True, check=False).stdout.splitlines()
        if identity and re.search(r"\bversion\s+9\.0\.1\b", identity[0]):
            return resolved
    return None


def test_real_ffmpeg_synthetic_benchmark_reaches_approved_continue_criteria(tmp_path: Path) -> None:
    ffmpeg = _local_ffmpeg()
    if ffmpeg is None:
        pytest.skip("FFmpeg 9.0.1 is unavailable")
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first = generate_corpus(first_root, ffmpeg, run_command)
    second = generate_corpus(second_root, ffmpeg, run_command)
    assert first.to_json() == second.to_json()
    checked_manifest = json.loads(
        Path("benchmarks/stage12-corpus-manifest.json").read_text(encoding="utf-8")
    )
    assert json.loads(first.to_json()) == checked_manifest
    assert first.media_duration_us >= 20_000_000
    assert first.hard_cut_count >= 12
    assert {item.rate for item in first.items} >= {"24", "25", "30000/1001", "60"}
    assert {item.negative_kind for item in first.items} >= {"no-cut", "fade/dissolve", "flash"}
    report = run_benchmark(first_root, first, ffmpeg, run_command)
    assert report.continue_passed, report.to_json()
    assert report.precision >= 0.95
    assert report.recall >= 0.90
    assert report.f1 >= 0.92
    assert report.negative_false_positives_per_minute <= 0.20
    assert report.suggestions_identical and report.deterministic_runs == 3
    assert "Decision: **CONTINUE**" in report.to_markdown()
    checked_report = json.loads(
        Path("benchmarks/stage12-ffmpeg-9.0.1.json").read_text(encoding="utf-8")
    )
    assert checked_report["continue_passed"] is True
    assert checked_report["criteria"] == report.criteria
    for field in (
        "corpus_version",
        "ffmpeg_identity",
        "media_seconds",
        "precision",
        "recall",
        "f1",
        "negative_false_positives_per_minute",
        "p95_boundary_error_us",
        "deterministic_runs",
        "suggestions_identical",
    ):
        assert checked_report[field] == getattr(report, field)
    assert checked_report["wall_seconds"] <= max(
        0.75 * checked_report["media_seconds"], 5.0
    )
    assert checked_report["wall_media_ratio"] == pytest.approx(
        checked_report["wall_seconds"] / checked_report["media_seconds"]
    )
    markdown = Path("benchmarks/stage12-ffmpeg-9.0.1.md").read_text(encoding="utf-8")
    assert markdown == BenchmarkReport(**checked_report).to_markdown()


def test_real_ffmpeg_nonzero_trim_timestamp_is_source_relative(tmp_path: Path) -> None:
    ffmpeg = _local_ffmpeg()
    if ffmpeg is None:
        pytest.skip("FFmpeg 9.0.1 is unavailable")
    manifest = generate_corpus(tmp_path, ffmpeg, run_command)
    item = manifest.items[0]
    suggestions = FfmpegScdetAdapter(ffmpeg, runner=run_command).detect(
        SceneSource(item.item_id, (tmp_path / item.filename).resolve()),
        ResolvedTrim(1_000_000, 3_000_000),
    )
    assert tuple(value.timestamp_us for value in suggestions) == (1_250_000, 2_500_000)
