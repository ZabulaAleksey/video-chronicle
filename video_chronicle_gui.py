#!/usr/bin/env python3
"""PySide6 desktop wrapper for the legacy ``join_media.py`` pipeline."""

from __future__ import annotations

import codecs
import os
import sys
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, Qt, Signal, Slot
from PySide6.QtGui import QCloseEvent, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gui_contract import (
    GuiRunRequest,
    RequestValidationError,
    build_cli_arguments,
    create_run_request,
)
from video_chronicle.domain import ExportPlan
from video_chronicle.gui_services import ApplicationServiceAdapter


PROJECT_DIR = Path(__file__).resolve().parent
CLI_SCRIPT = PROJECT_DIR / "join_media.py"
MAX_LOG_CHARACTERS = 500_000


def default_tool_value(tool_name: str) -> str:
    """Use the platform PATH until the user explicitly selects another tool."""

    return tool_name


def file_identity(path: Path) -> tuple[int, int, int, int] | None:
    """Return enough stat data to distinguish a newly published result."""

    try:
        stat = path.stat()
    except OSError:
        return None
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)


class CliProcessAdapter(QObject):
    """Asynchronous, list-argv boundary around the unchanged legacy CLI."""

    started = Signal()
    output_received = Signal(str)
    completed = Signal(bool, str)

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        cli_script: Path = CLI_SCRIPT,
        python_executable: str = sys.executable,
    ) -> None:
        super().__init__(parent)
        self._cli_script = cli_script
        self._python_executable = python_executable
        self._expected_output: Path | None = None
        self._output_before: tuple[int, int, int, int] | None = None
        self._active = False
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")

        self._process = QProcess(self)
        self._process.setWorkingDirectory(str(self._cli_script.parent))
        self._process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        environment = QProcessEnvironment.systemEnvironment()
        environment.insert("PYTHONIOENCODING", "utf-8")
        environment.insert("PYTHONUTF8", "1")
        self._process.setProcessEnvironment(environment)
        self._process.started.connect(self.started)
        self._process.readyReadStandardOutput.connect(self._forward_output)
        self._process.errorOccurred.connect(self._on_process_error)
        self._process.finished.connect(self._on_finished)

    @property
    def is_running(self) -> bool:
        return self._active

    def start(self, request: GuiRunRequest) -> None:
        if self._active:
            raise RuntimeError("Экспорт уже выполняется.")
        if not self._cli_script.is_file():
            raise RuntimeError(f"CLI-модуль не найден: {self._cli_script}")

        self._expected_output = request.output
        self._output_before = file_identity(request.output)
        self._active = True
        self._decoder.reset()
        arguments = build_cli_arguments(request, self._cli_script)
        self._process.start(self._python_executable, arguments)

    @Slot()
    def _forward_output(self) -> None:
        self._read_output()

    def _read_output(self, *, final: bool = False) -> None:
        data = bytes(self._process.readAllStandardOutput())
        text = self._decoder.decode(data, final=final)
        if text:
            self.output_received.emit(text)

    @Slot(QProcess.ProcessError)
    def _on_process_error(self, error: QProcess.ProcessError) -> None:
        message = f"Не удалось выполнить процесс: {self._process.errorString()}"
        self.output_received.emit(f"\n{message}\n")
        if error == QProcess.ProcessError.FailedToStart and self._active:
            self._active = False
            self.completed.emit(False, message)

    @Slot(int, QProcess.ExitStatus)
    def _on_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        self._read_output(final=True)
        if not self._active:
            return

        self._active = False
        normal_exit = exit_status == QProcess.ExitStatus.NormalExit
        output_after = (
            file_identity(self._expected_output)
            if self._expected_output is not None
            else None
        )
        output_published = output_after is not None and output_after != self._output_before
        if normal_exit and exit_code == 0 and output_published:
            self.completed.emit(True, f"Готово: {self._expected_output}")
            return

        if normal_exit and exit_code == 0:
            message = "CLI завершился без ошибки, но новый итоговый файл не подтверждён."
        elif normal_exit:
            message = f"Экспорт завершился с кодом {exit_code}."
        else:
            message = "Процесс аварийно завершился."
        self.completed.emit(False, message)


