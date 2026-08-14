"""Small, Qt-free domain models for one media export."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from .overlay import DEFAULT_OVERLAY_CONFIG, OverlayConfig


DateOrigin = Literal["metadata", "filename"]


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
class MediaItem:
    """An inspected source accepted by the current media pipeline."""

    path: Path
    taken_at: datetime
    is_photo: bool
    has_audio: bool
    date_source: str
    date_decision: DateDecision | None = None


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


@dataclass(frozen=True)
class ExportPlan:
    """Deterministic accepted timeline and inspection diagnostics."""

    request: ExportRequest
    items: tuple[MediaItem, ...]
    inspection_failures: tuple[tuple[Path, str], ...] = ()


class MediaError(RuntimeError):
    """An error tied to one input media file."""
