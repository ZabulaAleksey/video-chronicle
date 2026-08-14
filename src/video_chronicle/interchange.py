"""Qt-free, adapter-neutral timeline interchange contracts.

Interchange data is deliberately transient.  It is not part of the durable
project schema and importing it can only create a proposal.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol

from .project import (
    ProjectState,
    ResolvedTrim,
    TimelineGroup,
    TimelineLayout,
    TimelineLayoutEntry,
    TrimRange,
)


def _identifier(value: str, label: str) -> None:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ValueError(f"{label} must be a non-empty trimmed string")
    if any(character.isspace() for character in value):
        raise ValueError(f"{label} must not contain whitespace")


@dataclass(frozen=True, slots=True)
class InterchangeClip:
    item_id: str
    source_path: Path
    in_us: int
    out_us: int
    group_id: str | None = None

    def __post_init__(self) -> None:
        _identifier(self.item_id, "item_id")
        if not isinstance(self.source_path, Path) or not self.source_path.is_absolute():
            raise ValueError("source_path must be an absolute pathlib.Path")
        ResolvedTrim(self.in_us, self.out_us)
        if self.group_id is not None:
            _identifier(self.group_id, "group_id")


@dataclass(frozen=True, slots=True)
class InterchangeTimeline:
    project_id: str
    project_revision: int
    clips: tuple[InterchangeClip, ...]
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _identifier(self.project_id, "project_id")
        if (
            isinstance(self.project_revision, bool)
            or not isinstance(self.project_revision, int)
            or self.project_revision < 0
        ):
            raise ValueError("project_revision must be a non-negative integer")
        if not isinstance(self.clips, tuple) or not isinstance(self.warnings, tuple):
            raise TypeError("clips and warnings must be tuples")
        ids = tuple(clip.item_id for clip in self.clips)
        if len(ids) != len(set(ids)):
            raise ValueError("interchange clip item IDs must be unique")
        if any(not isinstance(warning, str) or not warning for warning in self.warnings):
            raise ValueError("warnings must be non-empty strings")

    @classmethod
    def from_project(cls, project: ProjectState) -> "InterchangeTimeline":
        if not isinstance(project, ProjectState):
            raise TypeError("project must be ProjectState")
        assert project.layout is not None
        items = {item.stable_id: item for item in project.timeline.items}
        clips = tuple(
            InterchangeClip(
                entry.item_id,
                items[entry.item_id].source_path,
                entry.trim.resolve(items[entry.item_id]).in_us,
                entry.trim.resolve(items[entry.item_id]).out_us,
                entry.group_id,
            )
            for entry in project.layout.entries
        )
        return cls(project.project_id, project.revision, clips)


@dataclass(frozen=True, slots=True)
class ProposedClip:
    source_path: Path
    in_us: int
    out_us: int
    item_id: str | None = None
    group_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.source_path, Path) or not self.source_path.is_absolute():
            raise ValueError("source_path must be an absolute pathlib.Path")
        ResolvedTrim(self.in_us, self.out_us)
        if self.item_id is not None:
            _identifier(self.item_id, "item_id")
        if self.group_id is not None:
            _identifier(self.group_id, "group_id")


@dataclass(frozen=True, slots=True)
class ImportResult:
    project_id: str
    project_revision: int
    clips: tuple[ProposedClip, ...]
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _identifier(self.project_id, "project_id")
        if self.project_revision < 0:
            raise ValueError("project_revision must be non-negative")
        if not isinstance(self.clips, tuple) or not isinstance(self.warnings, tuple):
            raise TypeError("clips and warnings must be tuples")

    @property
    def is_fully_mapped(self) -> bool:
        return all(clip.item_id is not None for clip in self.clips)


class TimelineInterchangePort(Protocol):
    def export_timeline(self, timeline: InterchangeTimeline) -> bytes: ...

    def import_timeline(
        self, payload: bytes, known_project: InterchangeTimeline
    ) -> ImportResult: ...


def apply_import_proposal(project: ProjectState, proposal: ImportResult) -> ProjectState:
    """Explicitly apply a complete proposal as one EDIT-001 revision.

    Refusal, cancellation, stale proposals and partial identity resolution leave
    the caller's immutable ``ProjectState`` byte-for-byte untouched.
    """

    if proposal.project_id != project.project_id:
        raise ValueError("proposal project ID does not match the current project")
    if proposal.project_revision != project.revision:
        raise ValueError("proposal is stale for the current project revision")
    if not proposal.is_fully_mapped:
        raise ValueError("proposal contains unmapped clips")
    item_ids = tuple(clip.item_id for clip in proposal.clips)
    assert all(item_id is not None for item_id in item_ids)
    if len(item_ids) != len(set(item_ids)) or set(item_ids) != set(project.timeline.item_ids):
        raise ValueError("proposal must be an exact permutation of project items")

    old_groups = {
        group.group_id: group for group in (project.layout.groups if project.layout else ())
    }
    used_group_ids: list[str] = []
    entries: list[TimelineLayoutEntry] = []
    for clip in proposal.clips:
        if clip.group_id is not None and clip.group_id not in used_group_ids:
            used_group_ids.append(clip.group_id)
        entries.append(
            TimelineLayoutEntry(
                item_id=clip.item_id or "",
                trim=TrimRange(clip.in_us, clip.out_us),
                group_id=clip.group_id,
            )
        )
    groups = tuple(
        old_groups.get(group_id, TimelineGroup(group_id, group_id))
        for group_id in used_group_ids
    )
    layout = TimelineLayout(tuple(entries), groups)
    layout.validate_for(project.timeline)
    return replace(
        project,
        revision=project.revision + 1,
        layout=layout,
        current_plan=None,
        jobs=(),
    )


@dataclass(frozen=True, slots=True)
class OptionalFeature:
    available: bool
    reason: str
    adapter: TimelineInterchangePort | None = None


def optional_otio_adapter(environ: dict[str, str] | None = None) -> OptionalFeature:
    """Resolve the optional adapter without changing default import behavior."""

    import os

    values = os.environ if environ is None else environ
    if values.get("VIDEO_CHRONICLE_EXPERIMENTAL_OTIO", "0") != "1":
        return OptionalFeature(False, "OTIO experiment is disabled")
    try:
        from .otio_adapter import NativeOtioAdapter

        adapter = NativeOtioAdapter()
    except ModuleNotFoundError as exc:
        if exc.name == "opentimelineio":
            return OptionalFeature(False, "optional dependency opentimelineio==0.18.1 is not installed")
        raise
    return OptionalFeature(True, "available", adapter)
