"""Immutable, UI-independent project and export job contracts."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Iterable

from .domain import MediaItem


ITEM_ID_PREFIX = "item-v1-"
PLAN_ID_PREFIX = "plan-v1-"


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
    current_plan: ExportPlanSnapshot | None = None
    jobs: tuple[ExportJob, ...] = ()

    def __post_init__(self) -> None:
        _require_identifier(self.project_id, "project_id")
        if not isinstance(self.timeline, Timeline):
            raise TypeError("timeline must be Timeline")
        if not isinstance(self.jobs, tuple):
            raise TypeError("jobs must be a tuple")
        job_ids = tuple(job.job_id for job in self.jobs)
        if len(set(job_ids)) != len(job_ids):
            raise ValueError("job IDs must be unique")
        if self.current_plan is None:
            if self.jobs:
                raise ValueError("jobs require a current plan")
            return
        if not isinstance(self.current_plan, ExportPlanSnapshot):
            raise TypeError("current_plan must be ExportPlanSnapshot or None")
        known_item_ids = set(self.timeline.item_ids)
        if any(item_id not in known_item_ids for item_id in self.current_plan.item_ids):
            raise ValueError("current plan references an unknown timeline item")
        positions = {
            item_id: index for index, item_id in enumerate(self.timeline.item_ids)
        }
        plan_positions = tuple(
            positions[item_id] for item_id in self.current_plan.item_ids
        )
        if plan_positions != tuple(sorted(plan_positions)):
            raise ValueError("current plan item order must follow the timeline")
        for job in self.jobs:
            if job.plan_id != self.current_plan.plan_id:
                raise ValueError("job references a plan other than current_plan")
            if (
                job.state is JobState.SUCCEEDED
                and job.final_output != self.current_plan.output_path
            ):
                raise ValueError("succeeded job output does not match current plan")
