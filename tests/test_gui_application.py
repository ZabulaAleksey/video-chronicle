from __future__ import annotations

import threading
import time
import base64
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMessageBox
from PySide6.QtWidgets import QScrollArea

from gui_contract import GuiRunRequest, build_cli_arguments
from video_chronicle.domain import (
    DateCandidate,
    DateDecision,
    ExportPlan,
    ExportMode,
    ExportRequest,
    MediaItem,
)
from video_chronicle.gui_services import ApplicationServiceAdapter
from video_chronicle.overlay import OverlayConfig
from video_chronicle_gui import ChronicleWindow, CliProcessAdapter


_PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _fake_preview(item, overlay, ffmpeg, destination, runner) -> None:
    destination.write_bytes(_PNG_1X1)


def _preview_ports():
    return SimpleNamespace(
        command_runner=lambda *args: None,
        validate_source=lambda input_dir, source: None,
    )


def _wait_until(qapp, predicate, timeout_seconds: float = 5.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while not predicate() and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.005)
    assert predicate(), "Qt worker did not finish before timeout"


def _canonical_request(input_dir: Path, output: Path) -> ExportRequest:
    return ExportRequest(
        input_dir=input_dir.resolve(),
        output=output.resolve(),
        error_log=(output.parent / "errors.log").resolve(),
        ffmpeg="resolved-ffmpeg",
        ffprobe="resolved-ffprobe",
        crf=20,
        preset="medium",
        overwrite=False,
        keep_work=False,
        overlay=OverlayConfig(enabled=False),
    )


def _preview_plan(request: ExportRequest) -> ExportPlan:
    selected = DateCandidate(
        wall_time=datetime(2024, 5, 6, 7, 8, 9),
        raw_value="2024-05-06T07:08:09+03:00",
        origin="metadata",
        key="creation_time",
        raw_key="creation_time",
        location="format",
        timezone="+03:00",
        priority=0,
    )
    conflict = DateCandidate(
        wall_time=datetime(2024, 5, 7, 7, 8, 9),
        raw_value="20240507_070809",
        origin="filename",
        key=None,
        raw_key=None,
        location="filename",
        timezone=None,
        priority=8,
    )
    decision = DateDecision(
        selected=selected,
        all_valid=(selected, conflict),
        conflicts=(conflict,),
        policy_version="date-v1",
    )
    item = MediaItem(
        path=request.input_dir / "семейное видео 01.mp4",
        taken_at=selected.wall_time,
        is_photo=False,
        has_audio=True,
        date_source=selected.source,
        date_decision=decision,
    )
    return ExportPlan(
        request=request,
        items=(item,),
        inspection_failures=((request.input_dir / "повреждённое фото.jpg", "bad media"),),
    )


def _gui_request(input_dir: Path, output: Path) -> GuiRunRequest:
    return GuiRunRequest(
        input_dir=input_dir,
        output=output,
        ffmpeg="ffmpeg",
        ffprobe="ffprobe",
    )


def test_application_adapter_is_async_repeatable_and_cleans_worker(
    qapp, tmp_path: Path
) -> None:
    input_dir = tmp_path / "медиа folder"
    input_dir.mkdir()
    output = tmp_path / "готовый фильм.mp4"
    request = _canonical_request(input_dir, output)
    worker_threads: list[int] = []
    release = threading.Event()

    def plan_service(canonical, ports, logger):
        worker_threads.append(threading.get_ident())
        logger.info("анализ %s", canonical.input_dir)
        release.wait(timeout=2)
        return _preview_plan(canonical)

    adapter = ApplicationServiceAdapter(
        plan_service=plan_service,
        ports_factory=lambda: object(),  # type: ignore[arg-type]
        request_factory=lambda gui: request,
    )
    completed: list[tuple[str, bool, str]] = []
    adapter.completed.connect(lambda *args: completed.append(args))
    ticks: list[bool] = []

    adapter.start_analysis(_gui_request(input_dir, output))
    QTimer.singleShot(0, lambda: ticks.append(True))
    qapp.processEvents()

    assert adapter.is_running is True
    assert ticks == [True]
    release.set()
    _wait_until(qapp, lambda: len(completed) == 1)
    assert completed[0][0:2] == ("analysis", True)
    assert adapter.is_running is False
    assert worker_threads[0] != threading.get_ident()

    adapter.start_analysis(_gui_request(input_dir, output))
    _wait_until(qapp, lambda: len(completed) == 2)
    assert adapter.is_running is False


