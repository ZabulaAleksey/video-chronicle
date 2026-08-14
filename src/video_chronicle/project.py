"""Immutable, UI-independent project and export job contracts."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Iterable

from .domain import ExportMode, MediaItem
from .overlay import DEFAULT_OVERLAY_CONFIG, OverlayConfig


ITEM_ID_PREFIX = "item-v1-"
PLAN_ID_PREFIX = "plan-v1-"
EDITING_PLAN_ID_PREFIX = "plan-v2-"
TARGET_FRAME_US = 16_667
PHOTO_DURATION_US = 2_000_000


def _require_identifier(value: str, label: str) -> None:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ValueError(f"{label} must be a non-empty trimmed string")
    if any(character.isspace() for character in value):
        raise ValueError(f"{label} must not contain whitespace")


def _require_absolute_path(path: Path, label: str) -> None:
    if not isinstance(path, Path):
        raise TypeError(f"{label} must be a pathlib.Path")
    if not path.is_absolute():
        raise ValueError(f"{label} must be absolute")
    if "\x00" in str(path):
        raise ValueError(f"{label} must not contain NUL")


def normalized_source_identity(path: Path) -> str:
    """Return the local v1 path identity without accessing the filesystem."""

    _require_absolute_path(path, "source_path")
    return os.path.normcase(os.path.normpath(str(path)))


def stable_item_id(path: Path) -> str:
    identity = normalized_source_identity(path)
    digest = hashlib.sha256(f"video-chronicle/item/v1\0{identity}".encode("utf-8")).hexdigest()
    return ITEM_ID_PREFIX + digest


@dataclass(frozen=True, slots=True)
class TimelineItem:
    """One accepted source with deterministic local path identity."""

    stable_id: str
    source_path: Path
    taken_at: datetime
    date_source: str
    date_raw_value: str | None = None
    date_timezone: str | None = None
    date_policy_version: str | None = None
    media_kind: str | None = None
    source_duration_us: int | None = None

    def __post_init__(self) -> None:
        _require_absolute_path(self.source_path, "source_path")
        if self.taken_at.tzinfo is not None:
            raise ValueError("taken_at must be a wall-clock datetime without tzinfo")
        if not isinstance(self.date_source, str) or not self.date_source:
            raise ValueError("date_source must not be empty")
        for value, label in (
            (self.date_raw_value, "date_raw_value"),
            (self.date_timezone, "date_timezone"),
            (self.date_policy_version, "date_policy_version"),
        ):
            if value is not None and (not isinstance(value, str) or not value):
                raise ValueError(f"{label} must be null or a non-empty string")
        expected = stable_item_id(self.source_path)
        if self.stable_id != expected:
            raise ValueError("stable_id does not match source_path identity")
        if self.media_kind not in {None, "photo", "video"}:
            raise ValueError("media_kind must be photo, video, or null")
        if self.source_duration_us is not None and (
            isinstance(self.source_duration_us, bool)
            or not isinstance(self.source_duration_us, int)
            or self.source_duration_us <= 0
        ):
            raise ValueError("source_duration_us must be a positive integer or null")

    @classmethod
    def from_media_item(cls, item: MediaItem) -> "TimelineItem":
        path = item.path.absolute()
        decision = item.date_decision
        selected = decision.selected if decision is not None else None
        return cls(
            stable_id=stable_item_id(path),
            source_path=path,
            taken_at=item.taken_at,
            date_source=item.date_source,
            date_raw_value=selected.raw_value if selected is not None else None,
            date_timezone=selected.timezone if selected is not None else None,
            date_policy_version=decision.policy_version if decision is not None else None,
            media_kind="photo" if item.is_photo else "video",
            source_duration_us=item.source_duration_us,
        )


def timeline_sort_key(item: TimelineItem) -> tuple[datetime, str, str]:
    return item.taken_at, item.source_path.name.casefold(), item.stable_id


@dataclass(frozen=True, slots=True)
class Timeline:
    """Chronological immutable timeline in the approved v1 order."""

    items: tuple[TimelineItem, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.items, tuple):
            raise TypeError("Timeline.items must be a tuple")
        item_ids = tuple(item.stable_id for item in self.items)
        if len(set(item_ids)) != len(item_ids):
            raise ValueError("Timeline item IDs must be unique")
        if self.items != tuple(sorted(self.items, key=timeline_sort_key)):
            raise ValueError("Timeline items do not follow the approved v1 order")

    @classmethod
    def build(cls, items: Iterable[TimelineItem]) -> "Timeline":
        return cls(tuple(sorted(tuple(items), key=timeline_sort_key)))

    @property
    def item_ids(self) -> tuple[str, ...]:
        return tuple(item.stable_id for item in self.items)


def _plan_digest(
    item_ids: tuple[str, ...],
    output_path: Path,
    crf: int,
    preset: str,
    overwrite: bool,
) -> str:
    fields = (
        "video-chronicle/plan/v1",
        *item_ids,
        str(output_path),
        str(crf),
        preset,
        "1" if overwrite else "0",
    )
    return hashlib.sha256("\0".join(fields).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ExportPlanSnapshot:
    """Serializable export intent; never contains executable paths or argv."""

    plan_id: str
    item_ids: tuple[str, ...]
    output_path: Path
    crf: int
    preset: str
    overwrite: bool

    def __post_init__(self) -> None:
        if not isinstance(self.item_ids, tuple):
            raise TypeError("item_ids must be a tuple")
        if not self.item_ids or len(set(self.item_ids)) != len(self.item_ids):
            raise ValueError("item_ids must be non-empty and unique")
        for item_id in self.item_ids:
            _require_identifier(item_id, "item_id")
        _require_absolute_path(self.output_path, "output_path")
        if self.output_path.suffix.casefold() != ".mp4":
            raise ValueError("output_path must have an .mp4 extension")
        if isinstance(self.crf, bool) or not isinstance(self.crf, int) or not 0 <= self.crf <= 51:
            raise ValueError("crf must be an integer between 0 and 51")
        if not isinstance(self.preset, str) or not self.preset or self.preset.strip() != self.preset:
            raise ValueError("preset must be a non-empty trimmed string")
        if not isinstance(self.overwrite, bool):
            raise TypeError("overwrite must be bool")
        expected = PLAN_ID_PREFIX + _plan_digest(
            self.item_ids, self.output_path, self.crf, self.preset, self.overwrite
        )
        if self.plan_id != expected:
            raise ValueError("plan_id does not match snapshot contents")

    @classmethod
    def create(
        cls,
        timeline: Timeline,
        output_path: Path,
        *,
        crf: int,
        preset: str,
        overwrite: bool,
    ) -> "ExportPlanSnapshot":
        output = output_path.absolute()
        item_ids = timeline.item_ids
        plan_id = PLAN_ID_PREFIX + _plan_digest(item_ids, output, crf, preset, overwrite)
        return cls(plan_id, item_ids, output, crf, preset, overwrite)


@dataclass(frozen=True, slots=True)
class TrimRange:
    """Persisted half-open trim; ``out_us=None`` means full source."""

    in_us: int = 0
    out_us: int | None = None

    def __post_init__(self) -> None:
        if isinstance(self.in_us, bool) or not isinstance(self.in_us, int) or self.in_us < 0:
            raise ValueError("trim in_us must be a non-negative integer")
        if self.out_us is not None and (
            isinstance(self.out_us, bool)
            or not isinstance(self.out_us, int)
            or self.out_us <= self.in_us
        ):
            raise ValueError("trim out_us must be an integer greater than in_us or null")

    @property
    def is_full_source(self) -> bool:
        return self.in_us == 0 and self.out_us is None

    def resolve(self, item: TimelineItem) -> "ResolvedTrim":
        duration = item.source_duration_us
        if duration is None:
            if not self.is_full_source:
                raise ValueError("cannot trim an item with unknown source duration")
            raise ValueError("source duration is required before preview/export")
        out_us = duration if self.out_us is None else self.out_us
        if out_us - self.in_us < TARGET_FRAME_US:
            raise ValueError("trim must contain at least one target frame")
        if item.media_kind == "photo":
            if self.in_us != 0 or out_us > PHOTO_DURATION_US:
                raise ValueError("photo trim must start at zero and not exceed two seconds")
        elif item.media_kind == "video":
            if out_us > duration:
                raise ValueError("video trim exceeds source duration")
        else:
            raise ValueError("media kind is required before preview/export")
        return ResolvedTrim(self.in_us, out_us)


@dataclass(frozen=True, slots=True)
class ResolvedTrim:
    in_us: int
    out_us: int

    def __post_init__(self) -> None:
        TrimRange(self.in_us, self.out_us)
        if self.out_us - self.in_us < TARGET_FRAME_US:
            raise ValueError("resolved trim must contain at least one target frame")


@dataclass(frozen=True, slots=True)
class TimelineLayoutEntry:
    item_id: str
    trim: TrimRange = TrimRange()
    group_id: str | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.item_id, "item_id")
        if not isinstance(self.trim, TrimRange):
            raise TypeError("trim must be TrimRange")
        if self.group_id is not None:
            _require_identifier(self.group_id, "group_id")


@dataclass(frozen=True, slots=True)
class TimelineGroup:
    group_id: str
    name: str

    def __post_init__(self) -> None:
        _require_identifier(self.group_id, "group_id")
        if not isinstance(self.name, str) or not self.name.strip() or self.name != self.name.strip():
            raise ValueError("group name must be a non-empty trimmed string")


@dataclass(frozen=True, slots=True)
class TimelineLayout:
    entries: tuple[TimelineLayoutEntry, ...]
    groups: tuple[TimelineGroup, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.entries, tuple) or not isinstance(self.groups, tuple):
            raise TypeError("layout entries and groups must be tuples")
        ids = tuple(entry.item_id for entry in self.entries)
        if len(set(ids)) != len(ids):
            raise ValueError("layout item IDs must be unique")
        group_ids = tuple(group.group_id for group in self.groups)
        if len(set(group_ids)) != len(group_ids):
            raise ValueError("layout group IDs must be unique")
        known = set(group_ids)
        if any(entry.group_id not in known for entry in self.entries if entry.group_id is not None):
            raise ValueError("layout entry references an unknown group")
        for group_id in group_ids:
            positions = [i for i, entry in enumerate(self.entries) if entry.group_id == group_id]
            if len(positions) < 2 or positions != list(range(positions[0], positions[-1] + 1)):
                raise ValueError("groups must be contiguous and contain at least two items")

    @classmethod
    def identity(cls, timeline: Timeline) -> "TimelineLayout":
        return cls(tuple(TimelineLayoutEntry(item_id) for item_id in timeline.item_ids))

    def validate_for(self, timeline: Timeline) -> None:
        if tuple(sorted(entry.item_id for entry in self.entries)) != tuple(sorted(timeline.item_ids)):
            raise ValueError("layout entries must be an exact timeline permutation")
        items = {item.stable_id: item for item in timeline.items}
        for entry in self.entries:
            item = items[entry.item_id]
            if item.media_kind is None and not entry.trim.is_full_source:
                raise ValueError("unknown media kind permits only full-source trim")
            if not entry.trim.is_full_source:
                entry.trim.resolve(item)

    def move_items(self, item_ids: Iterable[str], before_item_id: str | None) -> "TimelineLayout":
        moving_requested = tuple(item_ids)
        moving = tuple(entry.item_id for entry in self.entries if entry.item_id in set(moving_requested))
        if not moving_requested or len(set(moving_requested)) != len(moving_requested) or set(moving) != set(moving_requested):
            raise ValueError("moved item IDs must be unique known layout items")
        if before_item_id is not None and before_item_id not in {entry.item_id for entry in self.entries}:
            raise ValueError("before_item_id is unknown")
        if before_item_id in moving:
            raise ValueError("cannot move items before one of the moved items")
        moving_groups = {entry.group_id for entry in self.entries if entry.item_id in moving and entry.group_id}
        for group_id in moving_groups:
            members = {entry.item_id for entry in self.entries if entry.group_id == group_id}
            if not members.issubset(moving):
                raise ValueError("a group must be moved as a complete block")
        remaining = [entry for entry in self.entries if entry.item_id not in set(moving)]
        selected = [entry for entry in self.entries if entry.item_id in set(moving)]
        index = len(remaining) if before_item_id is None else next(i for i, entry in enumerate(remaining) if entry.item_id == before_item_id)
        return TimelineLayout(tuple(remaining[:index] + selected + remaining[index:]), self.groups)

    def create_group(self, group_id: str, name: str, item_ids: Iterable[str]) -> "TimelineLayout":
        selected = tuple(item_ids)
        positions = [i for i, entry in enumerate(self.entries) if entry.item_id in set(selected)]
        if len(selected) < 2 or len(positions) != len(selected) or positions != list(range(positions[0], positions[-1] + 1)):
            raise ValueError("a group requires at least two contiguous known items")
        if any(self.entries[i].group_id is not None for i in positions):
            raise ValueError("items already belong to a group")
        group = TimelineGroup(group_id, name)
        if any(existing.group_id == group_id for existing in self.groups):
            raise ValueError("group ID already exists")
        chosen = set(selected)
        return TimelineLayout(
            tuple(replace(entry, group_id=group_id) if entry.item_id in chosen else entry for entry in self.entries),
            self.groups + (group,),
        )

    def ungroup(self, group_id: str) -> "TimelineLayout":
        if group_id not in {group.group_id for group in self.groups}:
            raise ValueError("unknown group")
        return TimelineLayout(
            tuple(replace(entry, group_id=None) if entry.group_id == group_id else entry for entry in self.entries),
            tuple(group for group in self.groups if group.group_id != group_id),
        )

    def set_trim(self, item_id: str, trim: TrimRange, timeline: Timeline) -> "TimelineLayout":
        timeline_by_id = {item.stable_id: item for item in timeline.items}
        if item_id not in timeline_by_id:
            raise ValueError("unknown item")
        if not trim.is_full_source:
            trim.resolve(timeline_by_id[item_id])
        found = False
        entries = []
        for entry in self.entries:
            if entry.item_id == item_id:
                found = True
                entries.append(replace(entry, trim=trim))
            else:
                entries.append(entry)
        if not found:
            raise ValueError("item is missing from layout")
        return TimelineLayout(tuple(entries), self.groups)


@dataclass(frozen=True, slots=True)
class RenderSettings:
    mode: ExportMode = ExportMode.CHRONICLE
    overlay: OverlayConfig = DEFAULT_OVERLAY_CONFIG
    crf: int = 23
    encoder_preset: str = "medium"

    def __post_init__(self) -> None:
        if not isinstance(self.mode, ExportMode):
            raise TypeError("mode must be ExportMode")
        if self.mode is ExportMode.JOIN and self.overlay.enabled:
            raise ValueError("Join mode requires disabled overlay")
        if isinstance(self.crf, bool) or not isinstance(self.crf, int) or not 0 <= self.crf <= 51:
            raise ValueError("crf must be between 0 and 51")
        if not isinstance(self.encoder_preset, str) or not self.encoder_preset.strip():
            raise ValueError("encoder_preset must not be empty")


@dataclass(frozen=True, slots=True)
class PresetRef:
    preset_id: str
    version: int

    def __post_init__(self) -> None:
        _require_identifier(self.preset_id, "preset_id")
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version <= 0:
            raise ValueError("preset version must be a positive integer")


@dataclass(frozen=True, slots=True)
class RenderPreset:
    preset_id: str
    version: int
    name: str
    settings: RenderSettings

    def __post_init__(self) -> None:
        PresetRef(self.preset_id, self.version)
        if not isinstance(self.name, str) or not self.name.strip() or self.name != self.name.strip():
            raise ValueError("preset name must be a non-empty trimmed string")
        if not isinstance(self.settings, RenderSettings):
            raise TypeError("settings must be RenderSettings")

    @property
    def ref(self) -> PresetRef:
        return PresetRef(self.preset_id, self.version)

    def evolve(self, *, name: str | None = None, settings: RenderSettings | None = None) -> "RenderPreset":
        return RenderPreset(self.preset_id, self.version + 1, name or self.name, settings or self.settings)


@dataclass(frozen=True, slots=True)
class EditingClipSnapshot:
    item_id: str
    trim: ResolvedTrim
    group_id: str | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.item_id, "item_id")
        if not isinstance(self.trim, ResolvedTrim):
            raise TypeError("trim must be ResolvedTrim")
        if self.group_id is not None:
            _require_identifier(self.group_id, "group_id")


def _canonical_v2_digest(fields: dict[str, object]) -> str:
    import json
    return hashlib.sha256(json.dumps(fields, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class EditingExportSnapshot:
    plan_id: str
    project_id: str
    project_revision: int
    clips: tuple[EditingClipSnapshot, ...]
    groups: tuple[TimelineGroup, ...]
    preset_ref: PresetRef
    settings: RenderSettings
    output_path: Path
    overwrite: bool
    snapshot_version: int = 2

    def __post_init__(self) -> None:
        _require_identifier(self.project_id, "project_id")
        _require_absolute_path(self.output_path, "output_path")
        if self.snapshot_version != 2:
            raise ValueError("editing snapshot version must be 2")
        if self.project_revision < 0 or not self.clips:
            raise ValueError("invalid project revision or empty clips")
        item_ids = tuple(clip.item_id for clip in self.clips)
        if len(set(item_ids)) != len(item_ids):
            raise ValueError("snapshot clip IDs must be unique")
        group_ids = tuple(group.group_id for group in self.groups)
        if len(set(group_ids)) != len(group_ids):
            raise ValueError("snapshot group IDs must be unique")
        if any(clip.group_id not in set(group_ids) for clip in self.clips if clip.group_id is not None):
            raise ValueError("snapshot clip references an unknown group")
        if self.plan_id != EDITING_PLAN_ID_PREFIX + _canonical_v2_digest(self.digest_fields()):
            raise ValueError("plan_id does not match snapshot contents")

    def digest_fields(self) -> dict[str, object]:
        return {
            "snapshot_version": 2,
            "project_id": self.project_id,
            "project_revision": self.project_revision,
            "clips": [{"item_id": c.item_id, "trim": {"in_us": c.trim.in_us, "out_us": c.trim.out_us}, "group_id": c.group_id} for c in self.clips],
            "groups": [{"group_id": g.group_id, "name": g.name} for g in self.groups],
            "preset_ref": {"preset_id": self.preset_ref.preset_id, "version": self.preset_ref.version},
            "settings": _render_settings_mapping(self.settings),
            "output_path": str(self.output_path),
            "overwrite": self.overwrite,
        }

    @classmethod
    def create(cls, *, project_id: str, project_revision: int, clips: tuple[EditingClipSnapshot, ...], groups: tuple[TimelineGroup, ...], preset_ref: PresetRef, settings: RenderSettings, output_path: Path, overwrite: bool) -> "EditingExportSnapshot":
        values = dict(project_id=project_id, project_revision=project_revision, clips=clips, groups=groups, preset_ref=preset_ref, settings=settings, output_path=output_path.absolute(), overwrite=overwrite)
        temporary = object.__new__(cls)
        for key, value in values.items():
            object.__setattr__(temporary, key, value)
        object.__setattr__(temporary, "snapshot_version", 2)
        plan_id = EDITING_PLAN_ID_PREFIX + _canonical_v2_digest(temporary.digest_fields())
        return cls(plan_id=plan_id, **values)


def _render_settings_mapping(settings: RenderSettings) -> dict[str, object]:
    overlay = settings.overlay
    return {"mode": settings.mode.value, "overlay": {"enabled": overlay.enabled, "format": overlay.format, "position": overlay.position, "horizontal_margin": overlay.horizontal_margin, "vertical_margin": overlay.vertical_margin, "font_size": overlay.font_size, "text_color": overlay.text_color, "outline_color": overlay.outline_color, "outline_width": overlay.outline_width, "font_file": None if overlay.font_file is None else str(overlay.font_file), "font_identity": None if overlay.font_identity is None else list(overlay.font_identity)}, "crf": settings.crf, "encoder_preset": settings.encoder_preset}


class JobState(str, Enum):
    PLANNED = "planned"
    RUNNING = "running"
    CANCEL_REQUESTED = "cancel-requested"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


_ALLOWED_TRANSITIONS: dict[JobState, frozenset[JobState]] = {
    JobState.PLANNED: frozenset({JobState.RUNNING}),
    JobState.RUNNING: frozenset(
        {JobState.CANCEL_REQUESTED, JobState.SUCCEEDED, JobState.FAILED}
    ),
    JobState.CANCEL_REQUESTED: frozenset({JobState.CANCELLED, JobState.FAILED}),
    JobState.SUCCEEDED: frozenset(),
    JobState.FAILED: frozenset(),
    JobState.CANCELLED: frozenset(),
}


@dataclass(frozen=True, slots=True)
class ExportJob:
    """One immutable state in an export job lifecycle."""

    job_id: str
    plan_id: str
    state: JobState = JobState.PLANNED
    final_output: Path | None = None
    failure: str | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.job_id, "job_id")
        _require_identifier(self.plan_id, "plan_id")
        if not isinstance(self.state, JobState):
            raise TypeError("state must be JobState")
        if self.final_output is not None:
            _require_absolute_path(self.final_output, "final_output")
        if self.state is JobState.SUCCEEDED:
            if self.final_output is None:
                raise ValueError("succeeded job requires final_output")
            if self.failure is not None:
                raise ValueError("succeeded job cannot carry failure")
        elif self.state is JobState.FAILED:
            if not isinstance(self.failure, str) or not self.failure:
                raise ValueError("failed job requires a failure message")
            if self.final_output is not None:
                raise ValueError("failed job cannot carry final_output")
        elif self.final_output is not None or self.failure is not None:
            raise ValueError("non-terminal job cannot carry result fields")

    def transition(
        self,
        target: JobState,
        plan: ExportPlanSnapshot,
        *,
        final_output: Path | None = None,
        failure: str | None = None,
    ) -> "ExportJob":
        """Return the next immutable state or reject an invalid transition."""

        if not isinstance(target, JobState):
            raise TypeError("target must be JobState")
        if plan.plan_id != self.plan_id:
            raise ValueError("job does not reference the supplied plan")
        if target not in _ALLOWED_TRANSITIONS[self.state]:
            raise ValueError(f"invalid job transition: {self.state.value} -> {target.value}")
        if target is JobState.SUCCEEDED:
            if final_output != plan.output_path:
                raise ValueError("succeeded job final_output must match plan output")
        return replace(
            self,
            state=target,
            final_output=final_output,
            failure=failure,
        )


@dataclass(frozen=True, slots=True)
class ProjectState:
    """Self-consistent immutable project snapshot."""

    project_id: str
    timeline: Timeline
    current_plan: ExportPlanSnapshot | EditingExportSnapshot | None = None
    jobs: tuple[ExportJob, ...] = ()
    revision: int = 0
    layout: TimelineLayout | None = None
    presets: tuple[RenderPreset, ...] = ()
    active_preset: PresetRef | None = None
    migrated_from_v1: bool = False

    def __post_init__(self) -> None:
        _require_identifier(self.project_id, "project_id")
        if not isinstance(self.timeline, Timeline):
            raise TypeError("timeline must be Timeline")
        if not isinstance(self.jobs, tuple):
            raise TypeError("jobs must be a tuple")
        if isinstance(self.revision, bool) or not isinstance(self.revision, int) or self.revision < 0:
            raise ValueError("revision must be a non-negative integer")
        layout = self.layout or TimelineLayout.identity(self.timeline)
        layout.validate_for(self.timeline)
        object.__setattr__(self, "layout", layout)
        if not isinstance(self.presets, tuple):
            raise TypeError("presets must be a tuple")
        refs = tuple(preset.ref for preset in self.presets)
        if len(set(refs)) != len(refs):
            raise ValueError("preset versions must be unique")
        versions: dict[str, list[int]] = {}
        for preset in self.presets:
            versions.setdefault(preset.preset_id, []).append(preset.version)
        if any(values != sorted(set(values)) for values in versions.values()):
            raise ValueError("preset versions must be monotonic")
        if self.active_preset is not None and self.active_preset not in set(refs):
            raise ValueError("active_preset references an unknown preset version")
        job_ids = tuple(job.job_id for job in self.jobs)
        if len(set(job_ids)) != len(job_ids):
            raise ValueError("job IDs must be unique")
        if self.current_plan is None:
            if self.jobs:
                raise ValueError("jobs require a current plan")
            return
        if not isinstance(self.current_plan, (ExportPlanSnapshot, EditingExportSnapshot)):
            raise TypeError("current_plan must be an export snapshot or None")
        known_item_ids = set(self.timeline.item_ids)
        plan_item_ids = (
            self.current_plan.item_ids
            if isinstance(self.current_plan, ExportPlanSnapshot)
            else tuple(clip.item_id for clip in self.current_plan.clips)
        )
        if any(item_id not in known_item_ids for item_id in plan_item_ids):
            raise ValueError("current plan references an unknown timeline item")
        positions = {
            item_id: index for index, item_id in enumerate(self.timeline.item_ids)
        }
        plan_positions = tuple(
            positions[item_id] for item_id in plan_item_ids
        )
        if isinstance(self.current_plan, ExportPlanSnapshot) and plan_positions != tuple(sorted(plan_positions)):
            raise ValueError("current plan item order must follow the timeline")
        for job in self.jobs:
            if job.plan_id != self.current_plan.plan_id:
                raise ValueError("job references a plan other than current_plan")
            if (
                job.state is JobState.SUCCEEDED
                and job.final_output != self.current_plan.output_path
            ):
                raise ValueError("succeeded job output does not match current plan")

    def _edited(self, **changes: object) -> "ProjectState":
        return replace(self, revision=self.revision + 1, current_plan=None, jobs=(), **changes)

    def move_items(self, item_ids: Iterable[str], before_item_id: str | None = None) -> "ProjectState":
        assert self.layout is not None
        return self._edited(layout=self.layout.move_items(item_ids, before_item_id))

    def set_trim(self, item_id: str, trim: TrimRange) -> "ProjectState":
        assert self.layout is not None
        return self._edited(layout=self.layout.set_trim(item_id, trim, self.timeline))

    def create_group(self, group_id: str, name: str, item_ids: Iterable[str]) -> "ProjectState":
        assert self.layout is not None
        return self._edited(layout=self.layout.create_group(group_id, name, item_ids))

    def ungroup(self, group_id: str) -> "ProjectState":
        assert self.layout is not None
        return self._edited(layout=self.layout.ungroup(group_id))

    def save_preset(self, preset_id: str, name: str, settings: RenderSettings) -> "ProjectState":
        versions = [preset for preset in self.presets if preset.preset_id == preset_id]
        version = max((preset.version for preset in versions), default=0) + 1
        preset = RenderPreset(preset_id, version, name, settings)
        return self._edited(presets=self.presets + (preset,), active_preset=preset.ref)

    def apply_preset(self, preset_ref: PresetRef) -> "ProjectState":
        if preset_ref not in {preset.ref for preset in self.presets}:
            raise ValueError("unknown preset version")
        return self._edited(active_preset=preset_ref)

    def resolve_active_preset(self) -> RenderPreset:
        if self.active_preset is None:
            raise ValueError("project has no active preset")
        return next(preset for preset in self.presets if preset.ref == self.active_preset)
