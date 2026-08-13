"""Small, Qt-free domain models for one media export."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class MediaItem:
    """An inspected source accepted by the current media pipeline."""

    path: Path
    taken_at: datetime
    is_photo: bool
    has_audio: bool
    date_source: str


@dataclass(frozen=True)
class ExportRequest:
    """Validated inputs needed to plan and execute one legacy-compatible export."""

    input_dir: Path
    output: Path
    error_log: Path
    ffmpeg: str
    ffprobe: str
    font_file: Path | None
    crf: int
    preset: str
    overwrite: bool
    keep_work: bool


@dataclass(frozen=True)
class ExportPlan:
    """Deterministic source snapshot accepted for one export execution."""

    request: ExportRequest
    source_paths: tuple[Path, ...]


class MediaError(RuntimeError):
    """An error tied to one input media file."""