def test_rejected_second_export_does_not_corrupt_active_completion(
    qapp, tmp_path: Path
) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    first_output = tmp_path / "one.mp4"
    second_output = tmp_path / "two.mp4"
    release = threading.Event()

    def execute_service(plan, logger, ports):
        release.wait(timeout=2)
        plan.request.output.write_bytes(b"published")
        return 0

    adapter = ApplicationServiceAdapter(
        execute_service=execute_service,
        ports_factory=lambda: object(),  # type: ignore[arg-type]
    )
    completed: list[tuple[str, bool, str]] = []
    adapter.completed.connect(lambda *args: completed.append(args))
    first_plan = _preview_plan(_canonical_request(input_dir, first_output))
    second_plan = _preview_plan(_canonical_request(input_dir, second_output))

    adapter.start_export(first_plan, overwrite=False)
    try:
        adapter.start_export(second_plan, overwrite=False)
    except RuntimeError as exc:
        assert "уже выполняется" in str(exc)
    else:
        raise AssertionError("a concurrent export must be rejected")
    release.set()
    _wait_until(qapp, lambda: len(completed) == 1)

    assert completed[0][0:2] == ("export", True)
    assert first_output.read_bytes() == b"published"
    assert second_output.exists() is False


def test_window_renders_plan_and_invalidates_it_on_any_form_change(
    qapp, tmp_path: Path
) -> None:
    input_dir = tmp_path / "входные медиа"
    input_dir.mkdir()
    output = tmp_path / "итоговый фильм.mp4"
    canonical = _canonical_request(input_dir, output)
    adapter = ApplicationServiceAdapter(
        plan_service=lambda request, ports, logger: _preview_plan(request),
        ports_factory=lambda: object(),  # type: ignore[arg-type]
        request_factory=lambda gui: canonical,
    )
    window = ChronicleWindow(application_adapter=adapter)
    window.input_edit.setText(str(input_dir))
    window.output_edit.setText(str(output))

    window.analyze_button.click()
    assert window.input_edit.isEnabled() is False
    assert window.preview_state_label.text() == "Анализ выполняется…"
    _wait_until(qapp, lambda: not adapter.is_running)

    assert window.preview_state_label.text() == "План готов"
    assert window.preview_tree.topLevelItemCount() == 2
    accepted = window.preview_tree.topLevelItem(0)
    skipped = window.preview_tree.topLevelItem(1)
    assert accepted.text(0) == "1"
    assert accepted.text(2).endswith("семейное видео 01.mp4")
    assert accepted.text(4) == "metadata:creation_time"
    assert accepted.text(5) == "+03:00"
    assert accepted.text(6) == "1"
    assert skipped.text(1) == "Пропущен"
    assert skipped.text(6) == "bad media"
    assert "принято: 1, пропущено: 1" in window.plan_summary_label.text()
    assert window.run_button.isEnabled() is False
    assert window.preview_button.isEnabled() is True

    window.preset_combo.setCurrentText("slow")
    qapp.processEvents()
    assert window.preview_tree.topLevelItemCount() == 0
    assert window.preview_state_label.text() == "План устарел — повторите анализ"
    assert window.run_button.isEnabled() is False
    window.close()


def test_window_distinguishes_empty_and_error_analysis_states(
    qapp, tmp_path: Path
) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output = tmp_path / "output.mp4"
    canonical = _canonical_request(input_dir, output)

    for error, expected in (
        (
            RuntimeError(f"no supported videos or photos found in {input_dir}"),
            "Поддерживаемые медиафайлы не найдены",
        ),
        (RuntimeError("ffprobe failed"), "Ошибка анализа"),
    ):
        def failing_plan(request, ports, logger, failure=error):
            raise failure

        adapter = ApplicationServiceAdapter(
            plan_service=failing_plan,
            ports_factory=lambda: object(),  # type: ignore[arg-type]
            request_factory=lambda gui: canonical,
        )
        window = ChronicleWindow(application_adapter=adapter)
        window.input_edit.setText(str(input_dir))
        window.output_edit.setText(str(output))
        window.analyze_button.click()
        _wait_until(qapp, lambda: not adapter.is_running)
        assert window.preview_state_label.text() == expected
        assert window.run_button.isEnabled() is False
        window.close()


