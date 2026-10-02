from __future__ import annotations
import os
import sys
import time
from pathlib import Path
import pytest
from gui_contract import create_run_request
from video_chronicle_gui import CliProcessAdapter
from video_chronicle.process_control import ProcessControlError, run_managed_command


def wait(qapp, predicate, seconds=7):
    deadline = time.monotonic() + seconds
    while not predicate() and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    assert predicate()


def request(tmp_path):
    (tmp_path / "input").mkdir(exist_ok=True)
    return create_run_request(
        input_dir_text=str(tmp_path / "input"),
        output_text=str(tmp_path / "result.mp4"),
        ffmpeg_text="ffmpeg",
        ffprobe_text="ffprobe",
        crf=20,
        preset_text="medium",
    )


def setup(qapp, tmp_path, body, **options):
    script = tmp_path / "helper cli.py"
    script.write_text(body, encoding="utf-8")
    adapter = CliProcessAdapter(
        cli_script=script, python_executable=sys.executable, **options
    )
    completions = []
    chunks = []
    adapter.completed.connect(lambda ok, msg: completions.append((ok, msg)))
    adapter.output_received.connect(chunks.append)
    return adapter, completions, chunks, request(tmp_path)


@pytest.mark.skipif(os.name != "nt", reason="Windows Job descendant proof")
def test_legacy_timeout_reaps_descendant_before_completion(qapp, tmp_path):
    marker = tmp_path / "child-survived"
    child = f"import time,pathlib; p=pathlib.Path({str(marker)!r}); i=0\nwhile True:\n p.write_text(str(i)); i+=1; time.sleep(.02)"
    body = f"import subprocess,sys,time;subprocess.Popen([sys.executable,'-c',{child!r}]);time.sleep(20)"
    adapter, done, _, req = setup(qapp, tmp_path, body, timeout=0.5)
    adapter.start(req)
    wait(qapp, lambda: bool(done))
    assert len(done) == 1 and done[0][0] is False
    assert "ProcessTimedOut" in done[0][1]
    assert not adapter.is_running and not req.output.exists()
    assert marker.exists()
    final_content = marker.read_bytes()
    until = time.monotonic() + 0.3
    while time.monotonic() < until:
        qapp.processEvents()
        time.sleep(0.01)
    assert marker.read_bytes() == final_content


def test_legacy_output_overflow_fails_once(qapp, tmp_path):
    adapter, done, chunks, req = setup(
        qapp,
        tmp_path,
        "import sys,time;sys.stderr.write('x'*10000);sys.stderr.flush();time.sleep(10)",
        max_output_bytes=128,
    )
    adapter.start(req)
    wait(qapp, lambda: bool(done))
    assert len(done) == 1 and not done[0][0]
    assert "ProcessOutputLimitExceeded" in done[0][1]
    assert sum(len(s) for s in chunks) < 256
    assert not req.output.exists()


def test_legacy_streams_split_utf8_before_finish_and_keeps_cwd(qapp, tmp_path):
    body = "import sys,time,pathlib;sys.stdout.buffer.write(bytes([208]));sys.stdout.buffer.flush();time.sleep(.1);sys.stdout.buffer.write(bytes([175]));sys.stdout.buffer.flush();time.sleep(.7);pathlib.Path('result.mp4').write_bytes(b'ok')"
    adapter, done, chunks, req = setup(qapp, tmp_path, body)
    adapter.start(req)
    wait(qapp, lambda: "Я" in "".join(chunks))
    assert not done and adapter.is_running
    wait(qapp, lambda: bool(done))
    assert done[0][0] and req.output.read_bytes() == b"ok"
    assert "�" not in "".join(chunks)


def test_legacy_cancel_delivers_failure_after_reap(qapp, tmp_path):
    adapter, done, _, req = setup(qapp, tmp_path, "import time;time.sleep(20)")
    adapter.start(req)
    assert adapter.request_cancel()
    wait(qapp, lambda: bool(done))
    assert len(done) == 1 and not done[0][0]
    assert "ProcessCancelled" in done[0][1]
    assert not adapter.is_running


