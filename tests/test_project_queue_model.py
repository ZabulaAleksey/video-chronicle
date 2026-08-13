from __future__ import annotations

import copy
import hashlib
import json
import sys
from dataclasses import FrozenInstanceError, replace
from datetime import datetime
from pathlib import Path

import pytest

from video_chronicle.domain import DateCandidate, DateDecision, MediaItem
from video_chronicle.project import (
    ExportJob,
    ExportPlanSnapshot,
    JobState,
    ProjectState,
    Timeline,
    TimelineItem,
    stable_item_id,
)
from video_chronicle.repository import (
    InMemoryProjectRepository,
    ProjectNotFoundError,
    ProjectRepository,
)
from video_chronicle.serialization import (
    ProjectSerializationError,
    project_from_mapping,
    project_to_mapping,
)


def absolute_path(tmp_path: Path, name: str) -> Path:
    return (tmp_path / name).absolute()


def make_item(tmp_path: Path, name: str, taken_at: datetime) -> TimelineItem:
    path = absolute_path(tmp_path, name)
    return TimelineItem(
        stable_id=stable_item_id(path),
        source_path=path,
        taken_at=taken_at,
        date_source="filename",
        date_raw_value="20240102_030405",
        date_policy_version="DATE-001/v1",
    )


def make_project(tmp_path: Path, *, state: JobState = JobState.PLANNED) -> ProjectState:
    timeline = Timeline.build(
        [
            make_item(tmp_path, "B.mp4", datetime(2024, 1, 2, 3, 4, 5)),
            make_item(tmp_path, "a.jpg", datetime(2024, 1, 2, 3, 4, 5)),
        ]
    )
    plan = ExportPlanSnapshot.create(
        timeline,
        absolute_path(tmp_path, "result.mp4"),
        crf=20,
        preset="medium",
        overwrite=False,
    )
    job = ExportJob("job-1", plan.plan_id)
    if state is JobState.RUNNING:
        job = job.transition(JobState.RUNNING, plan)
    elif state is JobState.SUCCEEDED:
        job = job.transition(JobState.RUNNING, plan).transition(
            JobState.SUCCEEDED, plan, final_output=plan.output_path
        )
    elif state is JobState.FAILED:
        job = job.transition(JobState.RUNNING, plan).transition(
            JobState.FAILED, plan, failure="encoder failed"
        )
    return ProjectState("project-1", timeline, plan, (job,))


def test_timeline_stable_ids_and_approved_order_are_deterministic(tmp_path: Path) -> None:
    later = make_item(tmp_path, "c.mp4", datetime(2024, 2, 1))
    same_b = make_item(tmp_path, "B.mp4", datetime(2024, 1, 1))
    same_a = make_item(tmp_path, "a.mp4", datetime(2024, 1, 1))

    first = Timeline.build([later, same_b, same_a])
    second = Timeline.build([same_a, later, same_b])

    assert first == second
    assert [item.source_path.name for item in first.items] == ["a.mp4", "B.mp4", "c.mp4"]
    assert stable_item_id(same_a.source_path) == same_a.stable_id
    assert stable_item_id(same_a.source_path) != stable_item_id(same_b.source_path)


def test_timeline_rejects_duplicate_ids_and_noncanonical_order(tmp_path: Path) -> None:
    first = make_item(tmp_path, "a.mp4", datetime(2024, 1, 1))
    second = make_item(tmp_path, "b.mp4", datetime(2024, 1, 2))
    with pytest.raises(ValueError, match="unique"):
        Timeline((first, first))
    with pytest.raises(ValueError, match="approved"):
        Timeline((second, first))


def test_timeline_item_from_media_preserves_date_provenance(tmp_path: Path) -> None:
    path = absolute_path(tmp_path, "source.mov")
    candidate = DateCandidate(
        datetime(2024, 3, 4, 5, 6, 7),
        "2024-03-04T05:06:07+02:00",
        "metadata",
        "creation_time",
        "Creation_Time",
        "format",
        "+02:00",
        0,
    )
    decision = DateDecision(candidate, (candidate,), (), "DATE-001/v1")
    source = MediaItem(path, candidate.wall_time, False, True, candidate.source, decision)

    actual = TimelineItem.from_media_item(source)

    assert actual.date_raw_value == candidate.raw_value
    assert actual.date_timezone == "+02:00"
    assert actual.date_policy_version == "DATE-001/v1"


def test_models_are_immutable_and_require_consistent_ids(tmp_path: Path) -> None:
    item = make_item(tmp_path, "a.mp4", datetime(2024, 1, 1))
    with pytest.raises(FrozenInstanceError):
        item.date_source = "metadata"  # type: ignore[misc]
    with pytest.raises(ValueError, match="stable_id"):
        replace(item, stable_id="item-v1-wrong")


