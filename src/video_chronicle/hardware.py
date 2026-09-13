"""FFmpeg hardware capability probe and promotion-quality benchmark."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import hashlib
import json
import math
from pathlib import Path
import platform
import re
import shutil
import stat
import time

from .ports import CommandRunner


class HardwareProbeError(RuntimeError):
    pass


class EncoderBackend(str, Enum):
    SOFTWARE = "software"
    NVIDIA = "nvidia"
    INTEL_QSV = "intel-qsv"
    AMD_AMF = "amd-amf"


_CODECS = {
    EncoderBackend.SOFTWARE: "libx264",
    EncoderBackend.NVIDIA: "h264_nvenc",
    EncoderBackend.INTEL_QSV: "h264_qsv",
    EncoderBackend.AMD_AMF: "h264_amf",
}


@dataclass(frozen=True, slots=True)
class CapabilityReport:
    ffmpeg_path: str
    ffmpeg_sha256: str
    ffmpeg_version: str
    platform: str
    available_backends: tuple[EncoderBackend, ...]
    hwaccels: tuple[str, ...]

    def __post_init__(self) -> None:
        if EncoderBackend.SOFTWARE not in self.available_backends:
            raise ValueError("software/libx264 capability is mandatory")
        if not re.fullmatch(r"[0-9a-f]{64}", self.ffmpeg_sha256):
            raise ValueError("ffmpeg_sha256 must be lowercase SHA-256")

    def to_json(self) -> str:
        payload = asdict(self)
        payload["available_backends"] = [value.value for value in self.available_backends]
        return json.dumps(payload, sort_keys=True, indent=2) + "\n"


@dataclass(frozen=True, slots=True)
class BackendChoice:
    requested: EncoderBackend
    selected: EncoderBackend
    codec: str
    fallback_used: bool
    reason: str


@dataclass(frozen=True, slots=True)
class BackendBenchmark:
    backend: EncoderBackend
    ffmpeg_sha256: str
    source_sha256: str
    wall_seconds: float
    media_seconds: float
    wall_media_ratio: float
    ssim: float
    output_bytes: int
    platform: str

    def __post_init__(self) -> None:
        for value in (self.wall_seconds, self.media_seconds, self.wall_media_ratio, self.ssim):
            if not math.isfinite(value) or value < 0:
                raise ValueError("benchmark metrics must be finite and non-negative")
        if self.media_seconds <= 0 or not 0 <= self.ssim <= 1:
            raise ValueError("benchmark duration/SSIM is invalid")

    def to_json(self) -> str:
        payload = asdict(self)
        payload["backend"] = self.backend.value
        return json.dumps(payload, sort_keys=True, indent=2) + "\n"


@dataclass(frozen=True, slots=True)
class PromotionDecision:
    promote: bool
    criteria: dict[str, bool]
    reason: str


def probe_ffmpeg(ffmpeg: str, runner: CommandRunner) -> CapabilityReport:
    executable = _resolve_executable(ffmpeg)
    before = _sha256(executable)
    version_result = runner(
        [str(executable), "-version"], "FFmpeg capability version probe failed",
        timeout=15, max_output_bytes=1024 * 1024,
    )
    lines = version_result.stdout.splitlines()
    if not lines or not lines[0].startswith("ffmpeg version "):
        raise HardwareProbeError("FFmpeg version output is malformed")
    encoder_result = runner(
        [str(executable), "-hide_banner", "-encoders"],
        "FFmpeg encoder capability probe failed", timeout=30,
        max_output_bytes=4 * 1024 * 1024,
    )
    hwaccel_result = runner(
        [str(executable), "-hide_banner", "-hwaccels"],
        "FFmpeg hardware acceleration probe failed", timeout=30,
        max_output_bytes=1024 * 1024,
    )
    available = tuple(
        backend
        for backend, codec in _CODECS.items()
        if re.search(rf"(?m)^\s*V\S*\s+{re.escape(codec)}(?:\s|$)", encoder_result.stdout)
    )
    if EncoderBackend.SOFTWARE not in available:
        raise HardwareProbeError("selected FFmpeg does not provide mandatory libx264")
    hwaccels = tuple(
        line.strip().lower()
        for line in hwaccel_result.stdout.splitlines()
        if line.strip() and not line.lower().startswith("hardware acceleration")
    )
    after = _sha256(executable)
    if before != after:
        raise HardwareProbeError("FFmpeg executable changed during capability probe")
    return CapabilityReport(
        str(executable), before, lines[0].strip(), platform.platform(), available, hwaccels
    )


def choose_backend(
    report: CapabilityReport, requested: EncoderBackend = EncoderBackend.SOFTWARE
) -> BackendChoice:
    if requested in report.available_backends:
        return BackendChoice(requested, requested, _CODECS[requested], False, "available")
    return BackendChoice(
        requested,
        EncoderBackend.SOFTWARE,
        _CODECS[EncoderBackend.SOFTWARE],
        True,
        f"{requested.value} unavailable; using software/libx264",
    )


def encoder_arguments(choice: BackendChoice, *, crf: int = 20, preset: str = "medium") -> list[str]:
    if not 0 <= crf <= 51:
        raise ValueError("crf must be between 0 and 51")
    if choice.selected is EncoderBackend.SOFTWARE:
        return ["-c:v", "libx264", "-preset", preset, "-crf", str(crf)]
    if choice.selected is EncoderBackend.NVIDIA:
        return ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", str(crf), "-b:v", "0"]
    if choice.selected is EncoderBackend.INTEL_QSV:
        return ["-c:v", "h264_qsv", "-preset", "medium", "-global_quality", str(crf)]
    return [
        "-c:v", "h264_amf", "-quality", "balanced", "-qp_i", str(crf), "-qp_p", str(crf)
    ]


def benchmark_backend(
    source: Path,
    output: Path,
    report: CapabilityReport,
    choice: BackendChoice,
    runner: CommandRunner,
    *,
    media_seconds: float,
) -> BackendBenchmark:
    if choice.selected not in report.available_backends:
        raise HardwareProbeError("selected backend was not proven by this capability report")
    if not source.is_file() or source.is_symlink():
        raise HardwareProbeError("benchmark source must be a local regular file")
    _require_safe_path(source, "benchmark source")
    output.parent.mkdir(parents=True, exist_ok=True)
    _require_safe_directory(output.parent, "benchmark output parent")
    if output.exists() or output.is_symlink():
        raise HardwareProbeError("benchmark output must not already exist")
    source_hash = _sha256(source)
    started = time.perf_counter()
    runner(
        [
            report.ffmpeg_path, "-hide_banner", "-loglevel", "error", "-n",
            "-i", str(source), "-map", "0:v:0", "-an",
            *encoder_arguments(choice), str(output),
        ],
        f"{choice.selected.value} benchmark encode failed", timeout=300,
        max_output_bytes=4 * 1024 * 1024,
    )
    wall = time.perf_counter() - started
    if not output.is_file() or output.stat().st_size == 0:
        raise HardwareProbeError("benchmark did not create an output")
    quality = runner(
        [
            report.ffmpeg_path, "-hide_banner", "-i", str(source), "-i", str(output),
            "-lavfi", "[0:v:0][1:v:0]ssim", "-f", "null", "-",
        ],
        "benchmark SSIM comparison failed", timeout=300,
        max_output_bytes=4 * 1024 * 1024,
    )
    match = re.search(r"All:([0-9]+(?:\.[0-9]+)?)", quality.stderr)
    if match is None:
        raise HardwareProbeError("FFmpeg SSIM output is malformed")
    ssim = float(match.group(1))
    if _sha256(source) != source_hash or _sha256(Path(report.ffmpeg_path)) != report.ffmpeg_sha256:
        raise HardwareProbeError("benchmark source/tool identity changed")
    return BackendBenchmark(
        choice.selected,
        report.ffmpeg_sha256,
        source_hash,
        wall,
        media_seconds,
        wall / media_seconds,
        ssim,
        output.stat().st_size,
        platform.platform(),
    )


def evaluate_promotion(
    software: BackendBenchmark, candidate: BackendBenchmark
) -> PromotionDecision:
    if software.backend is not EncoderBackend.SOFTWARE:
        raise ValueError("promotion reference must use software/libx264")
    if software.source_sha256 != candidate.source_sha256:
        raise ValueError("promotion benchmarks must use the same source")
    criteria = {
        "candidate_is_hardware": candidate.backend is not EncoderBackend.SOFTWARE,
        "ssim_floor": candidate.ssim >= 0.95,
        "ssim_parity": candidate.ssim >= software.ssim - 0.01,
        "runtime": candidate.wall_seconds <= software.wall_seconds * 1.10,
    }
    promote = all(criteria.values())
    return PromotionDecision(
        promote,
        criteria,
        "hardware backend meets promotion thresholds" if promote else "software fallback retained",
    )


def _resolve_executable(value: str) -> Path:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute() and candidate.parent == Path("."):
        found = shutil.which(value)
        if found is None:
            raise HardwareProbeError("selected FFmpeg executable is unavailable")
        candidate = Path(found)
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise HardwareProbeError("selected FFmpeg executable is unavailable") from exc
    _require_safe_path(candidate, "selected FFmpeg")
    _require_safe_path(resolved, "selected FFmpeg")
    return resolved


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_link_or_reparse(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return False
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def _require_safe_directory(path: Path, label: str) -> None:
    if not path.is_dir():
        raise HardwareProbeError(f"{label} must be an existing directory")
    candidate = path
    while True:
        if _is_link_or_reparse(candidate):
            raise HardwareProbeError(f"{label} traverses a symlink/reparse point")
        if candidate == candidate.parent:
            break
        candidate = candidate.parent
    if str(path.resolve(strict=True)).startswith(("\\\\", "//")):
        raise HardwareProbeError(f"{label} must be on a local filesystem")


def _require_safe_path(path: Path, label: str) -> None:
    _require_safe_directory(path.parent, f"{label} parent")
    if not path.is_file() or _is_link_or_reparse(path):
        raise HardwareProbeError(f"{label} must be a local regular file")