def test_overwrite_is_confirmed_only_immediately_before_application_export(
    qapp, tmp_path: Path, monkeypatch
) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output = tmp_path / "output.mp4"
    canonical = _canonical_request(input_dir, output)
    executed: list[bool] = []

    def execute_service(plan, logger, ports):
        executed.append(plan.request.overwrite)
        plan.request.output.write_bytes(b"new-result-with-different-size")
        return 0

    adapter = ApplicationServiceAdapter(
        plan_service=lambda request, ports, logger: _preview_plan(request),
        execute_service=execute_service,
        preview_service=_fake_preview,
        ports_factory=_preview_ports,  # type: ignore[arg-type]
        request_factory=lambda gui: canonical,
    )
    window = ChronicleWindow(application_adapter=adapter)
    window.input_edit.setText(str(input_dir))
    window.output_edit.setText(str(output))
    window.analyze_button.click()
    _wait_until(qapp, lambda: not adapter.is_running)
    assert output.exists() is False
    window.preview_button.click()
    _wait_until(qapp, lambda: not adapter.is_running)
    assert window.run_button.isEnabled() is True

    output.write_bytes(b"existing")
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.No,
    )
    window.run_button.click()
    qapp.processEvents()
    assert executed == []
    assert output.read_bytes() == b"existing"

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    window.run_button.click()
    _wait_until(qapp, lambda: not adapter.is_running)
    assert executed == [True]
    assert window.status_label.text() == "Экспорт завершён"
    window.close()


def test_window_blocks_close_during_application_worker(
    qapp, tmp_path: Path, monkeypatch
) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output = tmp_path / "output.mp4"
    canonical = _canonical_request(input_dir, output)
    release = threading.Event()

    def slow_plan(request, ports, logger):
        release.wait(timeout=2)
        return _preview_plan(request)

    adapter = ApplicationServiceAdapter(
        plan_service=slow_plan,
        ports_factory=lambda: object(),  # type: ignore[arg-type]
        request_factory=lambda gui: canonical,
    )
    window = ChronicleWindow(application_adapter=adapter)
    window.input_edit.setText(str(input_dir))
    window.output_edit.setText(str(output))
    window.analyze_button.click()
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)
    event = QCloseEvent()

    window.closeEvent(event)

    assert event.isAccepted() is False
    release.set()
    _wait_until(qapp, lambda: not adapter.is_running)
    window.close()


def test_minimum_window_keeps_full_form_accessible_via_scroll(qapp) -> None:
    window = ChronicleWindow()
    window.resize(820, 660)
    window.show()
    qapp.processEvents()

    scroll = window.findChild(QScrollArea, "mainScroll")
    assert scroll is not None
    assert scroll.verticalScrollBar().maximum() > 0
    assert window.crf_spin.isVisible() is True
    assert window.preset_combo.isVisible() is True
    scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
    qapp.processEvents()
    assert scroll.verticalScrollBar().value() > 0
    window.close()


def test_overlay_only_change_keeps_plan_and_preview_temp_is_cleaned(
    qapp, tmp_path: Path
) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output = tmp_path / "output.mp4"
    canonical = _canonical_request(input_dir, output)
    analysis_calls: list[bool] = []
    preview_paths: list[Path] = []
    preview_configs: list[OverlayConfig] = []

    def plan_service(request, ports, logger):
        analysis_calls.append(True)
        return _preview_plan(request)

    def preview_service(item, overlay, ffmpeg, destination, runner):
        assert overlay.enabled is False
        preview_configs.append(overlay)
        preview_paths.append(destination)
        destination.write_bytes(_PNG_1X1)

    adapter = ApplicationServiceAdapter(
        plan_service=plan_service,
        preview_service=preview_service,
        ports_factory=_preview_ports,  # type: ignore[arg-type]
        request_factory=lambda gui: canonical,
    )
    window = ChronicleWindow(application_adapter=adapter)
    window.input_edit.setText(str(input_dir))
    window.output_edit.setText(str(output))
    window.analyze_button.click()
    _wait_until(qapp, lambda: not adapter.is_running)
    original_items = window._plan.items

    window.overlay_enabled.setChecked(False)
    qapp.processEvents()
    assert analysis_calls == [True]
    assert window._plan.items is original_items
    assert window.run_button.isEnabled() is False
    assert window.visual_preview_state_label.text() == "Предпросмотр устарел"

    window.preview_button.click()
    _wait_until(qapp, lambda: not adapter.is_running)
    assert preview_paths and all(not path.exists() for path in preview_paths)
    assert window._plan.request.overlay is not canonical.overlay
    assert window._plan.request.overlay.enabled is False
    assert preview_configs == [window._plan.request.overlay]
    assert preview_configs[0] is window._plan.request.overlay
    assert window.visual_preview_state_label.text() == "Подпись выключена"
    assert window.run_button.isEnabled() is True
    window.close()


