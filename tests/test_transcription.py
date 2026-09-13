from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from video_chronicle.transcription import (
    ModelManifest,
    TranscriptionError,
    TranscriptionRequest,
    WhisperCppAdapter,
    optional_transcription_adapter,
    write_transcript,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path: Path):
    source = (tmp_path / "видео sample.mp4").absolute()
    model = (tmp_path / "ggml-test.bin").absolute()
    whisper = (tmp_path / "whisper-cli.exe").absolute()
    ffmpeg = (tmp_path / "ffmpeg.exe").absolute()
    source.write_bytes(b"source-media")
    model.write_bytes(b"local-model")
    whisper.write_bytes(b"trusted-whisper")
    ffmpeg.write_bytes(b"trusted-ffmpeg")
    manifest = ModelManifest(
        model_id="ggml-test",
        version="1",
        sha256=_sha256(model),
        size_bytes=model.stat().st_size,
        license="MIT test fixture",
        source_url="https://example.invalid/ggml-test",
        languages=("auto", "en", "ru", "uk"),
    )
    return source, model, whisper, ffmpeg, manifest


def _runner_with_golden(calls: list[list[str]], temporary_paths: list[Path]):
    def runner(command, context, *, timeout=None, max_output_bytes=8 * 1024 * 1024):
        calls.append(command)
        if "-of" not in command:
            Path(command[-1]).write_bytes(b"RIFF-fixture")
        else:
            wav = Path(command[command.index("-f") + 1])
            prefix = Path(command[command.index("-of") + 1])
            temporary_paths.extend((wav, prefix.with_suffix(".json")))
            prefix.with_suffix(".json").write_text(
                json.dumps(
                    {
                        "result": {"language": "en"},
                        "transcription": [
                            {
                                "offsets": {"from": 0, "to": 750},
                                "text": " Hello world. ",
                            },
                            {
                                "offsets": {"from": 900, "to": 1500},
                                "text": "Second segment.",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
        return subprocess.CompletedProcess(command, 0, "", "")

    return runner


def test_disabled_transcription_has_no_commands_or_files(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    feature = optional_transcription_adapter({}, runner=lambda *args, **kwargs: calls.append(args[0]))
    assert feature.available is False
    assert "disabled" in feature.reason
    assert calls == []
    assert list(tmp_path.iterdir()) == []


def test_whisper_cpp_adapter_preserves_provenance_argv_and_cleans_temp(
    tmp_path: Path,
) -> None:
    source, model, whisper, ffmpeg, manifest = _fixture(tmp_path)
    calls: list[list[str]] = []
    temporary_paths: list[Path] = []
    adapter = WhisperCppAdapter(
        whisper,
        model,
        manifest,
        ffmpeg,
        runner=_runner_with_golden(calls, temporary_paths),
    )
    before = source.read_bytes()

    transcript = adapter.transcribe(
        TranscriptionRequest("item-test", source, 2_000_000, "auto")
    )

    assert transcript.language == "en"
    assert [(segment.start_us, segment.end_us, segment.text) for segment in transcript.segments] == [
        (0, 750_000, "Hello world."),
        (900_000, 1_500_000, "Second segment."),
    ]
    assert transcript.source_sha256 == hashlib.sha256(before).hexdigest()
    assert transcript.model_sha256 == manifest.sha256
    assert transcript.model_license == manifest.license
    assert calls[0][calls[0].index("-ar") + 1] == "16000"
    assert calls[0][calls[0].index("-ac") + 1] == "1"
    assert calls[1][calls[1].index("-l") + 1] == "auto"
    assert "-ojf" in calls[1]
    assert source.read_bytes() == before
    assert all(not path.exists() for path in temporary_paths)


def test_manifest_hash_mismatch_fails_before_any_command(tmp_path: Path) -> None:
    source, model, whisper, ffmpeg, manifest = _fixture(tmp_path)
    model.write_bytes(b"replaced-model")
    calls: list[list[str]] = []
    adapter = WhisperCppAdapter(
        whisper, model, manifest, ffmpeg, runner=lambda command, *a, **k: calls.append(command)
    )
    with pytest.raises(TranscriptionError, match="approved manifest"):
        adapter.transcribe(TranscriptionRequest("item-test", source, 1_000_000))
    assert calls == []


def test_overlapping_or_out_of_bounds_whisper_output_is_rejected(tmp_path: Path) -> None:
    source, model, whisper, ffmpeg, manifest = _fixture(tmp_path)

    def runner(command, context, **kwargs):
        if "-of" not in command:
            Path(command[-1]).write_bytes(b"RIFF")
        else:
            prefix = Path(command[command.index("-of") + 1])
            prefix.with_suffix(".json").write_text(
                json.dumps(
                    {
                        "result": {"language": "en"},
                        "transcription": [
                            {"offsets": {"from": 0, "to": 800}, "text": "one"},
                            {"offsets": {"from": 700, "to": 1200}, "text": "two"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
        return subprocess.CompletedProcess(command, 0, "", "")

    adapter = WhisperCppAdapter(whisper, model, manifest, ffmpeg, runner=runner)
    with pytest.raises(TranscriptionError, match="overlap"):
        adapter.transcribe(TranscriptionRequest("item-test", source, 2_000_000))


def test_transcript_sidecar_is_atomic_and_requires_overwrite(tmp_path: Path) -> None:
    source, model, whisper, ffmpeg, manifest = _fixture(tmp_path)
    adapter = WhisperCppAdapter(
        whisper, model, manifest, ffmpeg, runner=_runner_with_golden([], [])
    )
    transcript = adapter.transcribe(
        TranscriptionRequest("item-test", source, 2_000_000)
    )
    output = tmp_path / "transcript.json"
    write_transcript(output, transcript)
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema"] == "video-chronicle-transcript-v1"
    assert payload["segments"][0]["start_us"] == 0
    with pytest.raises(RuntimeError, match="output appeared"):
        write_transcript(output, transcript)
    write_transcript(output, transcript, overwrite=True)
