"""Typed process/filesystem boundaries used by the application service."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Any, Protocol

from .domain import MediaItem
from .overlay import OverlayConfig


class CommandRunner(Protocol):
    def __call__(
        self,
        command: list[str],
        context: str,
        *,
        timeout: float | None = None,
        max_output_bytes: int = 8 * 1024 * 1024,
    ) -> subprocess.CompletedProcess[str]: ...


class ProbeMedia(Protocol):
    def __call__(
        self, path: Path, ffprobe: str, runner: CommandRunner
    ) -> dict[str, Any]: ...


class InspectMedia(Protocol):
    def __call__(
        self,
        path: Path,
        ffprobe: str,
        probe: ProbeMedia,
        runner: CommandRunner,
    ) -> MediaItem: ...


class NormalizeMedia(Protocol):
    def __call__(
        self,
        item: MediaItem,
        destination: Path,
        ffmpeg: str,
        overlay: OverlayConfig,
        crf: int,
        preset: str,
        runner: CommandRunner,
    ) -> None: ...


class ConcatenateMedia(Protocol):
    def __call__(
        self,
        clips: list[Path],
        concat_file: Path,
        temporary_output: Path,
        ffmpeg: str,
        runner: CommandRunner,
    ) -> None: ...


class PublishOutput(Protocol):
    def __call__(
        self, temporary_output: Path, output: Path, overwrite: bool
    ) -> None: ...


class CollectSources(Protocol):
    def __call__(
        self, input_dir: Path, output: Path, error_log: Path
    ) -> list[Path]: ...


class CreateWorkspace(Protocol):
    def __call__(self, output_parent: Path) -> Path: ...


class CleanupWorkspace(Protocol):
    def __call__(self, workspace: Path) -> None: ...


class ValidateSource(Protocol):
    def __call__(self, input_dir: Path, source: Path) -> None: ...


@dataclass(frozen=True)
class PipelinePorts:
    """Explicit adapters at the application boundary."""

    command_runner: CommandRunner
    probe_media: ProbeMedia
    inspect_item: InspectMedia
    normalize_item: NormalizeMedia
    concatenate: ConcatenateMedia
    publish_output: PublishOutput
    collect_source_paths: CollectSources
    create_workspace: CreateWorkspace
    cleanup_workspace: CleanupWorkspace
    validate_source: ValidateSource