def test_preview_error_is_visible_and_export_stays_disabled(qapp, tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output = tmp_path / "output.mp4"
    canonical = _canonical_request(input_dir, output)

    def failing_preview(*args, **kwargs):
        raise RuntimeError("FFmpeg preview failed: synthetic diagnostic")

    adapter = ApplicationServiceAdapter(
        plan_service=lambda request, ports, logger: _preview_plan(request),
        preview_service=failing_preview,
        ports_factory=_preview_ports,  # type: ignore[arg-type]
        request_factory=lambda gui: canonical,
    )
    window = ChronicleWindow(application_adapter=adapter)
    window.input_edit.setText(str(input_dir))
    window.output_edit.setText(str(output))
    window.analyze_button.click()
    _wait_until(qapp, lambda: not adapter.is_running)
    window.overlay_enabled.setChecked(False)
    window.preview_button.click()
    _wait_until(qapp, lambda: not adapter.is_running)

    assert window.visual_preview_state_label.text() == "Ошибка предпросмотра"
    assert "synthetic diagnostic" in window.visual_preview_label.text()
    assert window.run_button.isEnabled() is False
    window.close()


def test_gui_mode_switch_invalidates_plan_and_join_skips_visual_preview(
    qapp, tmp_path: Path
) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output = tmp_path / "output.mp4"

    def request_factory(gui):
        return _canonical_request(input_dir, output).__class__(
            **{
                **_canonical_request(input_dir, output).__dict__,
                "mode": gui.mode,
                "overlay": gui.overlay,
            }
        )

    adapter = ApplicationServiceAdapter(
        plan_service=lambda request, ports, logger: _preview_plan(request),
        ports_factory=lambda: object(),  # type: ignore[arg-type]
        request_factory=request_factory,
    )
    window = ChronicleWindow(application_adapter=adapter)
    window.input_edit.setText(str(input_dir))
    window.output_edit.setText(str(output))
    assert window.mode_combo.currentData() == ExportMode.CHRONICLE.value
    assert "Chronicle" in window.mode_description_label.text()
    window.overlay_enabled.setChecked(False)

    window.mode_combo.setCurrentIndex(1)
    qapp.processEvents()
    assert window.mode_combo.currentData() == ExportMode.JOIN.value
    assert window.overlay_group.isEnabled() is False
    assert window.visual_preview_state_label.text() == "Отключён в режиме Join"
    assert window._plan is None

    window.analyze_button.click()
    _wait_until(qapp, lambda: not adapter.is_running)
    assert window._plan.request.mode is ExportMode.JOIN
    assert window._plan.request.overlay.enabled is False
    assert "Режим: join" in window.plan_summary_label.text()
    assert window.overlay_group.isEnabled() is False
    assert window.preview_button.isEnabled() is False
    assert window.run_button.isEnabled() is True

    window.mode_combo.setCurrentIndex(0)
    qapp.processEvents()
    assert window._plan is None
    assert window.run_button.isEnabled() is False
    assert window.overlay_enabled.isChecked() is False
    window.close()


def test_legacy_mode_round_trip_preserves_chronicle_default_and_cli_parity(
    qapp, tmp_path: Path
) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    adapter = CliProcessAdapter(cli_script=tmp_path / "join_media.py")
    window = ChronicleWindow(adapter=adapter)
    window.input_edit.setText(str(input_dir))
    window.output_edit.setText(str(tmp_path / "output.mp4"))

    assert window.overlay_enabled.isChecked() is True
    window.mode_combo.setCurrentIndex(1)
    window.mode_combo.setCurrentIndex(0)
    qapp.processEvents()

    request = window._form_request()
    arguments = build_cli_arguments(request, tmp_path / "join_media.py")
    assert request.mode is ExportMode.CHRONICLE
    assert request.overlay.enabled is True
    assert window.mode_combo.currentText() == "Chronicle"
    assert "--mode" not in arguments
    window.close()
