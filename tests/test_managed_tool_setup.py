"""Managed provisioning consumer tests; never install or contact WinGet."""

import sys
import time

import pytest
from PySide6.QtCore import QProcess

import video_chronicle_gui as gui
from video_chronicle import tool_setup
from video_chronicle.tool_setup import ManagedToolSetupProcess


def wait(qapp, predicate, timeout=8):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    assert predicate(), "managed setup did not reach its expected terminal state"


@pytest.mark.parametrize("mode", ["application", "legacy-cli"])
def test_production_composition_always_selects_managed_setup(qapp, monkeypatch, mode):
    monkeypatch.setenv("VIDEO_CHRONICLE_GUI_ADAPTER", mode)
    window = gui.build_main_window()
    assert window._tool_setup_factory is ManagedToolSetupProcess
    window.close()


@pytest.mark.parametrize(
    "timeout,budget", [(0, 1), (float("inf"), 1), (1, 0), (1, True)]
)
def test_setup_rejects_unbounded_profiles(timeout, budget):
    with pytest.raises(ValueError):
        ManagedToolSetupProcess(timeout=timeout, max_output_bytes=budget)


@pytest.mark.parametrize(
    "code,timeout,budget,error",
    [
        ("print('done')", 2, 100, None),
        ("import time; time.sleep(60)", 0.15, 100, "ProcessTimedOut"),
        ("print('x'*100000)", 2, 32, "ProcessOutputLimitExceeded"),
    ],
)
def test_real_managed_child_one_completion_after_worker_cleanup(
    qapp, code, timeout, budget, error
):
    process = ManagedToolSetupProcess(timeout=timeout, max_output_bytes=budget)
    process.setProgram(sys.executable)
    process.setArguments(["-c", code])
    completions = []
    process.finished.connect(lambda value, status: completions.append((value, status)))
    started = time.monotonic()
    process.start()
    assert time.monotonic() - started < 0.5  # GUI start itself remains nonblocking.
    wait(qapp, lambda: bool(completions))
    assert process._thread is None
    assert process.state() == QProcess.ProcessState.NotRunning
    assert process.last_error == error
    assert (
        completions == [(0, QProcess.ExitStatus.NormalExit)]
        if error is None
        else completions == [(1, QProcess.ExitStatus.CrashExit)]
    )
    for _ in range(5):
        qapp.processEvents()
    assert len(completions) == 1
    process.deleteLater()


def test_real_spawn_failure_reaches_one_completion(qapp, tmp_path):
    process = ManagedToolSetupProcess(timeout=1)
    process.setProgram(str(tmp_path / "nonexistent-tool.exe"))
    completed = []
    process.finished.connect(lambda *args: completed.append(args))
    process.start()
    wait(qapp, lambda: bool(completed))
    assert completed == [(1, QProcess.ExitStatus.CrashExit)]
    assert process.last_error == "FileNotFoundError"
    assert process._thread is None
    process.deleteLater()


def test_real_cancel_confirms_child_and_worker_cleanup(qapp):
    process = ManagedToolSetupProcess(timeout=5)
    process.setProgram(sys.executable)
    process.setArguments(["-c", "import time; time.sleep(60)"])
    completed = []
    process.finished.connect(lambda *args: completed.append(args))
    process.start()
    process.request_cancel()
    wait(qapp, lambda: bool(completed))
    assert completed == [(1, QProcess.ExitStatus.CrashExit)]
    assert process.last_error == "ProcessCancelled"
    assert process._thread is None
    process.deleteLater()


def prepare_missing_tools(monkeypatch):
    monkeypatch.setattr(gui, "resolve_encoding_tools", lambda: (None, None))
    monkeypatch.setattr(gui, "resolve_winget", lambda: "trusted-winget.exe")
    monkeypatch.setattr(gui.sys, "platform", "win32")


@pytest.mark.parametrize("failure", ["factory", "start"])
def test_factory_or_start_failure_restores_manual_ui_without_raw_fallback(
    qapp, monkeypatch, failure
):
    prepare_missing_tools(monkeypatch)
    raw_calls = []
    monkeypatch.setattr(QProcess, "start", lambda self: raw_calls.append(True))

    def factory(parent):
        if failure == "factory":
            raise RuntimeError("factory failed")
        process = ManagedToolSetupProcess(parent)
        process.start = lambda: (_ for _ in ()).throw(RuntimeError("start failed"))
        return process

    window = gui.ChronicleWindow(tool_setup_factory=factory)
    window.ensure_encoding_tools()
    assert window._tool_setup_process is None
    assert window.analyze_button.isEnabled()
    assert "Дополнительно" in window.status_label.text()
    assert raw_calls == []
    window.close()


@pytest.mark.parametrize(
    "error",
    ["ProcessTimedOut", "ProcessOutputLimitExceeded", "ProcessTreeTerminationError"],
)
def test_gui_managed_failure_retains_pinned_argv_and_restores_fallback(
    qapp, monkeypatch, error
):
    prepare_missing_tools(monkeypatch)
    calls = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        from video_chronicle import process_control

        raise getattr(process_control, error)("bounded managed failure")

    monkeypatch.setattr(tool_setup, "run_managed_command", runner)
    window = gui.build_main_window()
    window.ensure_encoding_tools()
    wait(qapp, lambda: window._tool_setup_process is None)
    assert len(calls) == 1
    command, profile = calls[0]
    assert command == ["trusted-winget.exe", *gui.winget_ffmpeg_install_arguments()]
    assert profile["timeout"] == 1800
    assert profile["max_output_bytes"] == 1024 * 1024
    assert profile["cancellation"] is not None
    assert window.analyze_button.isEnabled()
    assert "Дополнительно" in window.status_label.text()
    window.close()


def test_terminal_delivery_uses_qt_finished_even_if_wait_would_fail(qapp, monkeypatch):
    # A native join failure used to permanently block the UI after a completed
    # worker. Qt finished is the lifecycle authority after managed tree reap.
    monkeypatch.setattr(tool_setup._SetupThread, "wait", lambda self, *args: False)
    process = ManagedToolSetupProcess(timeout=2)
    process.setProgram(sys.executable)
    process.setArguments(["-c", "pass"])
    terminal = []
    process.finished.connect(lambda *args: terminal.append(args))
    process.start()
    wait(qapp, lambda: bool(terminal))
    assert terminal == [(0, QProcess.ExitStatus.NormalExit)]
    assert process._thread is None
    assert process.state() == QProcess.ProcessState.NotRunning
    qapp.processEvents()
    assert len(terminal) == 1
    process.deleteLater()