def test_export_snapshot_plan_id_is_content_deterministic(tmp_path: Path) -> None:
    timeline = Timeline.build([make_item(tmp_path, "a.mp4", datetime(2024, 1, 1))])
    output = absolute_path(tmp_path, "out.mp4")
    first = ExportPlanSnapshot.create(timeline, output, crf=20, preset="medium", overwrite=False)
    second = ExportPlanSnapshot.create(timeline, output, crf=20, preset="medium", overwrite=False)
    changed = ExportPlanSnapshot.create(timeline, output, crf=21, preset="medium", overwrite=False)
    assert first == second
    assert first.plan_id != changed.plan_id
    assert set(first.__dataclass_fields__) == {
        "plan_id", "item_ids", "output_path", "crf", "preset", "overwrite"
    }


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (JobState.PLANNED, JobState.RUNNING),
        (JobState.RUNNING, JobState.CANCEL_REQUESTED),
        (JobState.RUNNING, JobState.SUCCEEDED),
        (JobState.RUNNING, JobState.FAILED),
        (JobState.CANCEL_REQUESTED, JobState.CANCELLED),
        (JobState.CANCEL_REQUESTED, JobState.FAILED),
    ],
)
def test_job_transition_table_accepts_documented_edges(
    tmp_path: Path, source: JobState, target: JobState
) -> None:
    project = make_project(tmp_path)
    plan = project.current_plan
    assert plan is not None
    job = project.jobs[0]
    if source is not JobState.PLANNED:
        job = job.transition(JobState.RUNNING, plan)
        if source is JobState.CANCEL_REQUESTED:
            job = job.transition(JobState.CANCEL_REQUESTED, plan)
    kwargs: dict[str, object] = {}
    if target is JobState.SUCCEEDED:
        kwargs["final_output"] = plan.output_path
    elif target is JobState.FAILED:
        kwargs["failure"] = "failed"
    assert job.transition(target, plan, **kwargs).state is target


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (JobState.PLANNED, JobState.SUCCEEDED),
        (JobState.PLANNED, JobState.FAILED),
        (JobState.RUNNING, JobState.CANCELLED),
        (JobState.CANCEL_REQUESTED, JobState.SUCCEEDED),
        (JobState.SUCCEEDED, JobState.RUNNING),
        (JobState.FAILED, JobState.RUNNING),
        (JobState.CANCELLED, JobState.RUNNING),
    ],
)
def test_job_transition_table_rejects_invalid_and_terminal_edges(
    tmp_path: Path, source: JobState, target: JobState
) -> None:
    project = make_project(tmp_path)
    plan = project.current_plan
    assert plan is not None
    job = project.jobs[0]
    if source is not JobState.PLANNED:
        job = job.transition(JobState.RUNNING, plan)
        if source is JobState.CANCEL_REQUESTED:
            job = job.transition(JobState.CANCEL_REQUESTED, plan)
        elif source is JobState.SUCCEEDED:
            job = job.transition(JobState.SUCCEEDED, plan, final_output=plan.output_path)
        elif source is JobState.FAILED:
            job = job.transition(JobState.FAILED, plan, failure="failed")
        elif source is JobState.CANCELLED:
            job = job.transition(JobState.CANCEL_REQUESTED, plan).transition(
                JobState.CANCELLED, plan
            )
    with pytest.raises(ValueError, match="invalid job transition"):
        job.transition(target, plan)


def test_success_requires_exact_plan_output(tmp_path: Path) -> None:
    project = make_project(tmp_path, state=JobState.RUNNING)
    plan = project.current_plan
    assert plan is not None
    job = project.jobs[0]
    with pytest.raises(ValueError, match="must match"):
        job.transition(JobState.SUCCEEDED, plan)
    with pytest.raises(ValueError, match="must match"):
        job.transition(JobState.SUCCEEDED, plan, final_output=absolute_path(tmp_path, "other.mp4"))


