"""Deterministic synthetic corpus and metrics for ``ffmpeg-scdet-v1``."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import platform
import sys
import time
from typing import Iterable

from .ports import CommandRunner
from .project import ResolvedTrim
from .scene import FfmpegScdetAdapter, SceneSource


CORPUS_VERSION = "scene-corpus-v1"


@dataclass(frozen=True, slots=True)
class CorpusItem:
    item_id: str
    filename: str
    rate: str
    duration_us: int
    hard_cuts_us: tuple[int, ...]
    negative_kind: str | None
    sha256: str


@dataclass(frozen=True, slots=True)
class CorpusManifest:
    version: str
    items: tuple[CorpusItem, ...]

    @property
    def media_duration_us(self) -> int:
        return sum(item.duration_us for item in self.items)

    @property
    def hard_cut_count(self) -> int:
        return sum(len(item.hard_cuts_us) for item in self.items)

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, indent=2) + "\n"


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    corpus_version: str
    ffmpeg_identity: str
    python_version: str
    platform: str
    precision: float
    recall: float
    f1: float
    negative_false_positives_per_minute: float
    p95_boundary_error_us: int
    wall_seconds: float
    media_seconds: float
    wall_media_ratio: float
    deterministic_runs: int
    suggestions_identical: bool
    continue_passed: bool
    criteria: dict[str, bool]

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, indent=2) + "\n"

    def to_markdown(self) -> str:
        state = "CONTINUE" if self.continue_passed else "DROP"
        return (
            "# Stage 12 FFmpeg scene benchmark\n\n"
            f"Decision: **{state}**\n\n"
            f"- Corpus: `{self.corpus_version}`\n"
            f"- FFmpeg: `{self.ffmpeg_identity}`\n"
            f"- Precision / recall / F1: `{self.precision:.6f}` / `{self.recall:.6f}` / `{self.f1:.6f}`\n"
            f"- Negative FP/min: `{self.negative_false_positives_per_minute:.6f}`\n"
            f"- p95 boundary error: `{self.p95_boundary_error_us} us`\n"
            f"- Wall/media: `{self.wall_seconds:.6f}s / {self.media_seconds:.6f}s = {self.wall_media_ratio:.6f}`\n"
            f"- Timestamp determinism: `{self.deterministic_runs}/3`, identical=`{str(self.suggestions_identical).lower()}`\n"
            f"- Environment: Python `{self.python_version}`, `{self.platform}`\n"
        )


def generate_corpus(root: Path, ffmpeg: str, runner: CommandRunner) -> CorpusManifest:
    root.mkdir(parents=True, exist_ok=True)
    items: list[CorpusItem] = []
    rates = (("24", 30), ("25", 32), ("30000/1001", 38), ("60", 75))
    colors = ("black", "white", "red", "blue")
    for index, (rate_text, segment_frames) in enumerate(rates):
        rate = Fraction(rate_text)
        filename = f"hard_{index}_{rate.numerator}_{rate.denominator}.mp4"
        path = root / filename
        inputs: list[str] = []
        filters: list[str] = []
        for color_index, color in enumerate(colors):
            inputs.extend(["-f", "lavfi", "-i", f"color=c={color}:s=160x90:r={rate_text}"])
            filters.append(
                f"[{color_index}:v]trim=end_frame={segment_frames},setpts=PTS-STARTPTS[v{color_index}]"
            )
        concat_inputs = "".join(f"[v{i}]" for i in range(len(colors)))
        filter_complex = ";".join(filters) + f";{concat_inputs}concat=n=4:v=1:a=0,format=yuv420p[v]"
        _encode(
            runner,
            [ffmpeg, "-hide_banner", "-loglevel", "error", *inputs, "-filter_complex", filter_complex, "-map", "[v]", "-an", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18", "-map_metadata", "-1", "-movflags", "+faststart", "-y", str(path)],
        )
        boundaries = tuple(
            _fraction_us(Fraction(segment_frames * boundary, 1) / rate)
            for boundary in (1, 2, 3)
        )
        duration_us = _fraction_us(Fraction(segment_frames * 4, 1) / rate)
        items.append(CorpusItem(f"hard-{index}", filename, rate_text, duration_us, boundaries, None, _sha256(path)))

    negative_specs = (
        ("no-cut", "color=c=gray:s=160x90:r=30:d=2", "no-cut"),
        ("fade", "color=c=white:s=160x90:r=30:d=2,fade=t=in:st=0:d=2", "fade/dissolve"),
    )
    for item_id, source_filter, kind in negative_specs:
        path = root / f"{item_id}.mp4"
        _encode(runner, [ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", source_filter, "-an", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18", "-map_metadata", "-1", "-y", str(path)])
        items.append(CorpusItem(item_id, path.name, "30", 2_000_000, (), kind, _sha256(path)))

    flash = root / "flash.mp4"
    flash_filters = (
        "[0:v]trim=end_frame=30,setpts=PTS-STARTPTS[v0];"
        "[1:v]trim=end_frame=1,setpts=PTS-STARTPTS[v1];"
        "[2:v]trim=end_frame=29,setpts=PTS-STARTPTS[v2];"
        "[v0][v1][v2]concat=n=3:v=1:a=0,format=yuv420p[v]"
    )
    _encode(runner, [ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=gray:s=160x90:r=30", "-f", "lavfi", "-i", "color=c=#999999:s=160x90:r=30", "-f", "lavfi", "-i", "color=c=gray:s=160x90:r=30", "-filter_complex", flash_filters, "-map", "[v]", "-an", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18", "-map_metadata", "-1", "-y", str(flash)])
    items.append(CorpusItem("flash", flash.name, "30", 2_000_000, (), "flash", _sha256(flash)))

    manifest = CorpusManifest(CORPUS_VERSION, tuple(items))
    if manifest.media_duration_us < 20_000_000 or manifest.hard_cut_count < 12:
        raise RuntimeError("synthetic corpus does not satisfy its minimum coverage")
    return manifest


def run_benchmark(
    root: Path,
    manifest: CorpusManifest,
    ffmpeg: str,
    runner: CommandRunner,
    *,
    runs: int = 3,
) -> BenchmarkReport:
    if runs != 3:
        raise ValueError("the approved determinism gate requires exactly three runs")
    for item in manifest.items:
        if _sha256(root / item.filename) != item.sha256:
            raise RuntimeError(f"corpus identity mismatch: {item.filename}")
    adapter = FfmpegScdetAdapter(ffmpeg, runner=runner)
    all_runs: list[dict[str, tuple[tuple[int, float], ...]]] = []
    first_wall = 0.0
    for run_index in range(runs):
        started = time.perf_counter()
        detected: dict[str, tuple[tuple[int, float], ...]] = {}
        for item in manifest.items:
            suggestions = adapter.detect(
                SceneSource(item.item_id, (root / item.filename).resolve()),
                ResolvedTrim(0, item.duration_us),
            )
            detected[item.item_id] = tuple(
                (suggestion.timestamp_us, suggestion.score)
                for suggestion in suggestions
            )
        elapsed = time.perf_counter() - started
        if run_index == 0:
            first_wall = elapsed
        all_runs.append(detected)
    identical = all(run == all_runs[0] for run in all_runs[1:])
    tp = fp = fn = 0
    errors: list[int] = []
    negative_fp = 0
    negative_duration_us = 0
    by_id = {item.item_id: item for item in manifest.items}
    for item_id, detected_values in all_runs[0].items():
        item = by_id[item_id]
        detected = tuple(timestamp for timestamp, _score in detected_values)
        if item.negative_kind is not None:
            negative_fp += len(detected)
            negative_duration_us += item.duration_us
            fp += len(detected)
            continue
        rate = Fraction(item.rate)
        tolerance = max(_fraction_us(Fraction(1, 1) / rate), 50_000)
        matched, unmatched_detected, unmatched_truth, matched_errors = _maximum_match(
            detected, item.hard_cuts_us, tolerance
        )
        tp += matched
        fp += unmatched_detected
        fn += unmatched_truth
        errors.extend(matched_errors)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    fp_per_min = negative_fp / (negative_duration_us / 60_000_000) if negative_duration_us else 0.0
    p95 = _percentile95(errors)
    media_seconds = manifest.media_duration_us / 1_000_000
    strict_frame_us = min(
        _fraction_us(Fraction(1, 1) / Fraction(item.rate))
        for item in manifest.items
    )
    criteria = {
        "precision": precision >= 0.95,
        "recall": recall >= 0.90,
        "f1": f1 >= 0.92,
        "negative_fp_per_min": fp_per_min <= 0.20,
        "p95_error": p95 <= strict_frame_us,
        "determinism": identical,
        "runtime": first_wall <= max(0.75 * media_seconds, 5.0),
    }
    version = runner([ffmpeg, "-version"], "FFmpeg identity failed", timeout=15, max_output_bytes=1024 * 1024).stdout.splitlines()[0]
    return BenchmarkReport(
        manifest.version,
        version,
        platform.python_version(),
        platform.platform(),
        precision,
        recall,
        f1,
        fp_per_min,
        p95,
        first_wall,
        media_seconds,
        first_wall / media_seconds,
        runs,
        identical,
        all(criteria.values()),
        criteria,
    )


def _encode(runner: CommandRunner, command: list[str]) -> None:
    runner(command, "synthetic scene corpus generation failed", timeout=60, max_output_bytes=1024 * 1024)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fraction_us(value: Fraction) -> int:
    return (value.numerator * 1_000_000 + value.denominator // 2) // value.denominator


def _maximum_match(
    detected: Iterable[int], truth: Iterable[int], tolerance: int
) -> tuple[int, int, int, list[int]]:
    detected_tuple = tuple(sorted(detected))
    truth_tuple = tuple(sorted(truth))
    actual_index = expected_index = 0
    errors: list[int] = []
    # For ordered points on a line, matching the earliest currently compatible
    # pair is maximum-cardinality: a point that is already too early cannot
    # match any later point on the other side.
    while actual_index < len(detected_tuple) and expected_index < len(truth_tuple):
        actual = detected_tuple[actual_index]
        expected = truth_tuple[expected_index]
        if abs(actual - expected) <= tolerance:
            errors.append(abs(actual - expected))
            actual_index += 1
            expected_index += 1
        elif actual < expected - tolerance:
            actual_index += 1
        else:
            expected_index += 1
    return len(errors), len(detected_tuple) - len(errors), len(truth_tuple) - len(errors), errors


def _percentile95(values: list[int]) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = max(0, (95 * len(ordered) + 99) // 100 - 1)
    return ordered[index]
