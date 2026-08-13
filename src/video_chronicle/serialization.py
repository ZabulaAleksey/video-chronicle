"""Strict JSON-compatible schema v1 for immutable project snapshots."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, NoReturn

from .project import (
    ExportJob,
    ExportPlanSnapshot,
    JobState,
    ProjectState,
    Timeline,
    TimelineItem,
)


SCHEMA_NAME = "video-chronicle-project"
SCHEMA_VERSION = 1


class ProjectSerializationError(ValueError):
    """A project payload does not exactly match the approved schema."""


def _fail(message: str) -> NoReturn:
    raise ProjectSerializationError(message)


def _object(value: Any, fields: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail(f"{label} must be an object")
    actual = set(value)
    if actual != fields:
        missing = sorted(fields - actual)
        extra = sorted(actual - fields)
        _fail(f"{label} fields mismatch; missing={missing}, extra={extra}")
    if any(not isinstance(key, str) for key in value):
        _fail(f"{label} field names must be strings")
    return value


def _string(value: Any, label: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str):
        _fail(f"{label} must be a string" + (" or null" if nullable else ""))
    return value


def _path(value: Any, label: str, *, nullable: bool = False) -> Path | None:
    text = _string(value, label, nullable=nullable)
    if text is None:
        return None
    if not text or "\x00" in text:
        _fail(f"{label} is not a valid path")
    path = Path(text)
    if not path.is_absolute():
        _fail(f"{label} must be absolute")
    return path


def _datetime(value: Any, label: str) -> datetime:
    text = _string(value, label)
    assert text is not None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ProjectSerializationError(f"{label} is not a valid datetime") from exc
    if parsed.tzinfo is not None or parsed.isoformat(timespec="microseconds") != text:
        _fail(f"{label} must be a canonical wall-clock datetime")
    return parsed


def project_to_mapping(state: ProjectState) -> dict[str, Any]:
    """Create a JSON-safe mapping containing only schema-v1 fields."""

    project = {
        "project_id": state.project_id,
        "timeline": {
            "items": [
                {
                    "stable_id": item.stable_id,
                    "source_path": str(item.source_path),
                    "taken_at": item.taken_at.isoformat(timespec="microseconds"),
                    "date_source": item.date_source,
                    "date_raw_value": item.date_raw_value,
                    "date_timezone": item.date_timezone,
                    "date_policy_version": item.date_policy_version,
                }
                for item in state.timeline.items
            ]
        },
        "current_plan": None
        if state.current_plan is None
        else {
            "plan_id": state.current_plan.plan_id,
            "item_ids": list(state.current_plan.item_ids),
            "output_path": str(state.current_plan.output_path),
            "crf": state.current_plan.crf,
            "preset": state.current_plan.preset,
            "overwrite": state.current_plan.overwrite,
        },
        "jobs": [
            {
                "job_id": job.job_id,
                "plan_id": job.plan_id,
                "state": job.state.value,
                "final_output": None if job.final_output is None else str(job.final_output),
                "failure": job.failure,
            }
            for job in state.jobs
        ],
    }
    return {"schema": SCHEMA_NAME, "version": SCHEMA_VERSION, "project": project}


def project_from_mapping(payload: Any) -> ProjectState:
    """Validate and create data only; this function performs no I/O or execution."""

    try:
        root = _object(payload, {"schema", "version", "project"}, "root")
        if root["schema"] != SCHEMA_NAME:
            _fail("unknown project schema")
        if isinstance(root["version"], bool) or root["version"] != SCHEMA_VERSION:
            _fail("unknown project schema version")
        project = _object(
            root["project"],
            {"project_id", "timeline", "current_plan", "jobs"},
            "project",
        )
        timeline_data = _object(project["timeline"], {"items"}, "timeline")
        if not isinstance(timeline_data["items"], list):
            _fail("timeline.items must be an array")
        items: list[TimelineItem] = []
        item_fields = {
            "stable_id",
            "source_path",
            "taken_at",
            "date_source",
            "date_raw_value",
            "date_timezone",
            "date_policy_version",
        }
        for index, raw_item in enumerate(timeline_data["items"]):
            item = _object(raw_item, item_fields, f"timeline.items[{index}]")
            items.append(
                TimelineItem(
                    stable_id=_string(item["stable_id"], "stable_id") or "",
                    source_path=_path(item["source_path"], "source_path") or Path(),
                    taken_at=_datetime(item["taken_at"], "taken_at"),
                    date_source=_string(item["date_source"], "date_source") or "",
                    date_raw_value=_string(item["date_raw_value"], "date_raw_value", nullable=True),
                    date_timezone=_string(item["date_timezone"], "date_timezone", nullable=True),
                    date_policy_version=_string(
                        item["date_policy_version"], "date_policy_version", nullable=True
                    ),
                )
            )
        timeline = Timeline(tuple(items))

        raw_plan = project["current_plan"]
        plan: ExportPlanSnapshot | None = None
        if raw_plan is not None:
            plan_data = _object(
                raw_plan,
                {"plan_id", "item_ids", "output_path", "crf", "preset", "overwrite"},
                "current_plan",
            )
            if not isinstance(plan_data["item_ids"], list) or any(
                not isinstance(value, str) for value in plan_data["item_ids"]
            ):
                _fail("current_plan.item_ids must be an array of strings")
            if isinstance(plan_data["crf"], bool) or not isinstance(plan_data["crf"], int):
                _fail("current_plan.crf must be an integer")
            if not isinstance(plan_data["overwrite"], bool):
                _fail("current_plan.overwrite must be bool")
            plan = ExportPlanSnapshot(
                plan_id=_string(plan_data["plan_id"], "plan_id") or "",
                item_ids=tuple(plan_data["item_ids"]),
                output_path=_path(plan_data["output_path"], "output_path") or Path(),
                crf=plan_data["crf"],
                preset=_string(plan_data["preset"], "preset") or "",
                overwrite=plan_data["overwrite"],
            )

        if not isinstance(project["jobs"], list):
            _fail("jobs must be an array")
        jobs: list[ExportJob] = []
        for index, raw_job in enumerate(project["jobs"]):
            job = _object(
                raw_job,
                {"job_id", "plan_id", "state", "final_output", "failure"},
                f"jobs[{index}]",
            )
            state_text = _string(job["state"], "job.state")
            try:
                job_state = JobState(state_text)
            except ValueError as exc:
                raise ProjectSerializationError("unknown job state") from exc
            jobs.append(
                ExportJob(
                    job_id=_string(job["job_id"], "job_id") or "",
                    plan_id=_string(job["plan_id"], "job.plan_id") or "",
                    state=job_state,
                    final_output=_path(job["final_output"], "final_output", nullable=True),
                    failure=_string(job["failure"], "failure", nullable=True),
                )
            )
        return ProjectState(
            project_id=_string(project["project_id"], "project_id") or "",
            timeline=timeline,
            current_plan=plan,
            jobs=tuple(jobs),
        )
    except ProjectSerializationError:
        raise
    except (TypeError, ValueError) as exc:
        raise ProjectSerializationError(str(exc)) from exc


__all__ = [
    "ProjectSerializationError",
    "SCHEMA_NAME",
    "SCHEMA_VERSION",
    "project_from_mapping",
    "project_to_mapping",
]
