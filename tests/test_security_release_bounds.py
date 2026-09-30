from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

from video_chronicle import pipeline, safety
from video_chronicle.domain import SourceFingerprint
from video_chronicle.process_control import (
    ProcessOutputLimitExceeded,
    run_managed_command,
)


def test_untrusted_source_count_is_bounded_before_sort(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "MAX_SOURCE_ITEMS", 1)
    for name in ("a.mp4", "b.mp4"):
        (tmp_path / name).write_bytes(b"x")
    with pytest.raises(RuntimeError, match="item budget"):
        pipeline.collect_source_paths(tmp_path, tmp_path / "output.mp4", tmp_path / "errors.log")


def test_source_size_fails_before_hashing(tmp_path, monkeypatch):
    source = tmp_path / "large.mp4"
    source.write_bytes(b"12345")
    monkeypatch.setattr(safety, "MAX_SOURCE_BYTES", 4)
    with pytest.raises(ValueError, match="file budget"):
        SourceFingerprint.capture(source)


def test_duration_upper_bound_is_shared():
    safety.validate_source_duration(safety.MAX_SOURCE_DURATION_US)
    with pytest.raises(ValueError, match="duration budget"):
        safety.validate_source_duration(safety.MAX_SOURCE_DURATION_US + 1)


@pytest.mark.parametrize("value", [r"\\server\share\out.mp4", r"\\?\C:\out.mp4", r"\\.\C:\out.mp4"])
def test_network_device_outputs_fail_before_io(value):
    with pytest.raises(RuntimeError, match="UNC or a device"):
        safety.validate_local_write_path(Path(value))


def test_reparse_ancestor_rejected_before_log_creation(tmp_path, monkeypatch):
    parent = tmp_path / "parent"
    parent.mkdir()
    original_lstat = Path.lstat

    def fake_lstat(path):
        value = original_lstat(path)
        if path == parent:

            class Reparse:
                st_mode = value.st_mode
                st_file_attributes = getattr(
                    __import__("stat"), "FILE_ATTRIBUTE_REPARSE_POINT", 1024
                )

            return Reparse()
        return value

    monkeypatch.setattr(Path, "lstat", fake_lstat)
    with pytest.raises(RuntimeError, match="reparse"):
        pipeline.configure_logging(parent / "nested" / "errors.log")
    assert not (parent / "nested").exists()


def test_default_production_tool_deadline_is_finite(monkeypatch):
    import video_chronicle.process_control as control

    observed = []

    def fake(command, **kwargs):
        observed.append(kwargs["timeout"])
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(control, "run_managed_command", fake)
    pipeline.run_command(["trusted-tool"], "test")
    assert observed == [1800.0]


@pytest.mark.parametrize("value", [float("nan"), float("inf"), 0, -1])
def test_invalid_tool_deadline_fails_before_launch(value):
    with pytest.raises(ValueError, match="finite and positive"):
        pipeline.run_command(["nonexistent"], "test", timeout=value)


def test_live_disk_budget_kills_owned_tool(tmp_path):
    target = tmp_path / "oversized.mp4"
    started = time.monotonic()
    code = "from pathlib import Path;import sys,time;Path(sys.argv[1]).write_bytes(b'x'*16384);time.sleep(30)"
    with pytest.raises(ProcessOutputLimitExceeded, match="disk budget"):
        run_managed_command(
            [sys.executable, "-c", code, str(target)],
            cancellation=None,
            timeout=10,
            max_output_bytes=1024,
            output_file=target,
            max_output_file_bytes=8192,
        )
    assert time.monotonic() - started < 8


def test_exited_tool_disk_budget_is_checked_before_success(tmp_path):
    target = tmp_path / "oversized.mp4"
    code = "from pathlib import Path;import sys;Path(sys.argv[1]).write_bytes(b'x'*16384)"
    with pytest.raises(ProcessOutputLimitExceeded, match="disk budget"):
        run_managed_command(
            [sys.executable, "-c", code, str(target)],
            cancellation=None,
            timeout=10,
            max_output_bytes=1024,
            output_file=target,
            max_output_file_bytes=8192,
        )


def test_oversized_derived_artifact_is_not_published(tmp_path, monkeypatch):
    temporary = tmp_path / "temporary.mp4"
    temporary.write_bytes(b"12345")
    output = tmp_path / "final.mp4"
    monkeypatch.setattr(pipeline, "MAX_DERIVED_BYTES", 4)
    with pytest.raises(RuntimeError, match="file budget"):
        pipeline.publish_output(temporary, output, False)
    assert temporary.read_bytes() == b"12345" and not output.exists()


@pytest.mark.parametrize(
    "component",
    [
        "NUL.mp4",
        "CON.log",
        "aux",
        "PRN.txt",
        "COM1.mp4",
        "LPT9.log",
        "COM¹.mp4",
        "safe.mp4:stream",
        "alias.mp4.",
        "alias.mp4 ",
    ],
)
def test_windows_reserved_names_and_ads_are_rejected_without_io(component):
    with pytest.raises(RuntimeError, match="reserved Windows"):
        safety.validate_windows_write_name("C:\\safe\\" + component)


def test_windows_ordinary_drive_path_is_allowed_lexically():
    safety.validate_windows_write_name("C:\\safe\\ordinary.mp4")
