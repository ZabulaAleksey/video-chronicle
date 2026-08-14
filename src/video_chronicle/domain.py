"""Small, Qt-free domain models for one media export."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Literal

from .overlay import DEFAULT_OVERLAY_CONFIG, OverlayConfig


DateOrigin = Literal["metadata", "filename"]


class ExportMode(str, Enum):
    """User-visible policy applied at the request/overlay boundary."""

    JOIN = "join"
    CHRONICLE = "chronicle"


@dataclass(frozen=True)
class DateCandidate:
    """One valid recorded wall-clock value and its unmodified provenance."""

    wall_time: datetime
    raw_value: str
    origin: DateOrigin
    key: str | None
    raw_key: str | None
    location: str
    timezone: str | None
    priority: int

    def __post_init__(self) -> None:
        if self.wall_time.tzinfo is not None:
            raise ValueError("DateCandidate.wall_time must not carry tzinfo")
        if not self.raw_value:
            raise ValueError("DateCandidate.raw_value must not be empty")
        if self.origin == "metadata" and not self.key:
            raise ValueError("metadata DateCandidate requires a key")
        if self.origin == "metadata" and not self.raw_key:
            raise ValueError("metadata DateCandidate requires its raw key")
        if self.origin == "filename" and (
            self.key is not None or self.raw_key is not None
        ):
            raise ValueError("filename DateCandidate must not carry a metadata key")
        if self.priority < 0:
            raise ValueError("DateCandidate.priority must be non-negative")

    @property
    def source(self) -> str:
        """Return the stable source label used by the legacy CLI."""

        return f"metadata:{self.key}" if self.origin == "metadata" else "filename"


@dataclass(frozen=True)
class DateDecision:
    """Deterministic result of the approved DATE-001 selection policy."""

    selected: DateCandidate
    all_valid: tuple[DateCandidate, ...]
    conflicts: tuple[DateCandidate, ...]
    policy_version: str

    def __post_init__(self) -> None:
        if not self.policy_version:
            raise ValueError("DateDecision.policy_version must not be empty")
        if self.selected not in self.all_valid:
            raise ValueError("selected date must be present in all_valid")
        if any(candidate not in self.all_valid for candidate in self.conflicts):
            raise ValueError("date conflicts must be present in all_valid")
        if any(
            (candidate.wall_time, candidate.timezone)
            == (self.selected.wall_time, self.selected.timezone)
            for candidate in self.conflicts
        ):
            raise ValueError("equal recorded date values are not conflicts")


@dataclass(frozen=True)
class SourceFingerprint:
    """Immutable local file identity captured after successful inspection."""

    device: int
    inode: int
    size: int
    mtime_ns: int
    ctime_ns: int
    sha256: str | None = None

    @classmethod
    def capture(cls, path: Path) -> "SourceFingerprint":
        before = path.stat()
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        stat_result = path.stat()
        fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if any(getattr(before, field) != getattr(stat_result, field) for field in fields):
            raise OSError(f"source changed while fingerprinting: {path}")
        return cls(
            device=stat_result.st_dev,
            inode=stat_result.st_ino,
            size=stat_result.st_size,
            mtime_ns=stat_result.st_mtime_ns,
            ctime_ns=stat_result.st_ctime_ns,
            sha256=digest.hexdigest(),
        )


@dataclass(frozen=True)
class MediaItem:
    """An inspected source accepted by the current media pipeline."""

    path: Path
    taken_at: datetime
    is_photo: bool
    has_audio: bool
    date_source: str
    date_decision: DateDecision | None = None
    source_fingerprint: SourceFingerprint | None = None
    source_duration_us: int | None = None
    trim_in_us: int = 0
    trim_out_us: int | None = None
    trim_applied: bool = False

    def __post_init__(self) -> None:
        if self.source_duration_us is not None and (
            isinstance(self.source_duration_us, bool)
            or not isinstance(self.source_duration_us, int)
            or self.source_duration_us <= 0
        ):
            raise ValueError("source_duration_us must be a positive integer or null")
        if isinstance(self.trim_in_us, bool) or not isinstance(self.trim_in_us, int) or self.trim_in_us < 0:
            raise ValueError("trim_in_us must be a non-negative integer")
        if self.trim_out_us is not None and (
            isinstance(self.trim_out_us, bool)
            or not isinstance(self.trim_out_us, int)
            or self.trim_out_us <= self.trim_in_us
        ):
            raise ValueError("trim_out_us must be greater than trim_in_us")


@dataclass(frozen=True)
class ExportRequest:
    """Validated inputs needed to plan and execute one legacy-compatible export."""

    input_dir: Path
    output: Path
    error_log: Path
    ffmpeg: str
    ffprobe: str
    crf: int
    preset: str
    overwrite: bool
    keep_work: bool
    overlay: OverlayConfig = DEFAULT_OVERLAY_CONFIG
    mode: ExportMode = ExportMode.CHRONICLE

    def __post_init__(self) -> None:
        if not isinstance(self.mode, ExportMode):
            raise TypeError("mode must be ExportMode")
        if self.mode is ExportMode.JOIN and self.overlay.enabled:
            raise ValueError("Join mode requires a disabled overlay")


@dataclass(frozen=True)
class ExportPlan:
    """Deterministic accepted timeline and inspection diagnostics."""

    request: ExportRequest
    items: tuple[MediaItem, ...]
    inspection_failures: tuple[tuple[Path, str], ...] = ()
    project_snapshot: object | None = None

    @property
    def plan_id(self) -> str | None:
        return getattr(self.project_snapshot, "plan_id", None)


class MediaError(RuntimeError):
    """An error tied to one input media file."""
