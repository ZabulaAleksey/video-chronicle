"""Qt-free scene-suggestion contracts and FFmpeg ``scdet`` adapter."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import stat
import time
from typing import Protocol

from .domain import SourceFingerprint
from .ports import CommandRunner
from .project import ResolvedTrim


SCENE_DETECTOR = "ffmpeg-scdet-v1"
SCENE_THRESHOLD = 10.0
MAX_SCENE_OUTPUT_BYTES = 1024 * 1024
MAX_SUGGESTIONS = 4096


@dataclass(frozen=True, slots=True)
class SceneSource:
    item_id: str
    source_path: Path

    def __post_init__(self) -> None:
        if not isinstance(self.item_id, str) or not self.item_id or self.item_id.strip() != self.item_id:
            raise ValueError("item_id must be a non-empty trimmed string")
        if not isinstance(self.source_path, Path) or not self.source_path.is_absolute():
            raise ValueError("source_path must be an absolute pathlib.Path")


@dataclass(frozen=True, slots=True)
class CutSuggestion:
    item_id: str
    timestamp_us: int
    score: float
    detector: str
    threshold: float
    settings_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.item_id, str) or not self.item_id:
            raise ValueError("item_id must not be empty")
        if isinstance(self.timestamp_us, bool) or not isinstance(self.timestamp_us, int) or self.timestamp_us < 0:
            raise ValueError("timestamp_us must be a non-negative integer")
        if not isinstance(self.score, (int, float)) or not math.isfinite(float(self.score)):
            raise ValueError("score must be finite")
        if self.detector != SCENE_DETECTOR:
            raise ValueError("unsupported scene detector identity")
        if not math.isfinite(self.threshold) or self.threshold <= 0:
            raise ValueError("threshold must be finite and positive")
        if not re.fullmatch(r"[0-9a-f]{64}", self.settings_digest):
            raise ValueError("settings_digest must be lowercase SHA-256")


class SceneSuggestionPort(Protocol):
    def detect(
        self, source: SceneSource, resolved_trim: ResolvedTrim
    ) -> tuple[CutSuggestion, ...]: ...


class SceneDetectionError(RuntimeError):
    pass


class FfmpegScdetAdapter:
    """Detect scene boundaries without applying any edit to the project."""

    def __init__(
        self,
        ffmpeg: str,
        *,
        runner: CommandRunner | None = None,
        threshold: float = SCENE_THRESHOLD,
        timeout: float = 120.0,
    ) -> None:
        if not isinstance(ffmpeg, str) or not ffmpeg:
            raise ValueError("ffmpeg must be a selected executable string")
        if not math.isfinite(threshold) or threshold <= 0:
            raise ValueError("threshold must be finite and positive")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be finite and positive")
        if runner is None:
            from .pipeline import run_command

            runner = run_command
        self.ffmpeg = str(_resolve_safe_executable(ffmpeg))
        self.runner = runner
        self.threshold = float(threshold)
        self.timeout = float(timeout)

    def detect(
        self, source: SceneSource, resolved_trim: ResolvedTrim
    ) -> tuple[CutSuggestion, ...]:
        if not isinstance(source, SceneSource) or not isinstance(resolved_trim, ResolvedTrim):
            raise TypeError("detect requires SceneSource and ResolvedTrim")
        deadline = time.monotonic() + self.timeout
        _require_safe_regular_file(source.source_path)
        before = _capture_bounded_fingerprint(source.source_path, deadline)
        tool_before = _capture_bounded_fingerprint(Path(self.ffmpeg), deadline)
        tool_identity = self._tool_identity(deadline, tool_before)
        duration_us = resolved_trim.out_us - resolved_trim.in_us
        seconds = lambda value: format(Decimal(value) / Decimal(1_000_000), "f")
        filter_value = f"scdet=threshold={self.threshold:.1f}"
        command = [
            self.ffmpeg,
            "-hide_banner",
            "-loglevel",
            "info",
            "-ss",
            seconds(resolved_trim.in_us),
            "-i",
            str(source.source_path),
            "-t",
            seconds(duration_us),
            "-map",
            "0:v:0",
            "-an",
            "-vf",
            filter_value,
            "-f",
            "null",
            "-",
        ]
        result = self.runner(
            command,
            "FFmpeg scene detection failed",
            timeout=_remaining(deadline),
            max_output_bytes=MAX_SCENE_OUTPUT_BYTES,
        )
        after = _capture_bounded_fingerprint(source.source_path, deadline)
        if before != after:
            raise SceneDetectionError("source identity changed during scene detection")
        tool_after = _capture_bounded_fingerprint(Path(self.ffmpeg), deadline)
        if tool_before != tool_after:
            raise SceneDetectionError("FFmpeg executable identity changed during scene detection")
        digest = _settings_digest(
            before, resolved_trim, tool_identity, self.threshold
        )
        detected = _parse_scdet_output(result.stderr)
        suggestions: list[CutSuggestion] = []
        for filtered_us, score in detected:
            if score < self.threshold:
                raise SceneDetectionError("scdet reported a cut below the configured threshold")
            timestamp_us = resolved_trim.in_us + filtered_us
            if timestamp_us <= resolved_trim.in_us or timestamp_us >= resolved_trim.out_us:
                continue
            suggestions.append(
                CutSuggestion(
                    source.item_id,
                    timestamp_us,
                    score,
                    SCENE_DETECTOR,
                    self.threshold,
                    digest,
                )
            )
        suggestions.sort(key=lambda suggestion: (suggestion.timestamp_us, -suggestion.score))
        if len({suggestion.timestamp_us for suggestion in suggestions}) != len(suggestions):
            raise SceneDetectionError("FFmpeg returned duplicate scene timestamps")
        return tuple(suggestions)

    def _tool_identity(
        self, deadline: float, expected: SourceFingerprint
    ) -> str:
        result = self.runner(
            [self.ffmpeg, "-version"],
            "FFmpeg scene detector preflight failed",
            timeout=min(15.0, _remaining(deadline)),
            max_output_bytes=1024 * 1024,
        )
        first_line = result.stdout.splitlines()[0].strip() if result.stdout.splitlines() else ""
        if not first_line.startswith("ffmpeg version 9.0.1"):
            raise SceneDetectionError("ffmpeg-scdet-v1 requires FFmpeg 9.0.1")
        executable = Path(self.ffmpeg)
        actual = _capture_bounded_fingerprint(executable, deadline)
        if actual != expected:
            raise SceneDetectionError("FFmpeg executable changed during version preflight")
        executable_identity: object = {
            "path": str(executable),
            "size": actual.size,
            "mtime_ns": actual.mtime_ns,
            "sha256": actual.sha256,
        }
        return json.dumps(
            {"version": first_line, "executable": executable_identity},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )


def _parse_scdet_output(output: str) -> tuple[tuple[int, float], ...]:
    if not isinstance(output, str):
        raise TypeError("scene detector output must be text")
    result: list[tuple[int, float]] = []
    pattern = re.compile(
        r"lavfi\.scd\.score:\s*([^,\s]+),\s*lavfi\.scd\.time:\s*([^\s]+)\s*$"
    )
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if "lavfi.scd.score" not in line and "lavfi.scd.time" not in line:
            continue
        match = pattern.search(line)
        if match is None:
            raise SceneDetectionError("malformed scdet metadata line")
        try:
            score = float(match.group(1))
            timestamp = Decimal(match.group(2))
        except (ValueError, InvalidOperation) as exc:
            raise SceneDetectionError("invalid scdet numeric metadata") from exc
        if not math.isfinite(score) or score < 0 or not timestamp.is_finite() or timestamp < 0:
            raise SceneDetectionError("scdet metadata contains invalid numeric values")
        microseconds = int(
            (timestamp * Decimal(1_000_000)).quantize(
                Decimal(1), rounding=ROUND_HALF_UP
            )
        )
        result.append((microseconds, score))
        if len(result) > MAX_SUGGESTIONS:
            raise SceneDetectionError("scdet output exceeds 4096 suggestions")
    return tuple(result)


def _settings_digest(
    fingerprint: SourceFingerprint,
    trim: ResolvedTrim,
    tool_identity: str,
    threshold: float,
) -> str:
    fields = {
        "detector": SCENE_DETECTOR,
        "source": {
            "device": fingerprint.device,
            "inode": fingerprint.inode,
            "size": fingerprint.size,
            "mtime_ns": fingerprint.mtime_ns,
            "ctime_ns": fingerprint.ctime_ns,
            "sha256": fingerprint.sha256,
        },
        "trim": {"in_us": trim.in_us, "out_us": trim.out_us},
        "threshold": format(threshold, ".1f"),
        "tool": tool_identity,
    }
    encoded = json.dumps(fields, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _is_link_or_reparse(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return False
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def _checkpoint(deadline: float) -> None:
    from .execution import current_execution_context

    context = current_execution_context()
    if context is not None:
        context.checkpoint()
    if time.monotonic() >= deadline:
        raise SceneDetectionError("scene detection timed out while fingerprinting")


def _remaining(deadline: float) -> float:
    _checkpoint(deadline)
    return max(0.001, deadline - time.monotonic())


def _capture_bounded_fingerprint(path: Path, deadline: float) -> SourceFingerprint:
    _checkpoint(deadline)
    before = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            _checkpoint(deadline)
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    after = path.stat()
    fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
    if any(getattr(before, field) != getattr(after, field) for field in fields):
        raise SceneDetectionError(f"file identity changed while fingerprinting: {path}")
    return SourceFingerprint(
        device=after.st_dev,
        inode=after.st_ino,
        size=after.st_size,
        mtime_ns=after.st_mtime_ns,
        ctime_ns=after.st_ctime_ns,
        sha256=digest.hexdigest(),
    )


def _require_safe_regular_file(path: Path) -> None:
    candidate = path
    while candidate != candidate.parent:
        if candidate.exists() and _is_link_or_reparse(candidate):
            raise SceneDetectionError(f"scene source traverses symlink/reparse: {path}")
        candidate = candidate.parent
    if not path.is_file() or _is_link_or_reparse(path):
        raise SceneDetectionError(f"scene source is not a safe regular file: {path}")


def _resolve_safe_executable(value: str) -> Path:
    candidate = Path(value).expanduser()
    if candidate.is_absolute() or candidate.parent != Path("."):
        resolved_value = candidate
    else:
        found = shutil.which(value)
        if found is None:
            raise SceneDetectionError("selected FFmpeg executable is unavailable")
        resolved_value = Path(found)
    try:
        resolved = resolved_value.resolve(strict=True)
    except OSError as exc:
        raise SceneDetectionError("selected FFmpeg executable is unavailable") from exc
    _require_safe_regular_file(resolved_value)
    if not resolved.is_absolute():
        raise SceneDetectionError("FFmpeg executable did not resolve to an absolute path")
    return resolved


@dataclass(frozen=True, slots=True)
class OptionalSceneFeature:
    available: bool
    reason: str
    adapter: SceneSuggestionPort | None = None


def optional_scene_adapter(
    ffmpeg: str,
    environ: dict[str, str] | None = None,
    *,
    runner: CommandRunner | None = None,
) -> OptionalSceneFeature:
    values = os.environ if environ is None else environ
    if values.get("VIDEO_CHRONICLE_EXPERIMENTAL_SCENE", "off") != "ffmpeg-scdet":
        return OptionalSceneFeature(False, "scene experiment is disabled")
    try:
        adapter = FfmpegScdetAdapter(ffmpeg, runner=runner)
    except (OSError, SceneDetectionError):
        return OptionalSceneFeature(False, "selected FFmpeg executable is unavailable")
    return OptionalSceneFeature(True, "available", adapter)
