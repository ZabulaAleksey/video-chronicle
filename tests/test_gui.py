from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMessageBox

from gui_contract import GuiRunRequest, create_run_request
from video_chronicle_gui import ChronicleWindow, CliProcessAdapter


def _wait_until(qapp, predicate, timeout_seconds: float = 5.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while not predicate() and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    assert predicate(), "Qt signal was not received before the timeout"


def _helper_script(
    path: Path,
    *,
    exit_code: int = 0,
    create_output: bool = True,
    crash: bool = False,
) -> None:
    path.write_text(
        "\n".join(
            [
                "import argparse",
                "import os",
                "import pathlib",
                "import sys",
                "parser = argparse.ArgumentParser(add_help=False)",
                "parser.add_argument('--output')",
                "args, _ = parser.parse_known_args()",
                "print('диагностика из stderr', file=sys.stderr, flush=True)",
                f"crash = {crash!r}",
                "if crash:",
                "    os.abort()",
                f"create_output = {create_output!r}",
                "if create_output:",
                "    pathlib.Path(args.output).write_bytes(b'result')",
                f"raise SystemExit({exit_code})",
            ]
        ),
        encoding="utf-8",
    )


def test_process_adapter_forwards_stderr_and_verifies_output(qapp, tmp_path: Path) -> None:
    helper = tmp_path / "helper cli.py"
    _helper_script(helper)
    input_dir = tmp_path / "медиа folder"
    input_dir.mkdir()
    request = create_run_request(
        input_dir_text=str(input_dir),
        output_text=str(tmp_path / "готовый фильм.mp4"),
        ffmpeg_text="ffmpeg",
        ffprobe_text="ffprobe",
        crf=20,
        preset_text="medium",
    )
    adapter = CliProcessAdapter(cli_script=helper, python_executable=sys.executable)
    output: list[str] = []
    completed: list[tuple[bool, str]] = []
    adapter.output_received.connect(output.append)
    adapter.completed.connect(lambda success, message: completed.append((success, message)))

    adapter.start(request)
    _wait_until(qapp, lambda: bool(completed))

    assert completed[0][0] is True
    assert request.output.read_bytes() == b"result"
    assert "диагностика из stderr" in "".join(output)
    assert adapter.is_running is False


def test_process_adapter_treats_missing_output_as_failure(qapp, tmp_path: Path) -> None:
    helper = tmp_path / "helper.py"
    _helper_script(helper, create_output=False)
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    request = create_run_request(
        input_dir_text=str(input_dir),
        output_text=str(tmp_path / "missing.mp4"),
        ffmpeg_text="ffmpeg",
        ffprobe_text="ffprobe",
        crf=20,
        preset_text="medium",
    )
    adapter = CliProcessAdapter(cli_script=helper, python_executable=sys.executable)
    completed: list[tuple[bool, str]] = []
    adapter.completed.connect(lambda success, message: completed.append((success, message)))

    adapter.start(request)
    _wait_until(qapp, lambda: bool(completed))

    assert completed == [
        (False, "CLI завершился без ошибки, но новый итоговый файл не подтверждён.")
    ]


def test_process_adapter_rejects_unchanged_preexisting_output(
    qapp, tmp_path: Path
) -> None:
    helper = tmp_path / "helper.py"
    _helper_script(helper, create_output=False)
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_path = tmp_path / "existing.mp4"
    output_path.write_bytes(b"stale")
    request = create_run_request(
        input_dir_text=str(input_dir),
        output_text=str(output_path),
        ffmpeg_text="ffmpeg",
        ffprobe_text="ffprobe",
        crf=20,
        preset_text="medium",
        overwrite=True,
    )
    adapter = CliProcessAdapter(cli_script=helper, python_executable=sys.executable)
    completed: list[tuple[bool, str]] = []
    adapter.completed.connect(lambda success, message: completed.append((success, message)))

    adapter.start(request)
    _wait_until(qapp, lambda: bool(completed))

    assert completed[0][0] is False
    assert output_path.read_bytes() == b"stale"


def test_process_adapter_surfaces_legacy_cli_failure(qapp, tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    request = create_run_request(
        input_dir_text=str(input_dir),
        output_text=str(tmp_path / "output.mp4"),
        ffmpeg_text=str(tmp_path / "missing ffmpeg.exe"),
        ffprobe_text=str(tmp_path / "missing ffprobe.exe"),
        crf=20,
        preset_text="medium",
    )
    adapter = CliProcessAdapter()
    output: list[str] = []
    completed: list[tuple[bool, str]] = []
    adapter.output_received.connect(output.append)
    adapter.completed.connect(lambda success, message: completed.append((success, message)))

    adapter.start(request)
    _wait_until(qapp, lambda: bool(completed))

    assert completed[0][0] is False
    assert "FFmpeg not found" in "".join(output)
    assert request.output.exists() is False


def test_process_adapter_reports_failed_start_once(qapp, tmp_path: Path) -> None:
    helper = tmp_path / "helper.py"
    _helper_script(helper)
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    request = create_run_request(
        input_dir_text=str(input_dir),
        output_text=str(tmp_path / "output.mp4"),
        ffmpeg_text="ffmpeg",
        ffprobe_text="ffprobe",
        crf=20,
        preset_text="medium",
    )
    adapter = CliProcessAdapter(
        cli_script=helper,
        python_executable=str(tmp_path / "missing python.exe"),
    )
    completed: list[tuple[bool, str]] = []
    adapter.completed.connect(lambda success, message: completed.append((success, message)))

    adapter.start(request)
    _wait_until(qapp, lambda: bool(completed))
    qapp.processEvents()

    assert len(completed) == 1
    assert completed[0][0] is False
    assert adapter.is_running is False


def test_process_adapter_reports_crash_exit_once(qapp, tmp_path: Path) -> None:
    helper = tmp_path / "crash.py"
    _helper_script(helper, create_output=False, crash=True)
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    request = create_run_request(
        input_dir_text=str(input_dir),
        output_text=str(tmp_path / "output.mp4"),
        ffmpeg_text="ffmpeg",
        ffprobe_text="ffprobe",
        crf=20,
        preset_text="medium",
    )
    adapter = CliProcessAdapter(cli_script=helper, python_executable=sys.executable)
    completed: list[tuple[bool, str]] = []
    adapter.completed.connect(lambda success, message: completed.append((success, message)))

    adapter.start(request)
    _wait_until(qapp, lambda: bool(completed))
    qapp.processEvents()

    assert completed == [(False, "Процесс аварийно завершился.")]
    assert adapter.is_running is False


class FakeAdapter(QObject):
    started = Signal()
    output_received = Signal(str)
    completed = Signal(bool, str)

    def __init__(self) -> None:
        super().__init__()
        self.requests: list[GuiRunRequest] = []
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self, request: GuiRunRequest) -> None:
        self.requests.append(request)
        self._running = True
        self.started.emit()

    def finish(self, success: bool = True) -> None:
        self._running = False
        self.completed.emit(success, "Готово" if success else "Ошибка")


def test_window_disables_configuration_while_export_is_active(qapp, tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    adapter = FakeAdapter()
    window = ChronicleWindow(adapter=adapter)  # type: ignore[arg-type]
    window.input_edit.setText(str(input_dir))
    window.output_edit.setText(str(tmp_path / "output.mp4"))

    window.run_button.click()
    qapp.processEvents()

    assert len(adapter.requests) == 1
    assert window.run_button.isEnabled() is False
    assert window.input_edit.isEnabled() is False
    adapter.finish()
    qapp.processEvents()
    assert window.run_button.isEnabled() is True
    assert window.status_label.text() == "Экспорт завершён"
    window.close()


def test_window_requires_confirmation_before_overwrite(
    qapp, tmp_path: Path, monkeypatch
) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output = tmp_path / "output.mp4"
    output.write_bytes(b"existing")
    adapter = FakeAdapter()
    window = ChronicleWindow(adapter=adapter)  # type: ignore[arg-type]
    window.input_edit.setText(str(input_dir))
    window.output_edit.setText(str(output))
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.No,
    )

    window.run_button.click()
    qapp.processEvents()
    assert adapter.requests == []
    assert output.read_bytes() == b"existing"

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    window.run_button.click()
    qapp.processEvents()
    assert adapter.requests[0].overwrite is True
    adapter.finish()
    window.close()


def test_window_blocks_close_while_process_is_active(
    qapp, tmp_path: Path, monkeypatch
) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    adapter = FakeAdapter()
    window = ChronicleWindow(adapter=adapter)  # type: ignore[arg-type]
    window.input_edit.setText(str(input_dir))
    window.output_edit.setText(str(tmp_path / "output.mp4"))
    window.run_button.click()
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)
    event = QCloseEvent()

    window.closeEvent(event)

    assert event.isAccepted() is False
    adapter.finish()
    window.close()
