from __future__ import annotations

from datetime import datetime, timedelta, timezone
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
        "date_time_original",
        "creation_time",
    ]
    assert candidates[0].raw_key == "DATE_TIME_ORIGINAL"
    assert candidates[0].location == "format"
    assert candidates[1].timezone == "Z"


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
def test_timezone_provenance_is_retained_after_candidate_resolution(
    raw: str, expected_timezone: str | None
) -> None:
    probe = {"format": {"tags": {"creation_time": raw}}}

    candidate = metadata_candidates(probe, local_timezone=timezone.utc)[0]

    assert candidate.wall_time == datetime(2024, 1, 2, 3, 4, 5)
    assert candidate.wall_time.tzinfo is None
    assert candidate.timezone == expected_timezone
    assert candidate.raw_value == raw
    assert parse_datetime_text(raw) == candidate.wall_time


def test_explicit_quicktime_wall_clock_wins_over_generic_utc_creation_time() -> None:
    probe = {
        "format": {
            "tags": {
                "creation_time": "2024-06-01T07:15:30Z",
                "com.apple.quicktime.creationdate": "2024-06-01T10:15:30+03:00",
            }
        }
    }

    decision = decide_date(
        probe, Path("clip.mp4"), local_timezone=timezone.utc
    )

    assert decision is not None
    assert decision.selected.source == "metadata:com.apple.quicktime.creationdate"
    assert decision.selected.wall_time == datetime(2024, 6, 1, 10, 15, 30)
    assert decision.selected.timezone == "+03:00"
    assert decision.selected.raw_value == "2024-06-01T10:15:30+03:00"
    assert decision.conflicts[0].source == "metadata:creation_time"
    assert decision.conflicts[0].wall_time == datetime(2024, 6, 1, 7, 15, 30)


@pytest.mark.parametrize(
    "raw_value",
    ["2026-07-21T06:41:11Z", "UTC 2026-07-21 06:41:11"],
)
def test_generic_utc_creation_time_is_displayed_in_injected_local_timezone(
    raw_value: str,
) -> None:
    probe = {
        "format": {"tags": {"creation_time": raw_value}}
    }

    decision = decide_date(
        probe,
        Path("20260721_094111.mp4"),
        local_timezone=timezone(timedelta(hours=3)),
    )

    assert decision is not None
    assert decision.selected.source == "metadata:creation_time"
    assert decision.selected.wall_time == datetime(2026, 7, 21, 9, 41, 11)
    assert decision.selected.raw_value == raw_value
    assert decision.selected.timezone in {"Z", "UTC"}
    assert decision.all_valid[-1].source == "filename"
    assert decision.all_valid[-1].wall_time == datetime(2026, 7, 21, 9, 41, 11)


def test_decision_retains_filename_and_timezone_conflicts() -> None:
    path = Path("семья_20250102_030405.mp4")
    probe = {
        "format": {"tags": {"creation_time": "2024-01-02T03:04:05Z"}},
        "streams": [
            {"tags": {"creation_time": "2024-01-02T03:04:05+03:00"}}
        ],
    }

    first = decide_date(probe, path, local_timezone=timezone.utc)
    second = decide_date(probe, path, local_timezone=timezone.utc)

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
    path = Path("20260721_094111.mp4")
    probe = {
        "format": {"tags": {"creation_time": "2026-07-21T06:41:11Z"}},
        "streams": [{"codec_type": "video"}],
    }

    item = inspect_item(
        path,
        "ffprobe",
        lambda _path, _ffprobe, _runner: probe,
        lambda *args, **kwargs: None,
        local_timezone=timezone(timedelta(hours=3)),
    )

    assert item.taken_at == datetime(2026, 7, 21, 9, 41, 11)
    assert item.date_source == "metadata:creation_time"
    assert item.date_decision is not None
    assert item.date_decision.selected.timezone == "Z"
    assert item.date_decision.selected.raw_value == "2026-07-21T06:41:11Z"


def test_export_plan_excludes_missing_date_and_keeps_diagnostic(
    tmp_path: Path,
) -> None:
    import logging
    import subprocess

    from video_chronicle.application import plan_export
    from video_chronicle.domain import ExportRequest
    from video_chronicle.overlay import OverlayConfig
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
        crf=20,
        preset="medium",
        overwrite=False,
        keep_work=False,
        overlay=OverlayConfig(enabled=False),
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
