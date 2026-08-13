#!/usr/bin/env python3
"""PySide6 desktop wrapper for the legacy ``join_media.py`` pipeline."""

from __future__ import annotations

import codecs
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
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from gui_contract import (
    GuiRunRequest,
    RequestValidationError,
    build_cli_arguments,
    create_run_request,
)


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
    """One-window baseline UI for configuring and observing an export."""

    def __init__(self, adapter: CliProcessAdapter | None = None) -> None:
        super().__init__()
        self.setWindowTitle("Video Chronicle")
        self.setMinimumSize(820, 660)
        self.resize(940, 760)

        self._adapter = adapter or CliProcessAdapter(self)
        self._adapter.started.connect(self._on_started)
        self._adapter.output_received.connect(self._append_output)
        self._adapter.completed.connect(self._on_completed)
        self._active_request: GuiRunRequest | None = None

        default_input = Path.home() / "Input"
        self._suggested_output = default_input / "output.mp4"
        self._build_ui(default_input)

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
            "Выберите папку с фото и видео. Существующий медиаконвейер "
            "выполнит обработку в отдельном процессе."
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
        self.status_label = QLabel("Готово к настройке")
        self.status_label.setObjectName("status")
        self.run_button = QPushButton("Собрать хронологию")
        self.run_button.setObjectName("primary")
        self.run_button.setMinimumHeight(42)
        self.run_button.clicked.connect(self._start_export)
        action_row.addWidget(self.status_label, 1)
        action_row.addWidget(self.run_button)
        root.addLayout(action_row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        root.addWidget(self.progress)

        log_header = QHBoxLayout()
        log_title = QLabel("Журнал выполнения")
        log_title.setObjectName("sectionTitle")
        self.result_label = QLabel("")
        self.result_label.setObjectName("result")
        self.result_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        log_header.addWidget(log_title)
        log_header.addStretch(1)
        log_header.addWidget(self.result_label)
        root.addLayout(log_header)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setPlaceholderText("Здесь появятся сообщения join_media.py")
        self.log_view.document().setMaximumBlockCount(5_000)
        self.log_view.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        root.addWidget(self.log_view, 1)
        self.setCentralWidget(central)

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

    @Slot()
    def _start_export(self) -> None:
        try:
            request = create_run_request(
                input_dir_text=self.input_edit.text(),
                output_text=self.output_edit.text(),
                ffmpeg_text=self.ffmpeg_edit.text(),
                ffprobe_text=self.ffprobe_edit.text(),
                crf=self.crf_spin.value(),
                preset_text=self.preset_combo.currentText(),
            )
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
        self.run_button.setEnabled(not running)
        if running:
            self.status_label.setText("Запуск медиаконвейера…")
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
QFrame#card, QGroupBox {
    background: #ffffff;
    color: #233b3f;
    border: 1px solid #d9e4e5;
    border-radius: 10px;
}
QGroupBox { margin-top: 12px; padding: 14px 12px 10px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; }
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit {
    background: #ffffff;
    color: #182528;
    border: 1px solid #cbd9da;
    border-radius: 6px;
    padding: 7px 9px;
    selection-background-color: #2f918d;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QPlainTextEdit:focus {
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
QComboBox QAbstractItemView { background: #ffffff; color: #182528; selection-background-color: #2f918d; }
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
    window = ChronicleWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
