from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from video_chronicle.domain import MediaError
from video_chronicle.metadata import (
    POLICY_VERSION,
    decide_date,
    metadata_candidates,
    parse_datetime_text,
)
from video_chronicle.pipeline import inspect_item


def test_priority_is_case_insensitive_and_skips_invalid_occurrences() -> None:
    probe = {
        "format": {
            "tags": {
                "CrEaTiOn_TiMe": "not-a-date",
                "DATE_TIME_ORIGINAL": "2024:02:03 04:05:06",
            }
        },
        "streams": [
            {"tags": {"CREATION_TIME": "2024-01-02T03:04:05Z"}}
        ],
    }

    candidates = metadata_candidates(probe)

    assert [candidate.key for candidate in candidates] == [
        "creation_time",
        "date_time_original",
    ]
    assert candidates[0].raw_key == "CREATION_TIME"
    assert candidates[0].location == "stream:0"
    assert candidates[0].timezone == "Z"


@pytest.mark.parametrize(
    ("raw", "expected_timezone"),
    [
        ("2024-01-02T03:04:05Z", "Z"),
        ("2024-01-02T03:04:05+03:00", "+03:00"),
        ("2024:01:02 03:04:05+0300", "+0300"),
        ("UTC 2024-01-02 03:04:05", "UTC"),
        ("2024-01-02 03:04:05", None),
    ],
)
def test_timezone_is_retained_without_wall_clock_conversion(
    raw: str, expected_timezone: str | None
) -> None:
    probe = {"format": {"tags": {"creation_time": raw}}}

    candidate = metadata_candidates(probe)[0]

    assert candidate.wall_time == datetime(2024, 1, 2, 3, 4, 5)
    assert candidate.wall_time.tzinfo is None
    assert candidate.timezone == expected_timezone
    assert candidate.raw_value == raw
    assert parse_datetime_text(raw) == candidate.wall_time


def test_decision_retains_filename_and_timezone_conflicts() -> None:
    path = Path("семья_20250102_030405.mp4")
    probe = {
        "format": {"tags": {"creation_time": "2024-01-02T03:04:05Z"}},
        "streams": [
            {"tags": {"creation_time": "2024-01-02T03:04:05+03:00"}}
        ],
    }

    first = decide_date(probe, path)
    second = decide_date(probe, path)

    assert first == second
    assert first is not None
    assert first.policy_version == POLICY_VERSION
    assert first.selected.source == "metadata:creation_time"
    assert [candidate.origin for candidate in first.all_valid] == [
        "metadata",
        "metadata",
        "filename",
    ]
    assert first.all_valid[-1].raw_value == "20250102_030405"
    assert first.conflicts == first.all_valid[1:]


def test_equal_recorded_values_are_not_conflicts() -> None:
    probe = {
        "format": {"tags": {"creation_time": "2024-01-02 03:04:05"}},
        "streams": [
            {"tags": {"date_time_original": "2024:01:02 03:04:05"}}
        ],
    }

    decision = decide_date(probe, Path("без-даты.mp4"))

    assert decision is not None
    assert len(decision.all_valid) == 2
    assert decision.conflicts == ()


def test_filename_is_fallback_but_still_visible_with_metadata() -> None:
    with_metadata = decide_date(
        {"format": {"tags": {"date": "2024-01-02 03:04:05"}}},
        Path("clip_20250102_030405.mp4"),
    )
    filename_only = decide_date({}, Path("clip_20250102_030405.mp4"))

    assert with_metadata is not None
    assert with_metadata.selected.source == "metadata:date"
    assert with_metadata.all_valid[-1].source == "filename"
    assert filename_only is not None
    assert filename_only.selected.source == "filename"


def test_missing_date_is_explicit_and_inspection_rejects_item() -> None:
    path = Path("нет-даты.mp4")
    probe = {"streams": [{"codec_type": "video"}]}

    assert decide_date(probe, path) is None
    with pytest.raises(MediaError, match="no supported creation date"):
        inspect_item(
            path,
            "ffprobe",
            lambda _path, _ffprobe, _runner: probe,
            lambda *args, **kwargs: None,
        )


def test_inspection_exposes_typed_date_decision_to_consumers() -> None:
    path = Path("clip_20250102_030405.mp4")
    probe = {
        "format": {"tags": {"creation_time": "2024-01-02T03:04:05Z"}},
        "streams": [{"codec_type": "video"}],
    }

    item = inspect_item(
        path,
        "ffprobe",
        lambda _path, _ffprobe, _runner: probe,
        lambda *args, **kwargs: None,
    )

    assert item.taken_at == datetime(2024, 1, 2, 3, 4, 5)
    assert item.date_source == "metadata:creation_time"
    assert item.date_decision is not None
    assert item.date_decision.selected.timezone == "Z"


def test_export_plan_excludes_missing_date_and_keeps_diagnostic(
    tmp_path: Path,
) -> None:
    import logging
    import subprocess

    from video_chronicle.application import plan_export
    from video_chronicle.domain import ExportRequest
    from video_chronicle.ports import PipelinePorts
    from video_chronicle import pipeline

    input_dir = tmp_path / "input"
    input_dir.mkdir()
    dated = input_dir / "clip_20240102_030405.mp4"
    missing = input_dir / "нет-даты.mp4"
    dated.write_bytes(b"dated")
    missing.write_bytes(b"missing")
    request = ExportRequest(
        input_dir=input_dir,
        output=tmp_path / "result.mp4",
        error_log=tmp_path / "errors.log",
        ffmpeg="ffmpeg",
        ffprobe="ffprobe",
        font_file=None,
        crf=20,
        preset="medium",
        overwrite=False,
        keep_work=False,
    )
    runner = lambda command, context, **kwargs: subprocess.CompletedProcess(
        command, 0, "", ""
    )
    ports = PipelinePorts(
        command_runner=runner,
        probe_media=lambda path, ffprobe, command_runner: {
            "streams": [{"codec_type": "video"}]
        },
        inspect_item=pipeline.inspect_item,
        normalize_item=pipeline.normalize_item,
        concatenate=pipeline.concatenate,
        publish_output=pipeline.publish_output,
        collect_source_paths=lambda *args: [missing, dated],
        create_workspace=pipeline.create_workspace,
        cleanup_workspace=pipeline.cleanup_workspace,
        validate_source=lambda input_dir, source: None,
    )

    plan = plan_export(request, ports, logging.getLogger("test.date.plan"))

    assert tuple(item.path for item in plan.items) == (dated,)
    assert plan.inspection_failures[0][0] == missing
    assert "no supported creation date" in plan.inspection_failures[0][1]