def test_project_rejects_unknown_plan_items_jobs_and_duplicate_jobs(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    plan = project.current_plan
    assert plan is not None
    other_timeline = Timeline.build([make_item(tmp_path, "other.mp4", datetime(2024, 1, 3))])
    with pytest.raises(ValueError, match="unknown timeline item"):
        ProjectState("project-1", other_timeline, plan, project.jobs)
    with pytest.raises(ValueError, match="other than current_plan"):
        ProjectState("project-1", project.timeline, plan, (replace(project.jobs[0], plan_id="other-plan"),))
    with pytest.raises(ValueError, match="unique"):
        ProjectState("project-1", project.timeline, plan, (project.jobs[0], project.jobs[0]))
    reversed_plan = ExportPlanSnapshot(
        plan_id="plan-v1-" + hashlib.sha256(
            "\0".join(
                (
                    "video-chronicle/plan/v1",
                    *reversed(plan.item_ids),
                    str(plan.output_path),
                    str(plan.crf),
                    plan.preset,
                    "1" if plan.overwrite else "0",
                )
            ).encode("utf-8")
        ).hexdigest(),
        item_ids=tuple(reversed(plan.item_ids)),
        output_path=plan.output_path,
        crf=plan.crf,
        preset=plan.preset,
        overwrite=plan.overwrite,
    )
    with pytest.raises(ValueError, match="order must follow"):
        ProjectState("project-1", project.timeline, reversed_plan)


@pytest.mark.parametrize("state", [JobState.PLANNED, JobState.SUCCEEDED, JobState.FAILED])
def test_schema_v1_exact_json_round_trip(tmp_path: Path, state: JobState) -> None:
    project = make_project(tmp_path, state=state)
    mapping = project_to_mapping(project)
    encoded = json.dumps(mapping, ensure_ascii=False)
    decoded = json.loads(encoded)
    assert project_from_mapping(decoded) == project
    assert project_to_mapping(project_from_mapping(decoded)) == mapping
    assert set(mapping) == {"schema", "version", "project"}


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.update(version=2),
        lambda value: value.update(schema="other"),
        lambda value: value.update(extra=True),
        lambda value: value.pop("project"),
        lambda value: value["project"].update(extra=True),
        lambda value: value["project"]["timeline"]["items"][0].update(extra=True),
        lambda value: value["project"]["timeline"]["items"][0].update(source_path="relative.mp4"),
        lambda value: value["project"]["timeline"]["items"][0].update(taken_at="not-a-date"),
        lambda value: value["project"]["timeline"]["items"][0].update(stable_id="tampered"),
        lambda value: value["project"]["current_plan"].update(plan_id="tampered"),
        lambda value: value["project"]["jobs"][0].update(state="unknown"),
        lambda value: value["project"]["jobs"][0].update(plan_id="unknown-plan"),
    ],
)
def test_schema_rejects_unknown_extra_missing_and_corrupt_data(
    tmp_path: Path, mutation
) -> None:
    payload = copy.deepcopy(project_to_mapping(make_project(tmp_path)))
    mutation(payload)
    with pytest.raises(ProjectSerializationError):
        project_from_mapping(payload)


def test_schema_rejects_noncanonical_date_and_wrong_scalar_types(tmp_path: Path) -> None:
    payload = project_to_mapping(make_project(tmp_path))
    payload["project"]["timeline"]["items"][0]["taken_at"] = "2024-01-02T03:04:05"
    with pytest.raises(ProjectSerializationError, match="canonical"):
        project_from_mapping(payload)

    payload = project_to_mapping(make_project(tmp_path))
    payload["project"]["current_plan"]["crf"] = True
    with pytest.raises(ProjectSerializationError, match="integer"):
        project_from_mapping(payload)


def test_repository_replaces_by_id_and_keeps_project_snapshots_isolated(tmp_path: Path) -> None:
    repository = InMemoryProjectRepository()
    assert isinstance(repository, ProjectRepository)
    first = make_project(tmp_path)
    second = replace(first, jobs=(first.jobs[0].transition(JobState.RUNNING, first.current_plan),))  # type: ignore[arg-type]
    repository.save(first)
    repository.save(second)

    assert repository.get(first.project_id) == second
    assert repository.list_project_ids() == ("project-1",)
    with pytest.raises(ProjectNotFoundError):
        repository.get("missing")
    another_repository = InMemoryProjectRepository()
    with pytest.raises(ProjectNotFoundError):
        another_repository.get("project-1")


def test_model_import_has_no_qt_or_subprocess_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "video_chronicle.project",
        "video_chronicle.repository",
        "video_chronicle.serialization",
    ):
        sys.modules.pop(name, None)
    before_qt = {name for name in sys.modules if name.startswith("PySide6")}

    def forbidden(*args, **kwargs):
        raise AssertionError("model import attempted to start a process")

    import subprocess

    monkeypatch.setattr(subprocess, "run", forbidden)
    __import__("video_chronicle.project")
    __import__("video_chronicle.repository")
    __import__("video_chronicle.serialization")
    after_qt = {name for name in sys.modules if name.startswith("PySide6")}
    assert after_qt == before_qt
