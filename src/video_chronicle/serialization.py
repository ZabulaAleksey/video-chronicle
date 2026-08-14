"""Strict JSON-compatible schema v1 for immutable project snapshots."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, NoReturn

from .project import (
    EditingClipSnapshot,
    EditingExportSnapshot,
    ExportJob,
    ExportPlanSnapshot,
    JobState,
    PresetRef,
    ProjectState,
    RenderPreset,
    RenderSettings,
    ResolvedTrim,
    Timeline,
    TimelineGroup,
    TimelineItem,
    TimelineLayout,
    TimelineLayoutEntry,
    TrimRange,
)
from .domain import ExportMode
from .overlay import OverlayConfig


SCHEMA_NAME = "video-chronicle-project"
SCHEMA_VERSION = 1
CURRENT_SCHEMA_VERSION = 2


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


def _project_to_v1_mapping(state: ProjectState) -> dict[str, Any]:
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


def _project_from_v1_mapping(payload: Any) -> ProjectState:
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


def migrate_v1_state(state: ProjectState) -> ProjectState:
    """Pure EDIT-006 migration; no bytes are written by this function."""

    if state.presets:
        return state
    settings = RenderSettings(
        mode=ExportMode.CHRONICLE,
        overlay=OverlayConfig(),
        crf=state.current_plan.crf if isinstance(state.current_plan, ExportPlanSnapshot) else 23,
        encoder_preset=state.current_plan.preset if isinstance(state.current_plan, ExportPlanSnapshot) else "medium",
    )
    preset = RenderPreset("legacy-default", 1, "Legacy default", settings)
    return ProjectState(
        project_id=state.project_id,
        timeline=state.timeline,
        current_plan=state.current_plan,
        jobs=state.jobs,
        revision=0,
        layout=TimelineLayout.identity(state.timeline),
        presets=(preset,),
        active_preset=preset.ref,
        migrated_from_v1=True,
    )


def project_to_mapping(state: ProjectState, *, force_v2: bool = False) -> dict[str, Any]:
    """Serialize legacy states as v1, and editing/durable states as strict v2."""

    if not force_v2 and not state.presets and state.revision == 0 and not state.migrated_from_v1:
        return _project_to_v1_mapping(state)
    return _project_to_v2_mapping(state)


def project_from_mapping(payload: Any, *, migrate: bool = False) -> ProjectState:
    """Strictly load v1/v2; optionally apply the pure v1 migration."""

    if not isinstance(payload, Mapping):
        _fail("root must be an object")
    version = payload.get("version")
    if version == 1:
        state = _project_from_v1_mapping(payload)
        return migrate_v1_state(state) if migrate else state
    if version == 2:
        return _project_from_v2_mapping(payload)
    _fail("unknown project schema version")


def _overlay_to_mapping(value: OverlayConfig) -> dict[str, Any]:
    return {
        "enabled": value.enabled,
        "format": value.format,
        "position": value.position,
        "horizontal_margin": value.horizontal_margin,
        "vertical_margin": value.vertical_margin,
        "font_size": value.font_size,
        "text_color": value.text_color,
        "outline_color": value.outline_color,
        "outline_width": value.outline_width,
        "font_file": None if value.font_file is None else str(value.font_file),
        "font_identity": None if value.font_identity is None else list(value.font_identity),
    }


def _settings_to_mapping(value: RenderSettings) -> dict[str, Any]:
    return {"mode": value.mode.value, "overlay": _overlay_to_mapping(value.overlay), "crf": value.crf, "encoder_preset": value.encoder_preset}


def _plan_to_mapping(plan: ExportPlanSnapshot | EditingExportSnapshot | None) -> Any:
    if plan is None:
        return None
    if isinstance(plan, ExportPlanSnapshot):
        return {"snapshot_version": 1, "snapshot": {"plan_id": plan.plan_id, "item_ids": list(plan.item_ids), "output_path": str(plan.output_path), "crf": plan.crf, "preset": plan.preset, "overwrite": plan.overwrite}}
    return {"snapshot_version": 2, "snapshot": {"plan_id": plan.plan_id, **plan.digest_fields()}}


def _project_to_v2_mapping(state: ProjectState) -> dict[str, Any]:
    if state.layout is None or not state.presets or state.active_preset is None:
        raise ProjectSerializationError("schema v2 requires layout, presets, and active_preset")
    project = {
        "project_id": state.project_id,
        "revision": state.revision,
        "timeline": {"items": [{"stable_id": item.stable_id, "source_path": str(item.source_path), "taken_at": item.taken_at.isoformat(timespec="microseconds"), "date_source": item.date_source, "date_raw_value": item.date_raw_value, "date_timezone": item.date_timezone, "date_policy_version": item.date_policy_version, "media_kind": item.media_kind, "source_duration_us": item.source_duration_us} for item in state.timeline.items]},
        "layout": {"entries": [{"item_id": entry.item_id, "trim": {"in_us": entry.trim.in_us, "out_us": entry.trim.out_us}, "group_id": entry.group_id} for entry in state.layout.entries], "groups": [{"group_id": group.group_id, "name": group.name} for group in state.layout.groups]},
        "presets": [{"preset_id": preset.preset_id, "version": preset.version, "name": preset.name, "settings": _settings_to_mapping(preset.settings)} for preset in state.presets],
        "active_preset": {"preset_id": state.active_preset.preset_id, "version": state.active_preset.version},
        "current_plan": _plan_to_mapping(state.current_plan),
        "jobs": [{"job_id": job.job_id, "plan_id": job.plan_id, "state": job.state.value, "final_output": None if job.final_output is None else str(job.final_output), "failure": job.failure} for job in state.jobs],
    }
    return {"schema": SCHEMA_NAME, "version": 2, "project": project}


def _strict_int(value: Any, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        _fail(f"{label} must be an integer >= {minimum}")
    return value


def _overlay_from_mapping(raw: Any) -> OverlayConfig:
    fields = {"enabled", "format", "position", "horizontal_margin", "vertical_margin", "font_size", "text_color", "outline_color", "outline_width", "font_file", "font_identity"}
    value = _object(raw, fields, "overlay")
    if not isinstance(value["enabled"], bool):
        _fail("overlay.enabled must be bool")
    identity = value["font_identity"]
    if identity is not None and (not isinstance(identity, list) or len(identity) != 4 or any(type(part) is not int for part in identity)):
        _fail("overlay.font_identity must be four integers or null")
    config = OverlayConfig(enabled=value["enabled"], format=_string(value["format"], "overlay.format") or "", position=_string(value["position"], "overlay.position") or "", horizontal_margin=_strict_int(value["horizontal_margin"], "horizontal_margin"), vertical_margin=_strict_int(value["vertical_margin"], "vertical_margin"), font_size=_strict_int(value["font_size"], "font_size", minimum=1), text_color=_string(value["text_color"], "text_color") or "", outline_color=_string(value["outline_color"], "outline_color") or "", outline_width=_strict_int(value["outline_width"], "outline_width"), font_file=_path(value["font_file"], "font_file", nullable=True))
    if identity is not None and config.font_identity != tuple(identity):
        _fail("overlay font identity does not match the current regular file")
    return config


def _settings_from_mapping(raw: Any) -> RenderSettings:
    value = _object(raw, {"mode", "overlay", "crf", "encoder_preset"}, "settings")
    try:
        mode = ExportMode(_string(value["mode"], "settings.mode"))
    except ValueError as exc:
        raise ProjectSerializationError("unknown export mode") from exc
    return RenderSettings(mode, _overlay_from_mapping(value["overlay"]), _strict_int(value["crf"], "settings.crf"), _string(value["encoder_preset"], "encoder_preset") or "")


def _project_from_v2_mapping(payload: Any) -> ProjectState:
    try:
        root = _object(payload, {"schema", "version", "project"}, "root")
        if root["schema"] != SCHEMA_NAME or root["version"] != 2:
            _fail("unknown project schema")
        project = _object(root["project"], {"project_id", "revision", "timeline", "layout", "presets", "active_preset", "current_plan", "jobs"}, "project")
        timeline_data = _object(project["timeline"], {"items"}, "timeline")
        if not isinstance(timeline_data["items"], list): _fail("timeline.items must be an array")
        items = []
        item_fields = {"stable_id", "source_path", "taken_at", "date_source", "date_raw_value", "date_timezone", "date_policy_version", "media_kind", "source_duration_us"}
        for index, raw in enumerate(timeline_data["items"]):
            item = _object(raw, item_fields, f"timeline.items[{index}]")
            kind = item["media_kind"]
            if kind not in {None, "photo", "video"}: _fail("invalid media_kind")
            duration = item["source_duration_us"]
            if duration is not None: duration = _strict_int(duration, "source_duration_us", minimum=1)
            items.append(TimelineItem(_string(item["stable_id"], "stable_id") or "", _path(item["source_path"], "source_path") or Path(), _datetime(item["taken_at"], "taken_at"), _string(item["date_source"], "date_source") or "", _string(item["date_raw_value"], "date_raw_value", nullable=True), _string(item["date_timezone"], "date_timezone", nullable=True), _string(item["date_policy_version"], "date_policy_version", nullable=True), kind, duration))
        timeline = Timeline(tuple(items))
        layout_data = _object(project["layout"], {"entries", "groups"}, "layout")
        if not isinstance(layout_data["entries"], list) or not isinstance(layout_data["groups"], list): _fail("layout arrays are invalid")
        groups = tuple(TimelineGroup(_string(_object(raw, {"group_id", "name"}, "group")["group_id"], "group_id") or "", _string(raw["name"], "group.name") or "") for raw in layout_data["groups"])
        entries = []
        for raw in layout_data["entries"]:
            entry = _object(raw, {"item_id", "trim", "group_id"}, "layout.entry")
            trim = _object(entry["trim"], {"in_us", "out_us"}, "trim")
            out = trim["out_us"]
            if out is not None: out = _strict_int(out, "trim.out_us", minimum=1)
            entries.append(TimelineLayoutEntry(_string(entry["item_id"], "item_id") or "", TrimRange(_strict_int(trim["in_us"], "trim.in_us"), out), _string(entry["group_id"], "group_id", nullable=True)))
        layout = TimelineLayout(tuple(entries), groups); layout.validate_for(timeline)
        if not isinstance(project["presets"], list): _fail("presets must be an array")
        presets = []
        for raw in project["presets"]:
            preset = _object(raw, {"preset_id", "version", "name", "settings"}, "preset")
            presets.append(RenderPreset(_string(preset["preset_id"], "preset_id") or "", _strict_int(preset["version"], "preset.version", minimum=1), _string(preset["name"], "preset.name") or "", _settings_from_mapping(preset["settings"])))
        active = _object(project["active_preset"], {"preset_id", "version"}, "active_preset")
        active_ref = PresetRef(_string(active["preset_id"], "preset_id") or "", _strict_int(active["version"], "preset.version", minimum=1))
        plan = _v2_plan_from_mapping(project["current_plan"])
        if not isinstance(project["jobs"], list): _fail("jobs must be an array")
        jobs = tuple(_job_from_mapping(raw) for raw in project["jobs"])
        return ProjectState(_string(project["project_id"], "project_id") or "", timeline, plan, jobs, _strict_int(project["revision"], "revision"), layout, tuple(presets), active_ref)
    except ProjectSerializationError: raise
    except (TypeError, ValueError) as exc: raise ProjectSerializationError(str(exc)) from exc


def _job_from_mapping(raw: Any) -> ExportJob:
    job = _object(raw, {"job_id", "plan_id", "state", "final_output", "failure"}, "job")
    try: state = JobState(_string(job["state"], "job.state"))
    except ValueError as exc: raise ProjectSerializationError("unknown job state") from exc
    return ExportJob(_string(job["job_id"], "job_id") or "", _string(job["plan_id"], "plan_id") or "", state, _path(job["final_output"], "final_output", nullable=True), _string(job["failure"], "failure", nullable=True))


def _v2_plan_from_mapping(raw: Any) -> ExportPlanSnapshot | EditingExportSnapshot | None:
    if raw is None: return None
    tagged = _object(raw, {"snapshot_version", "snapshot"}, "current_plan")
    version = tagged["snapshot_version"]
    snapshot = tagged["snapshot"]
    if version == 1:
        value = _object(snapshot, {"plan_id", "item_ids", "output_path", "crf", "preset", "overwrite"}, "snapshot-v1")
        if not isinstance(value["item_ids"], list) or any(not isinstance(x, str) for x in value["item_ids"]): _fail("item_ids must be strings")
        if not isinstance(value["overwrite"], bool): _fail("overwrite must be bool")
        return ExportPlanSnapshot(_string(value["plan_id"], "plan_id") or "", tuple(value["item_ids"]), _path(value["output_path"], "output_path") or Path(), _strict_int(value["crf"], "crf"), _string(value["preset"], "preset") or "", value["overwrite"])
    if version != 2: _fail("unknown snapshot version")
    value = _object(snapshot, {"plan_id", "snapshot_version", "project_id", "project_revision", "clips", "groups", "preset_ref", "settings", "output_path", "overwrite"}, "snapshot-v2")
    if value["snapshot_version"] != 2: _fail("nested snapshot version mismatch")
    if not isinstance(value["groups"], list) or not isinstance(value["clips"], list): _fail("snapshot groups/clips must be arrays")
    groups_list = []
    for raw_group in value["groups"]:
        group = _object(raw_group, {"group_id", "name"}, "snapshot.group")
        groups_list.append(TimelineGroup(_string(group["group_id"], "group_id") or "", _string(group["name"], "group.name") or ""))
    clips_list = []
    for raw_clip in value["clips"]:
        clip = _object(raw_clip, {"item_id", "trim", "group_id"}, "snapshot.clip")
        trim = _object(clip["trim"], {"in_us", "out_us"}, "snapshot.trim")
        clips_list.append(EditingClipSnapshot(_string(clip["item_id"], "item_id") or "", ResolvedTrim(_strict_int(trim["in_us"], "trim.in_us"), _strict_int(trim["out_us"], "trim.out_us", minimum=1)), _string(clip["group_id"], "group_id", nullable=True)))
    raw_ref = _object(value["preset_ref"], {"preset_id", "version"}, "snapshot.preset_ref")
    ref = PresetRef(_string(raw_ref["preset_id"], "preset_id") or "", _strict_int(raw_ref["version"], "preset.version", minimum=1))
    if not isinstance(value["overwrite"], bool): _fail("snapshot.overwrite must be bool")
    return EditingExportSnapshot(_string(value["plan_id"], "plan_id") or "", _string(value["project_id"], "project_id") or "", _strict_int(value["project_revision"], "project_revision"), tuple(clips_list), tuple(groups_list), ref, _settings_from_mapping(value["settings"]), _path(value["output_path"], "output_path") or Path(), value["overwrite"])


__all__ = [
    "ProjectSerializationError",
    "SCHEMA_NAME",
    "SCHEMA_VERSION",
    "CURRENT_SCHEMA_VERSION",
    "migrate_v1_state",
    "project_from_mapping",
    "project_to_mapping",
]