def test_legacy_adapter_reusable_after_failure(qapp, tmp_path):
    adapter, done, _, req = setup(qapp, tmp_path, "raise SystemExit(3)")
    for count in (1, 2):
        adapter.start(req)
        wait(qapp, lambda: len(done) == count)
        assert done[-1] == (False, "Экспорт завершился с кодом 3.")


@pytest.mark.parametrize(
    "options",
    [
        {"timeout": float("inf")},
        {"timeout": 0},
        {"max_output_bytes": True},
        {"max_output_bytes": 0},
    ],
)
def test_legacy_profile_rejects_unbounded_values(qapp, tmp_path, options):
    with pytest.raises(ValueError):
        CliProcessAdapter(**options)


def test_reader_callback_failure_is_terminal_and_reaps_root(tmp_path):
    def fail(_):
        raise RuntimeError("private callback detail")

    start = time.monotonic()
    with pytest.raises(ProcessControlError, match="tool output reader failed") as error:
        run_managed_command(
            [sys.executable, "-c", "import time;print('x',flush=True);time.sleep(20)"],
            cancellation=None,
            timeout=10,
            max_output_bytes=1024,
            output_received=fail,
        )
    assert time.monotonic() - start < 7
    assert "private callback detail" not in str(error.value)


def test_terminal_worker_wins_before_queued_qt_delivery(qapp, tmp_path):
    adapter, done, _, req = setup(
        qapp, tmp_path, "import pathlib;pathlib.Path('result.mp4').write_bytes(b'ok')"
    )
    adapter.start(req)
    thread = adapter._process._thread
    deadline = time.monotonic() + 5
    while not thread.isFinished() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert thread.isFinished() and not done
    assert adapter.request_cancel() is False
    wait(qapp, lambda: bool(done))
    assert len(done) == 1 and done[0][0] is True


def test_cancel_wins_before_worker_terminal_lock(qapp, tmp_path, monkeypatch):
    import subprocess
    import threading
    import video_chronicle.legacy_cli as module

    entered = threading.Event()
    release = threading.Event()

    def task(command, **kwargs):
        entered.set()
        assert release.wait(5)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(module, "run_managed_command", task)
    adapter, done, _, req = setup(qapp, tmp_path, "pass")
    req.output.write_bytes(b"old")
    adapter.start(req)
    assert entered.wait(5)
    assert adapter.request_cancel()
    req.output.write_bytes(b"new")
    release.set()
    wait(qapp, lambda: bool(done))
    assert len(done) == 1 and done[0][0] is False
    assert "ProcessCancelled" in done[0][1]


def test_command_is_snapshotted_before_thread_admission(qapp, tmp_path, monkeypatch):
    import subprocess
    import threading
    import video_chronicle.legacy_cli as module

    entered = threading.Event()
    release = threading.Event()
    observed = []

    def task(command, **kwargs):
        entered.set()
        assert release.wait(5)
        observed.extend(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(module, "run_managed_command", task)
    port = module.ManagedLegacyCli(qapp)
    done = []
    port.finished.connect(lambda result, error: done.append((result, error)))
    command = ["trusted-python", "original-script"]
    port.start(command, tmp_path)
    assert entered.wait(5)
    command[:] = ["other-program", "mutated-script"]
    release.set()
    wait(qapp, lambda: bool(done))
    assert observed == ["trusted-python", "original-script"]
    assert done[0][1] is None
    # Match production parent ownership and drain the explicit teardown.
    from PySide6.QtCore import QCoreApplication, QEvent
    port.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_legacy_noninteractive_stdin_is_eof(qapp, tmp_path):
    body = "import sys,pathlib; assert sys.stdin.read() == ''; pathlib.Path('result.mp4').write_bytes(b'ok')"
    adapter, done, _, req = setup(qapp, tmp_path, body, timeout=1.5)
    adapter.start(req)
    wait(qapp, lambda: bool(done))
    assert len(done) == 1 and done[0][0] is True
    assert req.output.read_bytes() == b"ok"
