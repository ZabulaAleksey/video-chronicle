"""Local-only whisper.cpp transcription boundary with explicit provenance."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
import time
from typing import Any

from .domain import SourceFingerprint
from .execution import current_execution_context
from .ports import CommandRunner


TRANSCRIPT_SCHEMA = "video-chronicle-transcript-v1"
MAX_MODEL_BYTES = 4 * 1024 * 1024 * 1024
MAX_TRANSCRIPT_BYTES = 8 * 1024 * 1024
MAX_SEGMENTS = 20_000
MAX_SEGMENT_TEXT = 4096
MAX_DURATION_US = 12 * 60 * 60 * 1_000_000
DEFAULT_TIMEOUT_SECONDS = 30 * 60.0


class TranscriptionError(RuntimeError):
    """A local transcription boundary rejected input, output, or runtime state."""


@dataclass(frozen=True, slots=True)
class ModelManifest:
    model_id: str
    version: str
    sha256: str
    size_bytes: int
    license: str
    source_url: str
    languages: tuple[str, ...]
    engine: str = "whisper.cpp"

    def __post_init__(self) -> None:
        for value, label in (
            (self.model_id, "model_id"),
            (self.version, "version"),
            (self.license, "license"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{label} must be non-empty")
        if self.engine != "whisper.cpp":
            raise ValueError("only whisper.cpp model manifests are supported")
        if not re.fullmatch(r"[0-9a-f]{64}", self.sha256):
            raise ValueError("sha256 must be lowercase SHA-256")
        if not isinstance(self.size_bytes, int) or not 0 < self.size_bytes <= MAX_MODEL_BYTES:
            raise ValueError("model size is outside the 4 GiB limit")
        if not self.source_url.startswith("https://"):
            raise ValueError("model source_url must use https")
        if not self.languages or any(not _valid_language(value) for value in self.languages):
            raise ValueError("languages must contain normalized language tags")

    @classmethod
    def from_json_file(cls, path: Path) -> "ModelManifest":
        _require_safe_regular_file(path, "model manifest")
        if path.stat().st_size > 64 * 1024:
            raise TranscriptionError("model manifest exceeds 64 KiB")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise TranscriptionError("model manifest is not valid UTF-8 JSON") from exc
        required = {
            "model_id", "version", "sha256", "size_bytes", "license",
            "source_url", "languages", "engine",
        }
        if not isinstance(payload, dict) or set(payload) != required:
            raise TranscriptionError("model manifest fields do not match schema v1")
        languages = payload["languages"]
        if not isinstance(languages, list) or any(not isinstance(value, str) for value in languages):
            raise TranscriptionError("model manifest languages must be a string list")
        try:
            return cls(
                model_id=payload["model_id"],
                version=payload["version"],
                sha256=payload["sha256"],
                size_bytes=payload["size_bytes"],
                license=payload["license"],
                source_url=payload["source_url"],
                languages=tuple(languages),
                engine=payload["engine"],
            )
        except (TypeError, ValueError) as exc:
            raise TranscriptionError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class TranscriptSegment:
    start_us: int
    end_us: int
    text: str
    confidence: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.start_us, int) or not isinstance(self.end_us, int):
            raise TypeError("segment timestamps must be integer microseconds")
        if self.start_us < 0 or self.end_us <= self.start_us:
            raise ValueError("segment timestamps must satisfy 0 <= start < end")
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("segment text must not be empty")
        if len(self.text) > MAX_SEGMENT_TEXT:
            raise ValueError("segment text exceeds 4096 code points")
        if self.confidence is not None and (
            not isinstance(self.confidence, (int, float))
            or not math.isfinite(float(self.confidence))
            or not 0.0 <= float(self.confidence) <= 1.0
        ):
            raise ValueError("segment confidence must be finite in [0, 1]")


@dataclass(frozen=True, slots=True)
class Transcript:
    item_id: str
    language: str
    segments: tuple[TranscriptSegment, ...]
    source_sha256: str
    model_id: str
    model_version: str
    model_sha256: str
    model_license: str
    engine: str
    engine_sha256: str
    limitations: str
    schema: str = TRANSCRIPT_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != TRANSCRIPT_SCHEMA:
            raise ValueError("unsupported transcript schema")
        if not isinstance(self.item_id, str) or not self.item_id.strip():
            raise ValueError("item_id must not be empty")
        if not _valid_language(self.language):
            raise ValueError("language must be auto or a normalized language tag")
        if len(self.segments) > MAX_SEGMENTS:
            raise ValueError("transcript exceeds segment limit")
        previous_end = 0
        for segment in self.segments:
            if segment.start_us < previous_end:
                raise ValueError("transcript segments overlap or are unordered")
            previous_end = segment.end_us
        for digest in (self.source_sha256, self.model_sha256, self.engine_sha256):
            if not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ValueError("transcript provenance requires SHA-256 identities")
        if not self.limitations.strip():
            raise ValueError("transcript limitations must be visible")

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True, indent=2) + "\n"


@dataclass(frozen=True, slots=True)
class TranscriptionRequest:
    item_id: str
    source_path: Path
    source_duration_us: int
    language: str = "auto"

    def __post_init__(self) -> None:
        if not isinstance(self.item_id, str) or not self.item_id.strip():
            raise ValueError("item_id must not be empty")
        if not self.source_path.is_absolute():
            raise ValueError("source_path must be absolute")
        if not isinstance(self.source_duration_us, int) or not 0 < self.source_duration_us <= MAX_DURATION_US:
            raise ValueError("source duration is outside the 12 hour limit")
        if not _valid_language(self.language):
            raise ValueError("language must be auto or a normalized language tag")


class WhisperCppAdapter:
    """Run an explicitly supplied local whisper.cpp CLI and model."""

    def __init__(
        self,
        whisper_cli: Path,
        model_path: Path,
        manifest: ModelManifest,
        ffmpeg: Path,
        *,
        runner: CommandRunner,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        if not math.isfinite(timeout) or timeout <= 0 or timeout > DEFAULT_TIMEOUT_SECONDS:
            raise ValueError("timeout must be positive and no more than 30 minutes")
        self.whisper_cli = _resolved_safe_file(whisper_cli, "whisper-cli")
        self.model_path = _resolved_safe_file(model_path, "model")
        self.ffmpeg = _resolved_safe_file(ffmpeg, "FFmpeg")
        self.manifest = manifest
        self.runner = runner
        self.timeout = timeout

    def transcribe(self, request: TranscriptionRequest) -> Transcript:
        deadline = time.monotonic() + self.timeout
        source = _resolved_safe_file(request.source_path, "source media")
        if source.stat().st_size == 0:
            raise TranscriptionError("source media is empty")
        source_before = _fingerprint(source, deadline)
        model_before = _fingerprint(self.model_path, deadline)
        engine_before = _fingerprint(self.whisper_cli, deadline)
        if model_before.size != self.manifest.size_bytes or model_before.sha256 != self.manifest.sha256:
            raise TranscriptionError("model bytes do not match the approved manifest")
        if request.language != "auto" and "auto" not in self.manifest.languages and request.language not in self.manifest.languages:
            raise TranscriptionError("requested language is not declared by the model manifest")

        with tempfile.TemporaryDirectory(prefix="video_chronicle_transcribe_") as raw_root:
            root = Path(raw_root)
            wav = root / "audio.wav"
            prefix = root / "transcript"
            self.runner(
                [
                    str(self.ffmpeg), "-hide_banner", "-loglevel", "error", "-y",
                    "-i", str(source), "-vn", "-ac", "1", "-ar", "16000",
                    "-c:a", "pcm_s16le", str(wav),
                ],
                "FFmpeg audio extraction failed",
                timeout=_remaining(deadline),
            )
            _checkpoint(deadline)
            self.runner(
                [
                    str(self.whisper_cli), "-m", str(self.model_path), "-f", str(wav),
                    "-l", request.language, "-ojf", "-of", str(prefix), "-np",
                ],
                "whisper.cpp transcription failed",
                timeout=_remaining(deadline),
                max_output_bytes=MAX_TRANSCRIPT_BYTES,
            )
            json_path = prefix.with_suffix(".json")
            payload = _read_whisper_json(json_path)

        if _fingerprint(source, deadline) != source_before:
            raise TranscriptionError("source identity changed during transcription")
        if _fingerprint(self.model_path, deadline) != model_before:
            raise TranscriptionError("model identity changed during transcription")
        if _fingerprint(self.whisper_cli, deadline) != engine_before:
            raise TranscriptionError("whisper-cli identity changed during transcription")
        language, segments = _parse_whisper_payload(payload, request.source_duration_us)
        return Transcript(
            item_id=request.item_id,
            language=language,
            segments=segments,
            source_sha256=source_before.sha256 or "",
            model_id=self.manifest.model_id,
            model_version=self.manifest.version,
            model_sha256=self.manifest.sha256,
            model_license=self.manifest.license,
            engine=self.manifest.engine,
            engine_sha256=engine_before.sha256 or "",
            limitations=(
                "Automatic speech recognition may contain omissions, substitutions, "
                "and imprecise timestamps; verify before relying on the text."
            ),
        )


@dataclass(frozen=True, slots=True)
class OptionalTranscriptionFeature:
    available: bool
    reason: str
    adapter: WhisperCppAdapter | None = None


def optional_transcription_adapter(
    environ: dict[str, str] | None = None,
    *,
    runner: CommandRunner | None = None,
) -> OptionalTranscriptionFeature:
    values = os.environ if environ is None else environ
    if values.get("VIDEO_CHRONICLE_TRANSCRIPTION", "off") != "whisper-cpp":
        return OptionalTranscriptionFeature(False, "local transcription is disabled")
    required = {
        "VIDEO_CHRONICLE_WHISPER_CLI": "whisper-cli",
        "VIDEO_CHRONICLE_WHISPER_MODEL": "model",
        "VIDEO_CHRONICLE_WHISPER_MANIFEST": "manifest",
        "VIDEO_CHRONICLE_FFMPEG": "FFmpeg",
    }
    if any(not values.get(key) for key in required):
        return OptionalTranscriptionFeature(False, "local transcription paths are incomplete")
    if runner is None:
        from .pipeline import run_command

        runner = run_command
    try:
        manifest = ModelManifest.from_json_file(Path(values["VIDEO_CHRONICLE_WHISPER_MANIFEST"]))
        adapter = WhisperCppAdapter(
            Path(values["VIDEO_CHRONICLE_WHISPER_CLI"]),
            Path(values["VIDEO_CHRONICLE_WHISPER_MODEL"]),
            manifest,
            Path(values["VIDEO_CHRONICLE_FFMPEG"]),
            runner=runner,
        )
    except (OSError, ValueError, TranscriptionError) as exc:
        return OptionalTranscriptionFeature(False, str(exc))
    return OptionalTranscriptionFeature(True, "available", adapter)


def write_transcript(path: Path, transcript: Transcript, *, overwrite: bool = False) -> None:
    """Atomically publish one JSON sidecar with explicit overwrite policy."""

    destination = path.expanduser().absolute()
    if destination.suffix.casefold() != ".json":
        raise TranscriptionError("transcript output must have a .json extension")
    destination.parent.mkdir(parents=True, exist_ok=True)
    _require_safe_output_parent(destination.parent)
    descriptor, raw_temp = tempfile.mkstemp(
        prefix=".video_chronicle_transcript_", suffix=".tmp", dir=destination.parent
    )
    temp = Path(raw_temp)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(transcript.to_json())
            stream.flush()
            os.fsync(stream.fileno())
        from .pipeline import publish_output

        publish_output(temp, destination, overwrite)
    except Exception:
        temp.unlink(missing_ok=True)
        raise


def _read_whisper_json(path: Path) -> Any:
    if not path.is_file():
        raise TranscriptionError("whisper.cpp did not create JSON output")
    if path.stat().st_size > MAX_TRANSCRIPT_BYTES:
        raise TranscriptionError("whisper.cpp JSON exceeds 8 MiB")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise TranscriptionError("whisper.cpp output is not valid UTF-8 JSON") from exc


def _parse_whisper_payload(payload: Any, duration_us: int) -> tuple[str, tuple[TranscriptSegment, ...]]:
    if not isinstance(payload, dict):
        raise TranscriptionError("whisper.cpp JSON root must be an object")
    result = payload.get("result")
    raw_segments = payload.get("transcription")
    if not isinstance(result, dict) or not isinstance(result.get("language"), str):
        raise TranscriptionError("whisper.cpp JSON has no detected language")
    language = result["language"].strip().lower()
    if not _valid_language(language) or language == "auto":
        raise TranscriptionError("whisper.cpp returned an invalid detected language")
    if not isinstance(raw_segments, list) or len(raw_segments) > MAX_SEGMENTS:
        raise TranscriptionError("whisper.cpp transcription has invalid segment count")
    segments: list[TranscriptSegment] = []
    for raw in raw_segments:
        if not isinstance(raw, dict) or not isinstance(raw.get("offsets"), dict):
            raise TranscriptionError("whisper.cpp segment has no offsets")
        offsets = raw["offsets"]
        start_ms, end_ms, text = offsets.get("from"), offsets.get("to"), raw.get("text")
        if (
            not isinstance(start_ms, int)
            or not isinstance(end_ms, int)
            or not isinstance(text, str)
        ):
            raise TranscriptionError("whisper.cpp segment fields have invalid types")
        try:
            segment = TranscriptSegment(start_ms * 1000, end_ms * 1000, text.strip())
        except (TypeError, ValueError) as exc:
            raise TranscriptionError(str(exc)) from exc
        if segment.end_us > duration_us:
            raise TranscriptionError("whisper.cpp segment exceeds source duration")
        segments.append(segment)
    try:
        transcript_probe = Transcript(
            "probe", language, tuple(segments), "0" * 64, "probe", "probe",
            "0" * 64, "probe", "whisper.cpp", "0" * 64, "limitations",
        )
    except (TypeError, ValueError) as exc:
        raise TranscriptionError(str(exc)) from exc
    return transcript_probe.language, transcript_probe.segments


def _valid_language(value: object) -> bool:
    return isinstance(value, str) and bool(
        value == "auto" or re.fullmatch(r"[a-z]{2,3}(?:-[A-Z]{2})?", value)
    )


def _checkpoint(deadline: float) -> None:
    context = current_execution_context()
    if context is not None:
        context.checkpoint()
    if time.monotonic() >= deadline:
        raise TranscriptionError("local transcription deadline exceeded")


def _remaining(deadline: float) -> float:
    _checkpoint(deadline)
    return max(0.001, deadline - time.monotonic())


def _fingerprint(path: Path, deadline: float) -> SourceFingerprint:
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
        raise TranscriptionError(f"file identity changed while fingerprinting: {path}")
    return SourceFingerprint(
        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns,
        after.st_ctime_ns, digest.hexdigest(),
    )


def _is_link_or_reparse(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return False
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def _require_safe_regular_file(path: Path, label: str) -> None:
    candidate = path
    while candidate != candidate.parent:
        if candidate.exists() and _is_link_or_reparse(candidate):
            raise TranscriptionError(f"{label} traverses a symlink/reparse point")
        candidate = candidate.parent
    if not path.is_file() or _is_link_or_reparse(path):
        raise TranscriptionError(f"{label} is not a safe regular file")
    if str(path).startswith(("\\\\", "//")):
        raise TranscriptionError(f"{label} must be on a local filesystem")


def _resolved_safe_file(path: Path, label: str) -> Path:
    _require_safe_regular_file(path, label)
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise TranscriptionError(f"{label} is unavailable") from exc
    _require_safe_regular_file(resolved, label)
    return resolved


def _require_safe_output_parent(path: Path) -> None:
    resolved = path.resolve(strict=True)
    candidate = path
    while True:
        if _is_link_or_reparse(candidate):
            raise TranscriptionError("transcript output traverses a symlink/reparse point")
        if candidate == candidate.parent:
            break
        candidate = candidate.parent
    if str(resolved).startswith(("\\\\", "//")):
        raise TranscriptionError("transcript output must be on a local filesystem")
