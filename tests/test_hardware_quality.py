from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess

import pytest

from video_chronicle.hardware import (
    BackendBenchmark,
    EncoderBackend,
    HardwareProbeError,
    benchmark_backend,
    choose_backend,
    encoder_arguments,
    evaluate_promotion,
    probe_ffmpeg,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _completed(command: list[str], *, stdout: str = "", stderr: str = ""):
    return subprocess.CompletedProcess(command, 0, stdout, stderr)


def test_probe_reports_only_approved_backends(tmp_path: Path) -> None:
    ffmpeg = tmp_path / "ffmpeg.exe"
    ffmpeg.write_bytes(b"tool")
    commands: list[list[str]] = []

    def runner(command, context, **kwargs):
        commands.append(command)
        if command[-1] == "-version":
            return _completed(command, stdout="ffmpeg version 9.0.1 test\n")
        if command[-1] == "-encoders":
            return _completed(
                command,
                stdout=" V..... libx264 H.264\n V..... h264_nvenc NVIDIA\n V..... evil_h264 nope\n",
            )
        return _completed(command, stdout="Hardware acceleration methods:\ncuda\nd3d11va\n")

    report = probe_ffmpeg(str(ffmpeg), runner)

    assert report.ffmpeg_sha256 == _sha(ffmpeg)
    assert report.available_backends == (
        EncoderBackend.SOFTWARE,
        EncoderBackend.NVIDIA,
    )
    assert report.hwaccels == ("cuda", "d3d11va")
    assert commands == [
        [str(ffmpeg), "-version"],
        [str(ffmpeg), "-hide_banner", "-encoders"],
        [str(ffmpeg), "-hide_banner", "-hwaccels"],
    ]


def test_probe_rejects_malformed_or_missing_software_encoder(tmp_path: Path) -> None:
    ffmpeg = tmp_path / "ffmpeg.exe"
    ffmpeg.write_bytes(b"tool")

    def runner(command, context, **kwargs):
        if command[-1] == "-version":
            return _completed(command, stdout="ffmpeg version 9\n")
        return _completed(command, stdout=" V..... h264_nvenc NVIDIA\n")

    with pytest.raises(HardwareProbeError, match="libx264"):
        probe_ffmpeg(str(ffmpeg), runner)


def test_selection_and_fixed_arguments(tmp_path: Path) -> None:
    from video_chronicle.hardware import CapabilityReport

    report = CapabilityReport(
        str(tmp_path / "ffmpeg"), "0" * 64, "ffmpeg version test", "test",
        (EncoderBackend.SOFTWARE, EncoderBackend.INTEL_QSV), ("qsv",),
    )
    default = choose_backend(report)
    explicit = choose_backend(report, EncoderBackend.INTEL_QSV)
    fallback = choose_backend(report, EncoderBackend.NVIDIA)

    assert default.selected is EncoderBackend.SOFTWARE
    assert explicit.selected is EncoderBackend.INTEL_QSV
    assert fallback.selected is EncoderBackend.SOFTWARE and fallback.fallback_used
    assert encoder_arguments(default) == [
        "-c:v", "libx264", "-preset", "medium", "-crf", "20"
    ]
    assert encoder_arguments(explicit) == [
        "-c:v", "h264_qsv", "-preset", "medium", "-global_quality", "20"
    ]


def _benchmark(backend: EncoderBackend, source_hash: str, wall: float, ssim: float):
    return BackendBenchmark(
        backend, "1" * 64, source_hash, wall, 10.0, wall / 10.0, ssim, 100, "test"
    )


def test_promotion_thresholds_and_source_identity() -> None:
    software = _benchmark(EncoderBackend.SOFTWARE, "a" * 64, 10.0, 0.98)
    assert evaluate_promotion(
        software, _benchmark(EncoderBackend.NVIDIA, "a" * 64, 10.5, 0.975)
    ).promote
    assert not evaluate_promotion(
        software, _benchmark(EncoderBackend.NVIDIA, "a" * 64, 11.2, 0.975)
    ).promote
    assert not evaluate_promotion(
        software, _benchmark(EncoderBackend.NVIDIA, "a" * 64, 9.0, 0.94)
    ).promote
    with pytest.raises(ValueError, match="same source"):
        evaluate_promotion(
            software, _benchmark(EncoderBackend.NVIDIA, "b" * 64, 9.0, 0.98)
        )


def test_benchmark_uses_managed_argv_and_parses_ssim(tmp_path: Path) -> None:
    from video_chronicle.hardware import CapabilityReport

    ffmpeg = tmp_path / "ffmpeg.exe"
    source = tmp_path / "source.mp4"
    output = tmp_path / "encoded.mp4"
    ffmpeg.write_bytes(b"tool")
    source.write_bytes(b"source")
    report = CapabilityReport(
        str(ffmpeg), _sha(ffmpeg), "ffmpeg version test", "test",
        (EncoderBackend.SOFTWARE, EncoderBackend.NVIDIA), ("cuda",),
    )
    choice = choose_backend(report, EncoderBackend.NVIDIA)
    commands: list[list[str]] = []

    def runner(command, context, **kwargs):
        commands.append(command)
        if any("ssim" in argument for argument in command):
            return _completed(command, stderr="SSIM Y:0.98 All:0.979 (17.0)")
        output.write_bytes(b"encoded")
        return _completed(command)

    result = benchmark_backend(
        source, output, report, choice, runner, media_seconds=2.0
    )

    assert result.ssim == pytest.approx(0.979)
    assert result.source_sha256 == _sha(source)
    assert commands[0][0] == str(ffmpeg)
    assert "h264_nvenc" in commands[0]
    assert "-n" in commands[0] and "-y" not in commands[0]
    assert commands[1][-3:] == ["-f", "null", "-"]


def test_benchmark_refuses_existing_output(tmp_path: Path) -> None:
    from video_chronicle.hardware import CapabilityReport

    ffmpeg = tmp_path / "ffmpeg.exe"
    source = tmp_path / "source.mp4"
    output = tmp_path / "existing.mp4"
    ffmpeg.write_bytes(b"tool")
    source.write_bytes(b"source")
    output.write_bytes(b"keep")
    report = CapabilityReport(
        str(ffmpeg), _sha(ffmpeg), "ffmpeg version test", "test",
        (EncoderBackend.SOFTWARE,), (),
    )

    with pytest.raises(HardwareProbeError, match="must not already exist"):
        benchmark_backend(
            source, output, report, choose_backend(report), lambda *_a, **_k: None,
            media_seconds=1.0,
        )
    assert output.read_bytes() == b"keep"