class ChronicleWindow(QMainWindow):
    """One-window preview and export UI over canonical application services.

    Passing ``adapter`` explicitly selects the temporary whole-CLI fallback.
    Production uses :class:`ApplicationServiceAdapter` by default.
    """

    def __init__(
        self,
        adapter: CliProcessAdapter | None = None,
        *,
        application_adapter: ApplicationServiceAdapter | None = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("Video Chronicle")
        self.setMinimumSize(820, 660)
        self.resize(1060, 860)

        self._legacy_mode = adapter is not None
        self._adapter: CliProcessAdapter | ApplicationServiceAdapter
        if adapter is not None:
            self._adapter = adapter
            adapter.started.connect(self._on_started)
            adapter.output_received.connect(self._append_output)
            adapter.completed.connect(self._on_completed)
        else:
            app_adapter = application_adapter or ApplicationServiceAdapter(self)
            self._adapter = app_adapter
            app_adapter.started.connect(self._on_application_started)
            app_adapter.output_received.connect(self._append_output)
            app_adapter.plan_ready.connect(self._on_plan_ready)
            app_adapter.completed.connect(self._on_application_completed)
        self._active_request: GuiRunRequest | None = None
        self._plan: ExportPlan | None = None
        self._building_ui = True

        default_input = Path.home() / "Input"
        self._suggested_output = default_input / "output.mp4"
        self._build_ui(default_input)
        self._building_ui = False
        self._connect_invalidation_signals()
        if self._legacy_mode:
            self.analyze_button.hide()
            self.run_button.setEnabled(True)
            self.preview_state_label.setText(
                "Диагностический режим: preview отключён, запускается legacy CLI."
            )
        else:
            self.run_button.setEnabled(False)

    def _build_ui(self, default_input: Path) -> None:
        central = QWidget(self)
        central.setObjectName("central")
        root = QVBoxLayout(central)
        root.setContentsMargins(30, 26, 30, 26)
        root.setSpacing(18)

        eyebrow = QLabel("ЛОКАЛЬНАЯ СБОРКА ХРОНИКИ")
        eyebrow.setObjectName("eyebrow")
        title = QLabel("Video Chronicle")
        title.setObjectName("title")
        subtitle = QLabel(
            "Выберите папку с фото и видео, проверьте состав и порядок, "
            "затем запустите экспорт. Анализ и медиаконвейер работают вне UI thread."
        )
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        root.addWidget(eyebrow)
        root.addWidget(title)
        root.addWidget(subtitle)

        settings_card = QFrame()
        settings_card.setObjectName("card")
        card_layout = QVBoxLayout(settings_card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(14)

        paths = QFormLayout()
        paths.setHorizontalSpacing(18)
        paths.setVerticalSpacing(12)
        paths.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        self.input_edit = QLineEdit(str(default_input))
        self.input_edit.setAccessibleName("Папка с исходными медиафайлами")
        self.input_button = QPushButton("Выбрать…")
        self.input_button.clicked.connect(self._browse_input)
        paths.addRow("Исходники", self._path_row(self.input_edit, self.input_button))

        self.output_edit = QLineEdit(str(self._suggested_output))
        self.output_edit.setAccessibleName("Путь итогового MP4-файла")
        self.output_button = QPushButton("Выбрать…")
        self.output_button.clicked.connect(self._browse_output)
        paths.addRow("Результат", self._path_row(self.output_edit, self.output_button))
        card_layout.addLayout(paths)

        advanced = QGroupBox("Параметры кодирования")
        # The preview and log panes both request vertical stretch.  Preserve the
        # form's minimum layout height so those panes cannot collapse its rows.
        advanced.setMinimumHeight(190)
        advanced_layout = QGridLayout(advanced)
        advanced_layout.setHorizontalSpacing(12)
        advanced_layout.setVerticalSpacing(10)

        self.ffmpeg_edit = QLineEdit(default_tool_value("ffmpeg"))
        self.ffmpeg_button = QPushButton("Файл…")
        self.ffmpeg_button.clicked.connect(
            lambda: self._browse_tool(self.ffmpeg_edit, "FFmpeg")
        )
        advanced_layout.addWidget(QLabel("FFmpeg"), 0, 0)
        advanced_layout.addWidget(self.ffmpeg_edit, 0, 1)
        advanced_layout.addWidget(self.ffmpeg_button, 0, 2)

        self.ffprobe_edit = QLineEdit(default_tool_value("ffprobe"))
        self.ffprobe_button = QPushButton("Файл…")
        self.ffprobe_button.clicked.connect(
            lambda: self._browse_tool(self.ffprobe_edit, "FFprobe")
        )
        advanced_layout.addWidget(QLabel("FFprobe"), 1, 0)
        advanced_layout.addWidget(self.ffprobe_edit, 1, 1)
        advanced_layout.addWidget(self.ffprobe_button, 1, 2)

        self.crf_spin = QSpinBox()
        self.crf_spin.setRange(0, 51)
        self.crf_spin.setValue(20)
        self.crf_spin.setToolTip("Меньше — выше качество и больше размер файла")
        self.preset_combo = QComboBox()
        self.preset_combo.setEditable(True)
        self.preset_combo.addItems(
            [
                "ultrafast",
                "superfast",
                "veryfast",
                "faster",
                "fast",
                "medium",
                "slow",
                "slower",
                "veryslow",
            ]
        )
        self.preset_combo.setCurrentText("medium")
        advanced_layout.addWidget(QLabel("CRF"), 2, 0)
        advanced_layout.addWidget(self.crf_spin, 2, 1)
        advanced_layout.addWidget(QLabel("Preset"), 3, 0)
        advanced_layout.addWidget(self.preset_combo, 3, 1)
        advanced_layout.setColumnStretch(1, 1)
        tool_warning = QLabel(
            "FFmpeg и FFprobe запускаются с вашими правами. Выбирайте только доверенные сборки."
        )
        tool_warning.setObjectName("hint")
        tool_warning.setWordWrap(True)
        advanced_layout.addWidget(tool_warning, 4, 0, 1, 3)
        card_layout.addWidget(advanced)
        root.addWidget(settings_card)

        action_row = QHBoxLayout()
        self.status_label = QLabel("Настройте параметры и запустите анализ")
        self.status_label.setObjectName("status")
        self.analyze_button = QPushButton("Анализировать")
        self.analyze_button.setMinimumHeight(42)
        self.analyze_button.clicked.connect(self._start_analysis)
        self.run_button = QPushButton("Экспортировать")
        self.run_button.setObjectName("primary")
        self.run_button.setMinimumHeight(42)
        self.run_button.clicked.connect(self._start_export)
        action_row.addWidget(self.status_label, 1)
        action_row.addWidget(self.analyze_button)
        action_row.addWidget(self.run_button)
        root.addLayout(action_row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        root.addWidget(self.progress)

        workspace = QSplitter(Qt.Orientation.Horizontal)
        workspace.setChildrenCollapsible(False)

        preview_panel = QFrame()
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(0, 0, 8, 0)
        preview_layout.setSpacing(10)
        preview_header = QHBoxLayout()
        preview_title = QLabel("План хронологии")
        preview_title.setObjectName("sectionTitle")
        self.preview_state_label = QLabel("План ещё не построен")
        self.preview_state_label.setObjectName("previewState")
        self.preview_state_label.setAccessibleName("Состояние анализа")
        preview_header.addWidget(preview_title)
        preview_header.addStretch(1)
        preview_header.addWidget(self.preview_state_label)
        preview_layout.addLayout(preview_header)

        self.plan_summary_label = QLabel(
            "Изменение любого параметра потребует повторного анализа."
        )
        self.plan_summary_label.setObjectName("summary")
        self.plan_summary_label.setWordWrap(True)
        self.plan_summary_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        preview_layout.addWidget(self.plan_summary_label)

        self.preview_tree = QTreeWidget()
        self.preview_tree.setObjectName("previewTree")
        self.preview_tree.setAccessibleName("Состав и порядок хронологии")
        self.preview_tree.setHeaderLabels(
            ["№", "Статус", "Файл", "Дата", "Источник", "Timezone", "Конфликт / причина"]
        )
        self.preview_tree.setRootIsDecorated(False)
        self.preview_tree.setAlternatingRowColors(True)
        self.preview_tree.setUniformRowHeights(True)
        self.preview_tree.setMinimumHeight(165)
        preview_layout.addWidget(self.preview_tree, 1)

        log_panel = QFrame()
        log_layout = QVBoxLayout(log_panel)
        log_layout.setContentsMargins(8, 0, 0, 0)
        log_layout.setSpacing(10)
        log_header = QHBoxLayout()
        log_title = QLabel("Журнал анализа и экспорта")
        log_title.setObjectName("sectionTitle")
        self.result_label = QLabel("")
        self.result_label.setObjectName("result")
        self.result_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        log_header.addWidget(log_title)
        log_header.addStretch(1)
        log_header.addWidget(self.result_label)
        log_layout.addLayout(log_header)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setPlaceholderText("Здесь появятся сообщения application services")
        self.log_view.document().setMaximumBlockCount(5_000)
        self.log_view.setMinimumHeight(110)
        self.log_view.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        log_layout.addWidget(self.log_view, 1)
        workspace.addWidget(preview_panel)
        workspace.addWidget(log_panel)
        workspace.setStretchFactor(0, 3)
        workspace.setStretchFactor(1, 2)
        workspace.setSizes([620, 400])
        root.addWidget(workspace, 1)

        scroll = QScrollArea(self)
        scroll.setObjectName("mainScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(central)
        self.setCentralWidget(scroll)

        self._editable_widgets = [
            self.input_edit,
            self.input_button,
            self.output_edit,
            self.output_button,
            self.ffmpeg_edit,
            self.ffmpeg_button,
            self.ffprobe_edit,
            self.ffprobe_button,
            self.crf_spin,
            self.preset_combo,
        ]

    def _connect_invalidation_signals(self) -> None:
        for edit in (
            self.input_edit,
            self.output_edit,
            self.ffmpeg_edit,
            self.ffprobe_edit,
        ):
            edit.textChanged.connect(self._invalidate_plan)
        self.crf_spin.valueChanged.connect(self._invalidate_plan)
        self.preset_combo.currentTextChanged.connect(self._invalidate_plan)

    @staticmethod
    def _path_row(line_edit: QLineEdit, button: QPushButton) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(line_edit, 1)
        layout.addWidget(button)
        return widget

    @Slot()
    def _browse_input(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self, "Выберите папку с медиа", self.input_edit.text()
        )
        if not selected:
            return
        current_output = Path(self.output_edit.text()).expanduser()
        self.input_edit.setText(selected)
        if current_output == self._suggested_output or not self.output_edit.text().strip():
            self._suggested_output = Path(selected) / "output.mp4"
            self.output_edit.setText(str(self._suggested_output))

    @Slot()
    def _browse_output(self) -> None:
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить хронологию",
            self.output_edit.text(),
            "MP4 video (*.mp4)",
        )
        if selected:
            output = Path(selected)
            if output.suffix.casefold() != ".mp4":
                output = output.with_suffix(".mp4")
            self.output_edit.setText(str(output))

    def _browse_tool(self, target: QLineEdit, label: str) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self, f"Выберите {label}", target.text(), "Executable (*.exe);;All files (*)"
        )
        if selected:
            target.setText(selected)

    def _form_request(self) -> GuiRunRequest:
        return create_run_request(
            input_dir_text=self.input_edit.text(),
            output_text=self.output_edit.text(),
            ffmpeg_text=self.ffmpeg_edit.text(),
            ffprobe_text=self.ffprobe_edit.text(),
            crf=self.crf_spin.value(),
            preset_text=self.preset_combo.currentText(),
        )

    @Slot()
    def _invalidate_plan(self, *_args: object) -> None:
        if self._building_ui or self._legacy_mode:
            return
        self._plan = None
        self._active_request = None
        self.preview_tree.clear()
        self.preview_state_label.setText("План устарел — повторите анализ")
        self.plan_summary_label.setText(
            "Параметры изменены. Экспорт недоступен до повторного анализа."
        )
        if not self._adapter.is_running:
            self.run_button.setEnabled(False)
            self.status_label.setText("Требуется повторный анализ")

    @Slot()
    def _start_analysis(self) -> None:
        if self._legacy_mode or self._adapter.is_running:
            return
        try:
            request = self._form_request()
        except RequestValidationError as exc:
            QMessageBox.warning(self, "Проверьте параметры", str(exc))
            self.status_label.setText("Нужна корректировка параметров")
            self.preview_state_label.setText("Ошибка параметров")
            return

        self._plan = None
        self._active_request = request
        self.preview_tree.clear()
        self.log_view.clear()
        self.result_label.clear()
        self.preview_state_label.setText("Анализ выполняется…")
        self.plan_summary_label.setText(f"Проверка: {request.input_dir}")
        self._set_running(True)
        try:
            assert isinstance(self._adapter, ApplicationServiceAdapter)
            self._adapter.start_analysis(request)
        except RuntimeError as exc:
            self._on_application_completed("analysis", False, str(exc))

    @Slot(str)
    def _on_application_started(self, operation: str) -> None:
        if operation == "analysis":
            self.status_label.setText("Анализ медиафайлов…")
        else:
            self.status_label.setText("Медиаконвейер выполняется…")

    @Slot(object)
    def _on_plan_ready(self, plan: object) -> None:
        active = self._active_request
        if not isinstance(plan, ExportPlan) or active is None:
            return
        if (
            plan.request.input_dir != active.input_dir
            or plan.request.output != active.output
            or plan.request.crf != active.crf
            or plan.request.preset != active.preset
        ):
            return
        self._plan = plan
        self._populate_preview(plan)

    def _populate_preview(self, plan: ExportPlan) -> None:
        self.preview_tree.clear()
        for index, item in enumerate(plan.items, start=1):
            selected = item.date_decision.selected if item.date_decision else None
            provenance = selected.source if selected else item.date_source
            timezone = selected.timezone if selected and selected.timezone else "—"
            conflicts = (
                str(len(item.date_decision.conflicts))
                if item.date_decision and item.date_decision.conflicts
                else "—"
            )
            row = QTreeWidgetItem(
                [
                    str(index),
                    "Принят",
                    str(item.path),
                    item.taken_at.strftime("%d.%m.%Y %H:%M:%S"),
                    provenance,
                    timezone,
                    conflicts,
                ]
            )
            row.setToolTip(2, str(item.path))
            if selected is not None:
                row.setToolTip(
                    4,
                    f"raw={selected.raw_value}; location={selected.location}",
                )
            self.preview_tree.addTopLevelItem(row)
        for path, reason in plan.inspection_failures:
            row = QTreeWidgetItem(
                ["—", "Пропущен", str(path), "—", "—", "—", reason]
            )
            row.setToolTip(2, str(path))
            row.setToolTip(6, reason)
            self.preview_tree.addTopLevelItem(row)

        self.preview_tree.resizeColumnToContents(0)
        self.preview_tree.resizeColumnToContents(1)
        self.preview_tree.resizeColumnToContents(3)
        self.preview_tree.resizeColumnToContents(4)
        self.preview_tree.resizeColumnToContents(5)
        request = plan.request
        self.preview_state_label.setText("План готов")
        self.plan_summary_label.setText(
            f"Вход: {request.input_dir} | Выход: {request.output} | "
            f"принято: {len(plan.items)}, пропущено: {len(plan.inspection_failures)} | "
            f"CRF {request.crf}, preset {request.preset} | "
            "overwrite: только после отдельного подтверждения"
        )

    @Slot(str, bool, str)
    def _on_application_completed(
        self, operation: str, success: bool, message: str
    ) -> None:
        self._set_running(False)
        self.result_label.setText(message)
        self._append_output(f"\n{message}\n")
        if operation == "analysis":
            if success and self._plan is not None:
                self.status_label.setText("План готов к экспорту")
                self.run_button.setEnabled(True)
                self.progress.setValue(1)
                return
            self._plan = None
            self.run_button.setEnabled(False)
            self.progress.setValue(0)
            if "no supported videos or photos found" in message:
                self.preview_state_label.setText("Поддерживаемые медиафайлы не найдены")
                self.plan_summary_label.setText(
                    "Папка пуста или не содержит поддерживаемых фото и видео."
                )
                self.status_label.setText("Анализ завершён: пустой набор")
            else:
                self.preview_state_label.setText("Ошибка анализа")
                self.plan_summary_label.setText(message)
                self.status_label.setText("Анализ не выполнен")
            return

        self.status_label.setText("Экспорт завершён" if success else "Экспорт не выполнен")
        self.progress.setValue(1 if success else 0)
        self.run_button.setEnabled(self._plan is not None)

    @Slot()
    def _start_export(self) -> None:
        if not self._legacy_mode:
            self._start_application_export()
            return
        try:
            request = self._form_request()
        except RequestValidationError as exc:
            QMessageBox.warning(self, "Проверьте параметры", str(exc))
            self.status_label.setText("Нужна корректировка параметров")
            return

        if request.output.exists():
            answer = QMessageBox.question(
                self,
                "Заменить существующий файл?",
                f"Файл уже существует:\n{request.output}\n\nЗаменить его после успешной обработки?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                self.status_label.setText("Запуск отменён — существующий файл сохранён")
                return
            request = replace(request, overwrite=True)

        self.log_view.clear()
        self.result_label.clear()
        self._active_request = request
        self._set_running(True)
        self._append_output("Запуск join_media.py…\n")
        try:
            self._adapter.start(request)
        except RuntimeError as exc:
            self._on_completed(False, str(exc))

    def _start_application_export(self) -> None:
        if self._adapter.is_running or self._plan is None:
            return
        overwrite = False
        output = self._plan.request.output
        if output.exists():
            answer = QMessageBox.question(
                self,
                "Заменить существующий файл?",
                f"Файл уже существует:\n{output}\n\nЗаменить его после успешной обработки?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                self.status_label.setText(
                    "Экспорт отменён — существующий файл сохранён"
                )
                return
            overwrite = True

        self.log_view.clear()
        self.result_label.clear()
        self._set_running(True)
        self._append_output("Запуск previewed export plan…\n")
        try:
            assert isinstance(self._adapter, ApplicationServiceAdapter)
            self._adapter.start_export(self._plan, overwrite=overwrite)
        except RuntimeError as exc:
            self._on_application_completed("export", False, str(exc))

    @Slot()
    def _on_started(self) -> None:
        self.status_label.setText("Медиаконвейер выполняется…")

    @Slot(str)
    def _append_output(self, text: str) -> None:
        cursor = self.log_view.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text)
        excess = self.log_view.document().characterCount() - MAX_LOG_CHARACTERS
        if excess > 0:
            trim_cursor = QTextCursor(self.log_view.document())
            trim_cursor.setPosition(0)
            trim_cursor.setPosition(excess, QTextCursor.MoveMode.KeepAnchor)
            trim_cursor.removeSelectedText()
            cursor = QTextCursor(self.log_view.document())
            cursor.movePosition(QTextCursor.MoveOperation.End)
        self.log_view.setTextCursor(cursor)
        self.log_view.ensureCursorVisible()

    @Slot(bool, str)
    def _on_completed(self, success: bool, message: str) -> None:
        self._set_running(False)
        self.status_label.setText("Экспорт завершён" if success else "Экспорт не выполнен")
        self.result_label.setText(message)
        self.progress.setRange(0, 1)
        self.progress.setValue(1 if success else 0)
        self._append_output(f"\n{message}\n")

    def _set_running(self, running: bool) -> None:
        for widget in self._editable_widgets:
            widget.setEnabled(not running)
        self.analyze_button.setEnabled(not running)
        if self._legacy_mode:
            self.run_button.setEnabled(not running)
        else:
            self.run_button.setEnabled(not running and self._plan is not None)
        if running:
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, 1)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt API
        if self._adapter.is_running:
            QMessageBox.warning(
                self,
                "Экспорт ещё выполняется",
                "Дождитесь завершения экспорта. Безопасная отмена будет добавлена отдельно.",
            )
            event.ignore()
            return
        event.accept()


STYLE_SHEET = """
QWidget#central { background: #f4f7f8; color: #182528; }
QLabel { color: #233b3f; }
QLabel#eyebrow { color: #0d7d79; font-size: 11px; font-weight: 700; letter-spacing: 1px; }
QLabel#title { color: #102a2e; font-size: 30px; font-weight: 700; }
QLabel#subtitle { color: #52666a; font-size: 14px; }
QLabel#sectionTitle { color: #233b3f; font-size: 14px; font-weight: 700; }
QLabel#status { color: #40575b; font-weight: 600; }
QLabel#result { color: #0d716d; }
QLabel#hint { color: #6f5a2e; font-size: 12px; }
QLabel#previewState { color: #0d716d; font-weight: 600; }
QLabel#summary { color: #52666a; font-size: 12px; }
QFrame#card, QGroupBox {
    background: #ffffff;
    color: #233b3f;
    border: 1px solid #d9e4e5;
    border-radius: 10px;
}
QGroupBox { margin-top: 12px; padding: 14px 12px 10px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; }
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTreeWidget {
    background: #ffffff;
    color: #182528;
    border: 1px solid #cbd9da;
    border-radius: 6px;
    padding: 7px 9px;
    selection-background-color: #2f918d;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QPlainTextEdit:focus, QTreeWidget:focus {
    border: 1px solid #278b87;
}
QPushButton {
    background: #e7efef;
    color: #233b3f;
    border: 1px solid #cbd9da;
    border-radius: 7px;
    padding: 8px 14px;
    font-weight: 600;
}
QPushButton:hover { background: #dce9e9; }
QPushButton:disabled { color: #8d9b9d; background: #edf1f1; }
QPushButton#primary { background: #176f6b; border-color: #176f6b; color: white; padding: 9px 20px; }
QPushButton#primary:hover { background: #0f5f5b; }
QPushButton#primary:disabled { color: #8d9b9d; background: #edf1f1; border-color: #d2dddd; }
QComboBox QAbstractItemView { background: #ffffff; color: #182528; selection-background-color: #2f918d; }
QTreeWidget { alternate-background-color: #f5f9f9; }
QHeaderView::section { background: #e7efef; color: #233b3f; padding: 6px; border: 0; border-right: 1px solid #d3dfdf; }
QProgressBar { border: 0; background: #dfe9e9; border-radius: 3px; height: 6px; }
QProgressBar::chunk { background: #2b918c; border-radius: 3px; }
QPlainTextEdit { font-family: Consolas, "Cascadia Mono", monospace; font-size: 12px; }
"""


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Video Chronicle")
    app.setOrganizationName("Video Chronicle")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE_SHEET)
    mode = os.environ.get("VIDEO_CHRONICLE_GUI_ADAPTER", "application").casefold()
    legacy_adapter = CliProcessAdapter() if mode == "legacy-cli" else None
    window = ChronicleWindow(adapter=legacy_adapter)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
