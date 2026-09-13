#!/usr/bin/env python3
"""PySide6 desktop wrapper for the legacy ``join_media.py`` pipeline."""

from __future__ import annotations

import codecs
import hashlib
import os
import sys
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import (
    QFileSystemWatcher,
    QObject,
    QProcess,
    QProcessEnvironment,
    QSize,
    Qt,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtGui import QCloseEvent, QColor, QIcon, QPainter, QPixmap, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTabWidget,
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
from video_chronicle.domain import ExportMode, ExportPlan
from video_chronicle.execution import ProgressEvent
from video_chronicle.gui_services import ApplicationServiceAdapter, ThumbnailBatch
from video_chronicle.gui_services import replace_plan_overlay
from video_chronicle.application import apply_project_state, reconcile_project_sources
from video_chronicle.project import (
    ProjectState,
    RenderPreset,
    RenderSettings,
    Timeline,
    TimelineItem,
    TimelineLayout,
    TrimRange,
)
from video_chronicle.repository import JsonProjectRepository
from video_chronicle.tooling import (
    FFMPEG_WINGET_VERSION,
    refresh_windows_process_path,
    resolve_encoding_tool,
    resolve_encoding_tools,
    resolve_winget,
    winget_ffmpeg_install_arguments,
)
from video_chronicle.overlay import (
    DATE_FORMATS,
    OVERLAY_POSITIONS,
    TIME_FORMATS,
    OverlayConfig,
    available_overlay_font_families,
    resolve_overlay_font,
)


PROJECT_DIR = Path(__file__).resolve().parent
CLI_SCRIPT = PROJECT_DIR / "join_media.py"
MAX_LOG_CHARACTERS = 500_000
MAX_WATCHED_SOURCE_FILES = 4096


class TimelineThumbnailList(QListWidget):
    """Icon grid that reports a user drop without becoming order authority."""

    reorder_requested = Signal(object, object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setMovement(QListWidget.Movement.Snap)
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setWrapping(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setIconSize(QSize(160, 90))
        self.setGridSize(QSize(190, 130))
        self.setSpacing(6)
        self.setMinimumHeight(150)
        self.setMaximumHeight(300)

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt API
        moved = tuple(
            item.data(Qt.ItemDataRole.UserRole) for item in self.selectedItems()
        )
        super().dropEvent(event)
        order = tuple(
            self.item(index).data(Qt.ItemDataRole.UserRole)
            for index in range(self.count())
        )
        moved_set = set(moved)
        positions = [index for index, item_id in enumerate(order) if item_id in moved_set]
        if not moved or not positions:
            return
        if positions != list(range(positions[0], positions[-1] + 1)):
            self.reorder_requested.emit(moved, "__invalid_noncontiguous__")
            return
        before = next(
            (item_id for item_id in order[positions[-1] + 1 :] if item_id not in moved_set),
            None,
        )
        self.reorder_requested.emit(moved, before)


def default_tool_value(tool_name: str) -> str:
    """Show an absolute tool path when the configured executable is available."""

    return resolve_encoding_tool(tool_name) or tool_name


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
            app_adapter.preview_ready.connect(self._on_visual_preview_ready)
            app_adapter.thumbnails_ready.connect(self._on_thumbnails_ready)
            app_adapter.progress_received.connect(self._on_progress_event)
            app_adapter.execution_state_changed.connect(self._on_execution_state)
            app_adapter.project_ready.connect(self._on_project_ready)
            app_adapter.completed.connect(self._on_application_completed)
        self._active_request: GuiRunRequest | None = None
        self._plan: ExportPlan | None = None
        self._analyzed_plan: ExportPlan | None = None
        self._project_state: ProjectState | None = None
        self._project_repository: JsonProjectRepository | None = None
        self._persisted_project_revision = 0
        self._visual_preview_current = False
        self._thumbnail_pixmaps: dict[str, QPixmap] = {}
        self._thumbnail_failures: dict[str, str] = {}
        self._source_watcher = QFileSystemWatcher(self)
        self._source_change_timer = QTimer(self)
        self._source_change_timer.setSingleShot(True)
        self._source_change_timer.setInterval(150)
        self._source_change_timer.timeout.connect(self._check_source_freshness)
        self._source_watcher.directoryChanged.connect(self._on_source_files_changed)
        self._source_watcher.fileChanged.connect(self._on_source_files_changed)
        self._syncing_timeline_selection = False
        self._tool_setup_process: QProcess | None = None
        self._tool_setup_started = False
        self._cancel_ui_enabled = (
            not self._legacy_mode
            and os.environ.get("VIDEO_CHRONICLE_CANCEL_UI", "1") != "0"
            and isinstance(self._adapter, ApplicationServiceAdapter)
            and self._adapter.supports_cancel
        )
        self._analysis_cancel_ui_enabled = (
            not self._legacy_mode
            and os.environ.get("VIDEO_CHRONICLE_CANCEL_UI", "1") != "0"
            and isinstance(self._adapter, ApplicationServiceAdapter)
            and self._adapter.supports_analysis_cancel
        )
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
            self.overlay_group.setEnabled(False)
            self.preview_button.hide()
            for widget in (
                self.project_open_button,
                self.project_save_button,
                self.move_up_button,
                self.move_down_button,
                self.group_button,
                self.ungroup_button,
                self.preset_save_version_button,
                self.preset_apply_button,
                self.trim_in_spin,
                self.trim_out_spin,
                self.trim_apply_button,
            ):
                widget.hide()
        else:
            self.run_button.setEnabled(False)
        self._update_action_states()

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

        self.main_tab = QWidget()
        self.main_tab.setObjectName("mainSettingsTab")
        main_layout = QVBoxLayout(self.main_tab)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(14)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Режим"))
        self.mode_combo = QComboBox()
        self.mode_combo.setAccessibleName("Режим экспорта")
        self.mode_combo.addItem("Chronicle", ExportMode.CHRONICLE.value)
        self.mode_combo.addItem("Join", ExportMode.JOIN.value)
        mode_row.addWidget(self.mode_combo)
        self.mode_description_label = QLabel(
            "Chronicle создаёт хронологический MP4 и разрешает подпись даты."
        )
        self.mode_description_label.setObjectName("hint")
        self.mode_description_label.setWordWrap(True)
        mode_row.addWidget(self.mode_description_label, 1)
        main_layout.addLayout(mode_row)

        paths = QFormLayout()
        paths.setHorizontalSpacing(18)
        paths.setVerticalSpacing(12)
        paths.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        self.input_edit = QLineEdit(str(default_input))
        self._allow_widget_to_shrink_horizontally(self.input_edit)
        self.input_edit.setAccessibleName("Папка с исходными медиафайлами")
        self.input_button = QPushButton("Выбрать…")
        self.input_button.clicked.connect(self._browse_input)
        paths.addRow("Исходники", self._path_row(self.input_edit, self.input_button))

        self.output_edit = QLineEdit(str(self._suggested_output))
        self._allow_widget_to_shrink_horizontally(self.output_edit)
        self.output_edit.setAccessibleName("Путь итогового MP4-файла")
        self.output_button = QPushButton("Выбрать…")
        self.output_button.clicked.connect(self._browse_output)
        paths.addRow("Результат", self._path_row(self.output_edit, self.output_button))
        main_layout.addLayout(paths)
        main_layout.addStretch(1)

        self.timeline_tab = QWidget()
        self.timeline_tab.setObjectName("timelineTab")
        timeline_tab_layout = QVBoxLayout(self.timeline_tab)
        timeline_tab_layout.setContentsMargins(0, 0, 0, 0)
        self.timeline_scroll = QScrollArea()
        self.timeline_scroll.setObjectName("timelineScroll")
        self.timeline_scroll.viewport().setObjectName("timelineViewport")
        self.timeline_scroll.setWidgetResizable(True)
        self.timeline_scroll.setFrameShape(QFrame.Shape.NoFrame)
        timeline_tab_layout.addWidget(self.timeline_scroll)

        advanced = QGroupBox("Параметры кодирования")
        # Preserve the technical form's row height inside the shared tab frame.
        advanced.setMinimumHeight(245)
        advanced_layout = QGridLayout(advanced)
        advanced_layout.setHorizontalSpacing(12)
        advanced_layout.setVerticalSpacing(10)

        self.ffmpeg_edit = QLineEdit(default_tool_value("ffmpeg"))
        self._allow_widget_to_shrink_horizontally(self.ffmpeg_edit)
        self.ffmpeg_button = QPushButton("Файл…")
        self.ffmpeg_button.clicked.connect(
            lambda: self._browse_tool(self.ffmpeg_edit, "FFmpeg")
        )
        advanced_layout.addWidget(QLabel("FFmpeg"), 0, 0)
        advanced_layout.addWidget(self.ffmpeg_edit, 0, 1)
        advanced_layout.addWidget(self.ffmpeg_button, 0, 2)

        self.ffprobe_edit = QLineEdit(default_tool_value("ffprobe"))
        self._allow_widget_to_shrink_horizontally(self.ffprobe_edit)
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

        self.cache_enabled = QCheckBox("Ускорять повторные экспорты (кэш)")
        self.cache_enabled.setChecked(False)
        self.cache_enabled.setToolTip(
            "Сохранять проверенные подготовленные клипы и не кодировать их заново, "
            "если исходник и настройки не изменились"
        )
        self.cache_dir_edit = QLineEdit("")
        self._allow_widget_to_shrink_horizontally(self.cache_dir_edit)
        self.cache_dir_edit.setPlaceholderText("Системная папка кэша")
        self.cache_dir_button = QPushButton("Папка…")
        self.cache_dir_button.clicked.connect(self._browse_cache_dir)
        self.cache_purge_button = QPushButton("Очистить кэш…")
        self.cache_purge_button.clicked.connect(self._purge_cache)
        self.cache_purge_button.setVisible(not self._legacy_mode)
        advanced_layout.addWidget(self.cache_enabled, 5, 0)
        advanced_layout.addWidget(self.cache_dir_edit, 5, 1)
        advanced_layout.addWidget(self.cache_dir_button, 5, 2)
        advanced_layout.addWidget(self.cache_purge_button, 6, 2)
        cache_hint = QLabel(
            "Кэш ускоряет повторный экспорт, сохраняя проверенные подготовленные "
            "клипы на локальном диске. Он не изменяет исходники и не хранит project "
            "state или итоговый MP4; при необходимости его можно очистить."
        )
        cache_hint.setObjectName("hint")
        cache_hint.setWordWrap(True)
        advanced_layout.addWidget(cache_hint, 7, 0, 1, 3)

        self.overlay_group = QGroupBox("Дата, время и оформление")
        overlay_layout = QGridLayout(self.overlay_group)
        overlay_layout.setHorizontalSpacing(12)
        overlay_layout.setVerticalSpacing(10)
        self.overlay_enabled = QCheckBox("Показывать дату/время на кадре")
        self.overlay_enabled.setChecked(True)
        self.overlay_enabled.setAccessibleName("Включить подпись даты и времени")
        self.overlay_show_date = QCheckBox("Дата")
        self.overlay_show_date.setChecked(True)
        self.overlay_show_time = QCheckBox("Время")
        overlay_layout.addWidget(self.overlay_enabled, 0, 0, 1, 2)
        overlay_layout.addWidget(self.overlay_show_date, 0, 2)
        overlay_layout.addWidget(self.overlay_show_time, 0, 3)

        date_examples = {
            "DD.MM.YY ddd": "12.09.26 Сб (legacy)",
            "DD.MM.YYYY": "12.09.2026",
            "DD/MM/YYYY": "12/09/2026",
            "YYYY-MM-DD": "2026-09-12",
            "MM/DD/YYYY": "09/12/2026",
            "DD MMM YYYY": "12 Sep 2026",
            "DD MMMM YYYY": "12 September 2026",
            "CUSTOM": "Свой формат…",
        }
        self.overlay_format_combo = QComboBox()
        for format_id in DATE_FORMATS:
            self.overlay_format_combo.addItem(date_examples[format_id], format_id)
        self.overlay_custom_date_format = QLineEdit("")
        self._allow_widget_to_shrink_horizontally(self.overlay_custom_date_format)
        self.overlay_custom_date_format.setPlaceholderText("Например: YYYY/MM/DD")
        self.overlay_custom_date_format.setMaxLength(64)
        self.overlay_time_format_combo = QComboBox()
        time_examples = {
            "HH:mm": "23:48",
            "HH:mm:ss": "23:48:17",
            "hh:mm A": "11:48 PM",
            "hh:mm:ss A": "11:48:17 PM",
        }
        for format_id in TIME_FORMATS:
            self.overlay_time_format_combo.addItem(time_examples[format_id], format_id)
        self.overlay_layout_combo = QComboBox()
        for label, layout_id in (
            ("В одну строку", "inline"),
            ("Через разделитель", "separator"),
            ("В две строки", "multiline"),
        ):
            self.overlay_layout_combo.addItem(label, layout_id)
        self.overlay_separator = QLineEdit(" • ")
        self._allow_widget_to_shrink_horizontally(self.overlay_separator)
        self.overlay_separator.setMaxLength(8)
        self.overlay_position_combo = QComboBox()
        self.overlay_position_combo.addItems(list(OVERLAY_POSITIONS))
        self.overlay_position_combo.setCurrentText("bottom-left")
        for widget in (
            self.overlay_format_combo,
            self.overlay_time_format_combo,
            self.overlay_layout_combo,
            self.overlay_position_combo,
        ):
            self._allow_widget_to_shrink_horizontally(widget)
        overlay_layout.addWidget(QLabel("Формат даты"), 1, 0)
        overlay_layout.addWidget(self.overlay_format_combo, 1, 1)
        overlay_layout.addWidget(self.overlay_custom_date_format, 1, 2, 1, 2)
        overlay_layout.addWidget(QLabel("Формат времени"), 2, 0)
        overlay_layout.addWidget(self.overlay_time_format_combo, 2, 1)
        overlay_layout.addWidget(QLabel("Компоновка"), 2, 2)
        overlay_layout.addWidget(self.overlay_layout_combo, 2, 3)
        overlay_layout.addWidget(QLabel("Разделитель"), 3, 0)
        overlay_layout.addWidget(self.overlay_separator, 3, 1)
        overlay_layout.addWidget(QLabel("Позиция"), 3, 2)
        overlay_layout.addWidget(self.overlay_position_combo, 3, 3)

        self.overlay_horizontal_margin = QSpinBox()
        self.overlay_horizontal_margin.setRange(0, 300)
        self.overlay_horizontal_margin.setValue(20)
        self.overlay_vertical_margin = QSpinBox()
        self.overlay_vertical_margin.setRange(0, 300)
        self.overlay_vertical_margin.setValue(20)
        self.overlay_font_size = QSpinBox()
        self.overlay_font_size.setRange(12, 200)
        self.overlay_font_size.setValue(72)
        self.overlay_outline_width = QSpinBox()
        self.overlay_outline_width.setRange(0, 20)
        self.overlay_outline_width.setValue(4)
        overlay_layout.addWidget(QLabel("Отступ X"), 4, 0)
        overlay_layout.addWidget(self.overlay_horizontal_margin, 4, 1)
        overlay_layout.addWidget(QLabel("Отступ Y"), 4, 2)
        overlay_layout.addWidget(self.overlay_vertical_margin, 4, 3)

        self.overlay_font_combo = QComboBox()
        self.overlay_font_combo.addItem("Автоматически (legacy fallback)", None)
        for family in available_overlay_font_families():
            self.overlay_font_combo.addItem(family, family)
        self._allow_widget_to_shrink_horizontally(self.overlay_font_combo)
        overlay_layout.addWidget(QLabel("Системный шрифт"), 5, 0)
        overlay_layout.addWidget(self.overlay_font_combo, 5, 1, 1, 3)

        self.overlay_bold = QCheckBox("Жирный")
        self.overlay_italic = QCheckBox("Курсив")
        overlay_layout.addWidget(QLabel("Размер шрифта"), 6, 0)
        overlay_layout.addWidget(self.overlay_font_size, 6, 1)
        overlay_layout.addWidget(self.overlay_bold, 6, 2)
        overlay_layout.addWidget(self.overlay_italic, 6, 3)

        self.overlay_text_color = QLineEdit("#000000")
        self._allow_widget_to_shrink_horizontally(self.overlay_text_color)
        self.overlay_text_color.setMaxLength(7)
        self.overlay_opacity = QSpinBox()
        self.overlay_opacity.setRange(0, 100)
        self.overlay_opacity.setValue(100)
        self.overlay_opacity.setSuffix(" %")
        self.overlay_outline_enabled = QCheckBox("Обводка")
        self.overlay_outline_enabled.setChecked(True)
        self.overlay_outline_color = QLineEdit("#FFFFFF")
        self._allow_widget_to_shrink_horizontally(self.overlay_outline_color)
        self.overlay_outline_color.setMaxLength(7)
        overlay_layout.addWidget(QLabel("Цвет текста"), 7, 0)
        overlay_layout.addWidget(self.overlay_text_color, 7, 1)
        overlay_layout.addWidget(QLabel("Прозрачность"), 7, 2)
        overlay_layout.addWidget(self.overlay_opacity, 7, 3)
        overlay_layout.addWidget(self.overlay_outline_enabled, 8, 0)
        overlay_layout.addWidget(self.overlay_outline_color, 8, 1)
        overlay_layout.addWidget(QLabel("Толщина"), 8, 2)
        overlay_layout.addWidget(self.overlay_outline_width, 8, 3)

        self.overlay_shadow_enabled = QCheckBox("Тень")
        self.overlay_shadow_opacity = QSpinBox()
        self.overlay_shadow_opacity.setRange(0, 100)
        self.overlay_shadow_opacity.setValue(50)
        self.overlay_shadow_opacity.setSuffix(" %")
        self.overlay_shadow_x = QSpinBox()
        self.overlay_shadow_x.setRange(-50, 50)
        self.overlay_shadow_x.setValue(2)
        self.overlay_shadow_y = QSpinBox()
        self.overlay_shadow_y.setRange(-50, 50)
        self.overlay_shadow_y.setValue(2)
        overlay_layout.addWidget(self.overlay_shadow_enabled, 9, 0)
        overlay_layout.addWidget(self.overlay_shadow_opacity, 9, 1)
        overlay_layout.addWidget(self.overlay_shadow_x, 9, 2)
        overlay_layout.addWidget(self.overlay_shadow_y, 9, 3)

        self.overlay_font_edit = QLineEdit("")
        self._allow_widget_to_shrink_horizontally(self.overlay_font_edit)
        self.overlay_font_edit.setPlaceholderText("Необязательно: точный файл .ttf/.otf")
        self.overlay_font_button = QPushButton("Файл…")
        self.overlay_font_button.clicked.connect(self._browse_overlay_font)
        overlay_layout.addWidget(QLabel("Файл шрифта"), 10, 0)
        overlay_layout.addWidget(self.overlay_font_edit, 10, 1, 1, 2)
        overlay_layout.addWidget(self.overlay_font_button, 10, 3)
        overlay_layout.setColumnStretch(1, 1)
        overlay_layout.setColumnStretch(3, 1)
        self.settings_tabs = QTabWidget()
        self.settings_tabs.setObjectName("settingsTabs")
        self.settings_tabs.setMinimumHeight(520)
        self._allow_widget_to_shrink_horizontally(self.settings_tabs)
        advanced.setTitle("")
        self.overlay_group.setTitle("")
        self.settings_tabs.addTab(self.main_tab, "Основное")
        self.settings_tabs.addTab(self.timeline_tab, "План хронологии")
        self.settings_tabs.addTab(self.overlay_group, "Дата и время")
        self.settings_tabs.addTab(advanced, "Дополнительно")
        self.settings_tabs.setCurrentIndex(0)
        card_layout.addWidget(self.settings_tabs)
        root.addWidget(settings_card)

        action_row = QHBoxLayout()
        self.status_label = QLabel("Настройте параметры и запустите анализ")
        self.status_label.setObjectName("status")
        self.status_label.setWordWrap(True)
        self._allow_widget_to_shrink_horizontally(self.status_label)
        self.analyze_button = QPushButton("Анализировать")
        self.analyze_button.setMinimumHeight(42)
        self.analyze_button.clicked.connect(self._start_analysis)
        self.run_button = QPushButton("Экспортировать")
        self.run_button.setObjectName("primary")
        self.run_button.setMinimumHeight(42)
        self.run_button.clicked.connect(self._start_export)
        self.analysis_cancel_button = QPushButton("Остановить анализ")
        self.analysis_cancel_button.setEnabled(False)
        self.analysis_cancel_button.setVisible(False)
        self.analysis_cancel_button.clicked.connect(self._cancel_analysis)
        self.cancel_button = QPushButton("Остановить экспорт")
        self.cancel_button.setEnabled(False)
        self.cancel_button.setVisible(False)
        self.cancel_button.clicked.connect(self._cancel_export)
        action_row.addWidget(self.status_label, 1)
        action_row.addWidget(self.analyze_button)
        action_row.addWidget(self.run_button)
        action_row.addWidget(self.analysis_cancel_button)
        action_row.addWidget(self.cancel_button)
        root.addLayout(action_row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        root.addWidget(self.progress)

        preview_panel = QFrame()
        preview_panel.setObjectName("timelineContent")
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(0, 0, 8, 0)
        preview_layout.setSpacing(10)
        preview_header = QHBoxLayout()
        preview_title = QLabel("План хронологии")
        preview_title.setObjectName("sectionTitle")
        self.preview_state_label = QLabel("План ещё не построен")
        self.preview_state_label.setObjectName("previewState")
        self.preview_state_label.setAccessibleName("Состояние анализа")
        self.preview_state_label.setWordWrap(True)
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

        editor_actions = QGridLayout()
        editor_actions.setHorizontalSpacing(8)
        editor_actions.setVerticalSpacing(8)
        self.project_open_button = QPushButton("Открыть проект…")
        self.project_save_button = QPushButton("Сохранить проект…")
        self.move_up_button = QPushButton("↑ Выше")
        self.move_up_button.setAccessibleName("Переместить выбранные фрагменты выше")
        self.move_down_button = QPushButton("↓ Ниже")
        self.move_down_button.setAccessibleName("Переместить выбранные фрагменты ниже")
        self.group_button = QPushButton("Группа")
        self.ungroup_button = QPushButton("Разгруппировать")
        self.preset_save_version_button = QPushButton("Сохранить preset version")
        self.preset_apply_button = QPushButton("Применить preset")
        self.trim_in_spin = QSpinBox(); self.trim_in_spin.setRange(0, 2_147_483_647); self.trim_in_spin.setSuffix(" ms")
        self.trim_out_spin = QSpinBox(); self.trim_out_spin.setRange(0, 2_147_483_647); self.trim_out_spin.setSuffix(" ms")
        self.trim_apply_button = QPushButton("Trim")
        for widget, row, column, column_span in (
            (self.project_open_button, 0, 0, 2),
            (self.project_save_button, 1, 0, 2),
            (self.move_up_button, 2, 0, 1),
            (self.move_down_button, 2, 1, 1),
            (self.group_button, 3, 0, 1),
            (self.ungroup_button, 3, 1, 1),
            (self.preset_save_version_button, 4, 0, 2),
            (self.preset_apply_button, 5, 0, 2),
            (self.trim_in_spin, 6, 0, 1),
            (self.trim_out_spin, 6, 1, 1),
            (self.trim_apply_button, 7, 0, 2),
        ):
            editor_actions.addWidget(widget, row, column, 1, column_span)
        editor_actions.setColumnStretch(0, 1)
        editor_actions.setColumnStretch(1, 1)
        self.project_open_button.clicked.connect(self._open_project)
        self.project_save_button.clicked.connect(self._save_project)
        self.move_up_button.clicked.connect(lambda: self._move_selected(-1))
        self.move_down_button.clicked.connect(lambda: self._move_selected(1))
        self.group_button.clicked.connect(self._group_selected)
        self.ungroup_button.clicked.connect(self._ungroup_selected)
        self.preset_save_version_button.clicked.connect(self._save_preset_version)
        self.preset_apply_button.clicked.connect(self._apply_active_preset)
        self.trim_apply_button.clicked.connect(self._trim_selected)
        preview_layout.addLayout(editor_actions)

        self.thumbnail_list = TimelineThumbnailList()
        self.thumbnail_list.setObjectName("thumbnailList")
        self.thumbnail_list.setAccessibleName(
            "Миниатюры фрагментов; перетаскивайте для изменения порядка"
        )
        self.thumbnail_list.itemSelectionChanged.connect(
            self._sync_tree_selection_from_thumbnails
        )
        self.thumbnail_list.reorder_requested.connect(self._apply_thumbnail_move)
        preview_layout.addWidget(self.thumbnail_list)

        self.preview_tree = QTreeWidget()
        self.preview_tree.setObjectName("previewTree")
        self.preview_tree.setAccessibleName("Состав и порядок хронологии")
        self.preview_tree.setHeaderLabels(
            ["№", "Статус", "Файл", "Дата", "Источник", "Timezone", "Конфликт / причина", "Длительность", "Trim"]
        )
        self.preview_tree.setRootIsDecorated(False)
        self.preview_tree.setAlternatingRowColors(True)
        self.preview_tree.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.preview_tree.setUniformRowHeights(True)
        self.preview_tree.setMinimumHeight(165)
        self.preview_tree.itemSelectionChanged.connect(
            self._sync_thumbnail_selection_from_tree
        )
        preview_layout.addWidget(self.preview_tree, 1)

        visual_header = QGridLayout()
        visual_title = QLabel("Кадр с подписью")
        visual_title.setObjectName("sectionTitle")
        self.visual_preview_state_label = QLabel("Предпросмотр не построен")
        self.visual_preview_state_label.setObjectName("previewState")
        self.preview_button = QPushButton("Обновить предпросмотр")
        self.preview_button.setEnabled(False)
        self.preview_button.clicked.connect(self._start_visual_preview)
        visual_header.addWidget(visual_title, 0, 0)
        visual_header.addWidget(self.visual_preview_state_label, 1, 0)
        visual_header.addWidget(self.preview_button, 2, 0)
        visual_header.setColumnStretch(0, 1)
        preview_layout.addLayout(visual_header)
        self.visual_preview_label = QLabel("640 × 360")
        self.visual_preview_label.setObjectName("visualPreview")
        self.visual_preview_label.setAccessibleName("Предпросмотр подписи даты")
        self.visual_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.visual_preview_label.setMinimumSize(320, 180)
        self.visual_preview_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        preview_layout.addWidget(self.visual_preview_label)

        log_panel = QFrame()
        log_panel.setObjectName("logPanel")
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
        self.timeline_scroll.setWidget(preview_panel)
        log_panel.setMinimumHeight(160)
        root.addWidget(log_panel)

        scroll = QScrollArea(self)
        scroll.setObjectName("mainScroll")
        scroll.viewport().setObjectName("mainViewport")
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
            self.cache_enabled,
            self.cache_dir_edit,
            self.cache_dir_button,
            self.cache_purge_button,
            self.mode_combo,
            self.overlay_group,
            self.project_open_button,
            self.project_save_button,
            self.move_up_button,
            self.move_down_button,
            self.group_button,
            self.ungroup_button,
            self.preset_save_version_button,
            self.preset_apply_button,
            self.trim_in_spin,
            self.trim_out_spin,
            self.trim_apply_button,
            self.thumbnail_list,
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
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        self.overlay_enabled.toggled.connect(self._invalidate_overlay)
        self.overlay_show_date.toggled.connect(self._invalidate_overlay)
        self.overlay_show_time.toggled.connect(self._invalidate_overlay)
        self.overlay_format_combo.currentIndexChanged.connect(self._invalidate_overlay)
        self.overlay_custom_date_format.textChanged.connect(self._invalidate_overlay)
        self.overlay_time_format_combo.currentIndexChanged.connect(self._invalidate_overlay)
        self.overlay_layout_combo.currentIndexChanged.connect(self._invalidate_overlay)
        self.overlay_separator.textChanged.connect(self._invalidate_overlay)
        self.overlay_position_combo.currentTextChanged.connect(self._invalidate_overlay)
        self.overlay_horizontal_margin.valueChanged.connect(self._invalidate_overlay)
        self.overlay_vertical_margin.valueChanged.connect(self._invalidate_overlay)
        self.overlay_font_combo.currentIndexChanged.connect(self._invalidate_overlay)
        self.overlay_font_size.valueChanged.connect(self._invalidate_overlay)
        self.overlay_bold.toggled.connect(self._invalidate_overlay)
        self.overlay_italic.toggled.connect(self._invalidate_overlay)
        self.overlay_opacity.valueChanged.connect(self._invalidate_overlay)
        self.overlay_outline_enabled.toggled.connect(self._invalidate_overlay)
        self.overlay_outline_width.valueChanged.connect(self._invalidate_overlay)
        self.overlay_text_color.textChanged.connect(self._invalidate_overlay)
        self.overlay_outline_color.textChanged.connect(self._invalidate_overlay)
        self.overlay_shadow_enabled.toggled.connect(self._invalidate_overlay)
        self.overlay_shadow_opacity.valueChanged.connect(self._invalidate_overlay)
        self.overlay_shadow_x.valueChanged.connect(self._invalidate_overlay)
        self.overlay_shadow_y.valueChanged.connect(self._invalidate_overlay)
        self.overlay_font_edit.textChanged.connect(self._invalidate_overlay)
        self._update_overlay_control_state()

    @staticmethod
    def _allow_widget_to_shrink_horizontally(widget: QWidget) -> None:
        policy = widget.sizePolicy()
        policy.setHorizontalPolicy(QSizePolicy.Policy.Ignored)
        widget.setSizePolicy(policy)
        widget.setMinimumWidth(0)

    def ensure_encoding_tools(self) -> None:
        """Resolve tools or asynchronously install the pinned Windows package."""

        if self._tool_setup_started:
            return
        self._tool_setup_started = True
        ffmpeg, ffprobe = resolve_encoding_tools()
        if ffmpeg and ffprobe:
            self._apply_encoding_tool_paths(ffmpeg, ffprobe)
            self.status_label.setText("FFmpeg и FFprobe найдены автоматически")
            return
        if sys.platform != "win32":
            self.status_label.setText(
                "FFmpeg/FFprobe не найдены. Установите их через системный package manager "
                "или укажите пути в разделе «Дополнительно»."
            )
            return
        winget = resolve_winget()
        if winget is None:
            self.status_label.setText(
                "FFmpeg/FFprobe не найдены, а WinGet недоступен. Установите Microsoft "
                "App Installer или укажите пути в разделе «Дополнительно»."
            )
            return

        self.status_label.setText(
            f"FFmpeg {FFMPEG_WINGET_VERSION} не найден — выполняется автоматическая установка…"
        )
        self.analyze_button.setEnabled(False)
        self.run_button.setEnabled(False)
        process = QProcess(self)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.setProgram(winget)
        process.setArguments(winget_ffmpeg_install_arguments())
        process.errorOccurred.connect(self._on_encoding_tool_setup_error)
        process.finished.connect(self._on_encoding_tool_setup_finished)
        self._tool_setup_process = process
        process.start()

    def _apply_encoding_tool_paths(self, ffmpeg: str, ffprobe: str) -> None:
        self.ffmpeg_edit.setText(ffmpeg)
        self.ffprobe_edit.setText(ffprobe)

    def _restore_actions_after_tool_setup(self) -> None:
        if self._legacy_mode:
            self.run_button.setEnabled(True)
        else:
            self.analyze_button.setEnabled(True)

    def _release_tool_setup_process(self) -> None:
        process = self._tool_setup_process
        self._tool_setup_process = None
        if process is not None:
            process.deleteLater()

    @Slot(QProcess.ProcessError)
    def _on_encoding_tool_setup_error(self, error: QProcess.ProcessError) -> None:
        if error != QProcess.ProcessError.FailedToStart:
            return
        self.status_label.setText(
            "Не удалось запустить WinGet. Укажите FFmpeg/FFprobe в разделе «Дополнительно»."
        )
        self._release_tool_setup_process()
        self._restore_actions_after_tool_setup()

    @Slot(int, QProcess.ExitStatus)
    def _on_encoding_tool_setup_finished(
        self, exit_code: int, exit_status: QProcess.ExitStatus
    ) -> None:
        self._release_tool_setup_process()
        if exit_status != QProcess.ExitStatus.NormalExit or exit_code != 0:
            self.status_label.setText(
                f"Автоматическая установка FFmpeg завершилась с кодом {exit_code}. "
                "Укажите пути в разделе «Дополнительно»."
            )
            self._restore_actions_after_tool_setup()
            return
        refresh_windows_process_path()
        ffmpeg, ffprobe = resolve_encoding_tools()
        if not ffmpeg or not ffprobe:
            self.status_label.setText(
                "FFmpeg установлен, но новые пути пока не найдены. Перезапустите GUI "
                "или укажите их в разделе «Дополнительно»."
            )
            self._restore_actions_after_tool_setup()
            return
        self._apply_encoding_tool_paths(ffmpeg, ffprobe)
        self.status_label.setText(
            f"FFmpeg {FFMPEG_WINGET_VERSION} установлен и готов к работе"
        )
        self._restore_actions_after_tool_setup()

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

    @Slot()
    def _browse_overlay_font(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите шрифт подписи",
            self.overlay_font_edit.text(),
            "Fonts (*.ttf *.otf)",
        )
        if selected:
            self.overlay_font_combo.setCurrentIndex(0)
            self.overlay_font_edit.setText(selected)

    def _browse_tool(self, target: QLineEdit, label: str) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self, f"Выберите {label}", target.text(), "Executable (*.exe);;All files (*)"
        )
        if selected:
            target.setText(selected)

    @Slot()
    def _browse_cache_dir(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self, "Выберите приватную папку кэша", self.cache_dir_edit.text()
        )
        if selected:
            self.cache_dir_edit.setText(selected)

    @Slot()
    def _purge_cache(self) -> None:
        if self._legacy_mode or self._adapter.is_running:
            return
        answer = QMessageBox.question(
            self,
            "Очистить кэш?",
            "Будут удалены только проверенные промежуточные клипы. Исходники и результат не изменятся.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        raw = self.cache_dir_edit.text().strip()
        cache_dir = Path(raw).expanduser() if raw else None
        self._set_running(True)
        try:
            assert isinstance(self._adapter, ApplicationServiceAdapter)
            input_dir = Path(self.input_edit.text().strip()).expanduser().resolve()
            output = Path(self.output_edit.text().strip()).expanduser().resolve()
            self._adapter.start_cache_purge(
                cache_dir,
                protected_input=input_dir,
                protected_output=output,
            )
        except RuntimeError as exc:
            self._on_application_completed("cache-purge", False, str(exc))

    def _form_request(self) -> GuiRunRequest:
        return create_run_request(
            input_dir_text=self.input_edit.text(),
            output_text=self.output_edit.text(),
            ffmpeg_text=self.ffmpeg_edit.text(),
            ffprobe_text=self.ffprobe_edit.text(),
            crf=self.crf_spin.value(),
            preset_text=self.preset_combo.currentText(),
            overlay=self._form_overlay_config(resolve_fallback=False),
            mode=self._selected_mode(),
            cache_enabled=self.cache_enabled.isChecked(),
            cache_dir_text=self.cache_dir_edit.text(),
        )

    def _selected_mode(self) -> ExportMode:
        mode = self.mode_combo.currentData()
        try:
            return ExportMode(mode)
        except (TypeError, ValueError):
            return ExportMode.CHRONICLE

    def _form_overlay_config(self, *, resolve_fallback: bool) -> OverlayConfig:
        raw_font = self.overlay_font_edit.text().strip()
        try:
            config = OverlayConfig(
                enabled=(
                    self.overlay_enabled.isChecked()
                    and self._selected_mode() is ExportMode.CHRONICLE
                ),
                format=None,
                show_date=self.overlay_show_date.isChecked(),
                show_time=self.overlay_show_time.isChecked(),
                date_format=self.overlay_format_combo.currentData(),
                custom_date_format=(
                    self.overlay_custom_date_format.text()
                    if self.overlay_format_combo.currentData() == "CUSTOM"
                    else None
                ),
                time_format=self.overlay_time_format_combo.currentData(),
                layout=self.overlay_layout_combo.currentData(),
                separator=self.overlay_separator.text(),
                position=self.overlay_position_combo.currentText(),  # type: ignore[arg-type]
                horizontal_margin=self.overlay_horizontal_margin.value(),
                vertical_margin=self.overlay_vertical_margin.value(),
                font_family=(
                    None if raw_font else self.overlay_font_combo.currentData()
                ),
                font_size=self.overlay_font_size.value(),
                bold=self.overlay_bold.isChecked(),
                italic=self.overlay_italic.isChecked(),
                text_color=self.overlay_text_color.text().strip(),
                opacity=self.overlay_opacity.value() / 100,
                outline_enabled=self.overlay_outline_enabled.isChecked(),
                outline_color=self.overlay_outline_color.text().strip(),
                outline_width=self.overlay_outline_width.value(),
                shadow_enabled=self.overlay_shadow_enabled.isChecked(),
                shadow_opacity=self.overlay_shadow_opacity.value() / 100,
                shadow_offset_x=self.overlay_shadow_x.value(),
                shadow_offset_y=self.overlay_shadow_y.value(),
                font_file=Path(raw_font).expanduser() if raw_font else None,
            )
            if resolve_fallback:
                from video_chronicle import pipeline

                config = resolve_overlay_font(config, pipeline.find_default_font())
            return config
        except (ValueError, RuntimeError) as exc:
            raise RequestValidationError(str(exc)) from exc

    def _update_overlay_control_state(self) -> None:
        active = self.overlay_enabled.isChecked()
        self.overlay_show_date.setEnabled(active)
        self.overlay_show_time.setEnabled(active)
        self.overlay_format_combo.setEnabled(active and self.overlay_show_date.isChecked())
        self.overlay_custom_date_format.setEnabled(
            active
            and self.overlay_show_date.isChecked()
            and self.overlay_format_combo.currentData() == "CUSTOM"
        )
        self.overlay_time_format_combo.setEnabled(active and self.overlay_show_time.isChecked())
        both = active and self.overlay_show_date.isChecked() and self.overlay_show_time.isChecked()
        self.overlay_layout_combo.setEnabled(both)
        self.overlay_separator.setEnabled(
            both and self.overlay_layout_combo.currentData() == "separator"
        )
        self.overlay_outline_color.setEnabled(active and self.overlay_outline_enabled.isChecked())
        self.overlay_outline_width.setEnabled(active and self.overlay_outline_enabled.isChecked())
        self.overlay_shadow_opacity.setEnabled(active and self.overlay_shadow_enabled.isChecked())
        self.overlay_shadow_x.setEnabled(active and self.overlay_shadow_enabled.isChecked())
        self.overlay_shadow_y.setEnabled(active and self.overlay_shadow_enabled.isChecked())

    @Slot(int)
    def _on_mode_changed(self, _index: int) -> None:
        mode = self._selected_mode()
        is_join = mode is ExportMode.JOIN
        self.overlay_group.setEnabled(not is_join and not self._legacy_mode)
        if is_join:
            self.mode_description_label.setText(
                "Join создаёт хронологический MP4 без подписи даты."
            )
        else:
            self.mode_description_label.setText(
                "Chronicle создаёт хронологический MP4 и разрешает подпись даты."
            )
        self._invalidate_plan()
        if is_join:
            self.visual_preview_state_label.setText("Отключён в режиме Join")
            self.visual_preview_label.setText("Join не добавляет подпись даты")
            self.preview_button.setEnabled(False)

    @Slot()
    def _invalidate_plan(self, *_args: object) -> None:
        if self._building_ui or self._legacy_mode:
            return
        if self._analyzed_plan is not None and isinstance(
            self._adapter, ApplicationServiceAdapter
        ):
            try:
                request = self._form_request()
                reconfigured = self._adapter.rebind_plan(
                    request, self._analyzed_plan
                )
            except (RequestValidationError, RuntimeError, OSError, ValueError):
                reconfigured = None
            if reconfigured is not None:
                previous_request = self._plan.request if self._plan is not None else None
                self._active_request = request
                self._analyzed_plan = reconfigured
                if self._project_state is not None:
                    active = self._project_state.resolve_active_preset()
                    settings = RenderSettings(
                        reconfigured.request.mode,
                        reconfigured.request.overlay,
                        reconfigured.request.crf,
                        reconfigured.request.preset,
                    )
                    if active.settings != settings:
                        self._project_state = self._project_state.save_preset(
                            active.preset_id, active.name, settings
                        )
                    self._plan = apply_project_state(
                        self._analyzed_plan, self._project_state
                    )
                else:
                    self._plan = reconfigured
                visual_changed = (
                    previous_request is None
                    or previous_request.mode is not self._plan.request.mode
                    or previous_request.overlay != self._plan.request.overlay
                )
                if visual_changed:
                    self._visual_preview_current = False
                    self.visual_preview_state_label.setText("Предпросмотр устарел")
                    self.visual_preview_label.setText(
                        "Настройки обновлены; кадр можно обновить отдельно"
                    )
                self.preview_button.setEnabled(
                    self._plan.request.mode is not ExportMode.JOIN
                    and not self._adapter.is_running
                )
                self._update_plan_summary(self._plan)
                self.preview_state_label.setText("План обновлён без повторного анализа")
                self.status_label.setText("Настройки применены — экспорт доступен")
                self.run_button.setEnabled(not self._adapter.is_running)
                self._update_action_states()
                return
        self._mark_source_analysis_stale()

    def _mark_source_analysis_stale(self) -> None:
        self._plan = None
        self._active_request = None
        self._visual_preview_current = False
        self.visual_preview_label.clear()
        self.visual_preview_state_label.setText("Предпросмотр устарел")
        self.preview_button.setEnabled(False)
        self.preview_tree.clear()
        self.thumbnail_list.clear()
        self._thumbnail_pixmaps.clear()
        self._thumbnail_failures.clear()
        self.preview_state_label.setText("План устарел — повторите анализ")
        self.plan_summary_label.setText(
            "Параметры изменены. Экспорт недоступен до повторного анализа."
        )
        if not self._adapter.is_running:
            self.run_button.setEnabled(False)
            self.status_label.setText("Требуется повторный анализ")

    @Slot(str)
    def _on_source_files_changed(self, _path: str) -> None:
        if self._building_ui or self._legacy_mode or self._adapter.is_running:
            return
        self._source_change_timer.start()

    def _check_source_freshness(self) -> bool:
        if (
            self._building_ui
            or self._legacy_mode
            or self._adapter.is_running
            or self._analyzed_plan is None
            or not isinstance(self._adapter, ApplicationServiceAdapter)
        ):
            return False
        try:
            request = self._form_request()
            fresh = self._adapter.reconfigure_plan(request, self._analyzed_plan)
        except (RequestValidationError, RuntimeError, OSError, ValueError):
            fresh = None
        if fresh is None:
            self._mark_source_analysis_stale()
            return False
        self._active_request = request
        self._analyzed_plan = fresh
        return True

    def _watch_analyzed_sources(self, plan: ExportPlan) -> None:
        watched = self._source_watcher.files() + self._source_watcher.directories()
        if watched:
            self._source_watcher.removePaths(watched)
        source_paths = [item.path for item in plan.items]
        source_paths.extend(path for path, _reason in plan.inspection_failures)
        paths = [str(plan.request.input_dir)]
        paths.extend(
            str(path)
            for path in source_paths[:MAX_WATCHED_SOURCE_FILES]
            if path.is_file()
        )
        self._source_watcher.addPaths(paths)

    @Slot()
    def _invalidate_overlay(self, *_args: object) -> None:
        self._update_overlay_control_state()
        if self._building_ui or self._legacy_mode:
            return
        self._invalidate_plan()

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
        self._visual_preview_current = False
        self._active_request = request
        self.preview_tree.clear()
        self.thumbnail_list.clear()
        self._thumbnail_pixmaps.clear()
        self._thumbnail_failures.clear()
        self.log_view.clear()
        self.result_label.clear()
        self.preview_state_label.setText("Анализ выполняется…")
        self.visual_preview_state_label.setText("Ожидание плана…")
        self.visual_preview_label.clear()
        self.preview_button.setEnabled(False)
        self.plan_summary_label.setText(f"Проверка: {request.input_dir}")
        self._set_running(True)
        try:
            assert isinstance(self._adapter, ApplicationServiceAdapter)
            self._adapter.start_analysis(
                request, previous_plan=self._analyzed_plan
            )
        except RuntimeError as exc:
            self._on_application_completed("analysis", False, str(exc))

    @Slot(str)
    def _on_application_started(self, operation: str) -> None:
        if operation == "analysis":
            self.status_label.setText("Анализ медиафайлов…")
            self.analysis_cancel_button.setVisible(self._analysis_cancel_ui_enabled)
            self.analysis_cancel_button.setEnabled(self._analysis_cancel_ui_enabled)
            self.cancel_button.setVisible(False)
        elif operation == "thumbnails":
            self.status_label.setText("Создание миниатюр…")
            self.analysis_cancel_button.setVisible(False)
            self.cancel_button.setVisible(False)
        else:
            self.status_label.setText("Медиаконвейер выполняется…")
            self.analysis_cancel_button.setVisible(False)
            is_export = operation == "export"
            self.cancel_button.setVisible(is_export and self._cancel_ui_enabled)
            self.cancel_button.setEnabled(is_export and self._cancel_ui_enabled)

    @Slot(object)
    def _on_progress_event(self, value: object) -> None:
        if not isinstance(value, ProgressEvent):
            return
        if value.total_units is None:
            self.progress.setRange(0, 0)
            return
        self.progress.setRange(0, max(1, value.total_units))
        self.progress.setValue(value.completed_units)
        self.progress.setTextVisible(True)
        if value.operation == "export":
            self.cancel_button.setEnabled(self._cancel_ui_enabled)
            phase_names = {
                "preflight": "Проверка плана…",
                "normalize": "Нормализация медиа…",
                "concat": "Объединение клипов…",
                "publication": "Результат опубликован",
            }
            status = phase_names.get(value.phase, value.phase)
            if value.phase == "normalize" and value.cache_hit is not None:
                status += " (кэш: hit)" if value.cache_hit else " (кэш: miss)"
            self.status_label.setText(status)

    @Slot(str)
    def _on_execution_state(self, state: str) -> None:
        if state == "cancel-requested":
            operation = (
                self._adapter.current_operation
                if isinstance(self._adapter, ApplicationServiceAdapter)
                else None
            )
            if operation == "analysis":
                self.status_label.setText("Остановка анализа…")
                self.analysis_cancel_button.setEnabled(False)
            else:
                self.status_label.setText("Остановка экспорта…")
                self.cancel_button.setEnabled(False)

    @Slot()
    def _cancel_analysis(self) -> None:
        if not isinstance(self._adapter, ApplicationServiceAdapter):
            return
        if self._adapter.cancel_analysis():
            self.status_label.setText("Остановка анализа…")
            self.analysis_cancel_button.setEnabled(False)

    @Slot()
    def _cancel_export(self) -> None:
        if not isinstance(self._adapter, ApplicationServiceAdapter):
            return
        if self._adapter.cancel_export():
            self.status_label.setText("Остановка экспорта…")
            self.cancel_button.setEnabled(False)

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
            or plan.request.mode is not active.mode
        ):
            return
        candidate_state = self._project_state
        candidate_plan = plan
        if self._project_state is not None:
            try:
                candidate_state = reconcile_project_sources(
                    self._project_state, plan
                )
                candidate_plan = apply_project_state(plan, candidate_state)
            except ValueError as exc:
                QMessageBox.warning(self, "Проект", str(exc))
                return
        self._analyzed_plan = plan
        self._project_state = candidate_state
        self._plan = candidate_plan
        self._visual_preview_current = False
        self._populate_preview(candidate_plan)
        self._watch_analyzed_sources(self._analyzed_plan)

    def _ensure_project_state(self) -> ProjectState:
        if self._project_state is not None:
            return self._project_state
        self._project_state = self._build_project_state()
        return self._project_state

    def _build_project_state(self) -> ProjectState:
        if self._analyzed_plan is None:
            raise RuntimeError("Сначала выполните анализ.")
        timeline = Timeline.build(
            TimelineItem.from_media_item(item) for item in self._analyzed_plan.items
        )
        request = self._analyzed_plan.request
        settings = RenderSettings(
            request.mode,
            request.overlay,
            request.crf,
            request.preset,
        )
        preset = RenderPreset("gui-default", 1, "GUI default", settings)
        digest = hashlib.sha256(
            str(request.input_dir).encode("utf-8")
        ).hexdigest()[:16]
        return ProjectState(
            f"project-{digest}",
            timeline,
            revision=0,
            layout=TimelineLayout.identity(timeline),
            presets=(preset,),
            active_preset=preset.ref,
        )

    def _refresh_edited_plan(self) -> None:
        if self._analyzed_plan is None or self._project_state is None:
            return
        selected_ids = set(self._selected_item_ids())
        self._plan = apply_project_state(self._analyzed_plan, self._project_state)
        tree_blocked = self.preview_tree.blockSignals(True)
        cards_blocked = self.thumbnail_list.blockSignals(True)
        try:
            self._populate_preview(self._plan)
            self._select_timeline_ids(selected_ids)
        finally:
            self.preview_tree.blockSignals(tree_blocked)
            self.thumbnail_list.blockSignals(cards_blocked)
        self._visual_preview_current = False
        self.visual_preview_state_label.setText("Предпросмотр устарел")
        self.preview_button.setEnabled(True)
        self.preview_state_label.setText("План изменён; preview можно обновить отдельно")
        self.run_button.setEnabled(not self._adapter.is_running)
        self._update_action_states()

    def _selected_item_ids(self) -> tuple[str, ...]:
        card_ids = tuple(
            item_id
            for item in self.thumbnail_list.selectedItems()
            if isinstance(
                (item_id := item.data(Qt.ItemDataRole.UserRole)), str
            )
        )
        if card_ids:
            return card_ids
        return tuple(
            item_id
            for item in self.preview_tree.selectedItems()
            if isinstance(
                (item_id := item.data(0, Qt.ItemDataRole.UserRole)), str
            )
        )

    def _select_timeline_ids(self, item_ids: set[str]) -> None:
        for index in range(self.thumbnail_list.count()):
            card = self.thumbnail_list.item(index)
            card.setSelected(card.data(Qt.ItemDataRole.UserRole) in item_ids)
        for index in range(self.preview_tree.topLevelItemCount()):
            row = self.preview_tree.topLevelItem(index)
            row.setSelected(row.data(0, Qt.ItemDataRole.UserRole) in item_ids)

    @Slot()
    def _sync_tree_selection_from_thumbnails(self) -> None:
        if self._syncing_timeline_selection:
            return
        self._syncing_timeline_selection = True
        try:
            selected = {
                item.data(Qt.ItemDataRole.UserRole)
                for item in self.thumbnail_list.selectedItems()
            }
            blocked = self.preview_tree.blockSignals(True)
            try:
                for index in range(self.preview_tree.topLevelItemCount()):
                    row = self.preview_tree.topLevelItem(index)
                    row.setSelected(row.data(0, Qt.ItemDataRole.UserRole) in selected)
            finally:
                self.preview_tree.blockSignals(blocked)
        finally:
            self._syncing_timeline_selection = False
        self._update_action_states()

    @Slot()
    def _sync_thumbnail_selection_from_tree(self) -> None:
        if self._syncing_timeline_selection:
            return
        self._syncing_timeline_selection = True
        try:
            selected = {
                row.data(0, Qt.ItemDataRole.UserRole)
                for row in self.preview_tree.selectedItems()
                if isinstance(row.data(0, Qt.ItemDataRole.UserRole), str)
            }
            blocked = self.thumbnail_list.blockSignals(True)
            try:
                for index in range(self.thumbnail_list.count()):
                    card = self.thumbnail_list.item(index)
                    card.setSelected(card.data(Qt.ItemDataRole.UserRole) in selected)
            finally:
                self.thumbnail_list.blockSignals(blocked)
        finally:
            self._syncing_timeline_selection = False
        self._update_action_states()

    @Slot(object, object)
    def _apply_thumbnail_move(
        self, moved_ids_value: object, before_item_id_value: object
    ) -> None:
        if self._adapter.is_running or self._plan is None:
            if self._plan is not None:
                self._populate_preview(self._plan)
            return
        moved_ids = tuple(moved_ids_value) if isinstance(moved_ids_value, tuple) else ()
        before_item_id = (
            before_item_id_value if isinstance(before_item_id_value, str) else None
        )
        if before_item_id == "__invalid_noncontiguous__":
            self._populate_preview(self._plan)
            self.status_label.setText("Перетаскивайте выбранные фрагменты единым блоком")
            return
        try:
            current = self._ensure_project_state()
            candidate = current.move_items(moved_ids, before_item_id)
        except (RuntimeError, ValueError) as exc:
            self._populate_preview(self._plan)
            self.status_label.setText(f"Порядок не изменён: {exc}")
            return
        if candidate.layout == current.layout:
            self._populate_preview(self._plan)
            return
        self._project_state = candidate
        self._refresh_edited_plan()

    def _move_candidate(
        self,
        direction: int,
        state: ProjectState | None = None,
    ) -> ProjectState | None:
        ids = self._selected_item_ids()
        if not ids or self._plan is None:
            return None
        try:
            state = state or self._project_state or self._build_project_state()
        except RuntimeError:
            return None
        assert state.layout is not None
        selected = set(ids)
        positions = [
            index
            for index, entry in enumerate(state.layout.entries)
            if entry.item_id in selected
        ]
        if not positions:
            return None
        target = min(positions) - 1 if direction < 0 else max(positions) + 2
        if target < 0 or target > len(state.layout.entries):
            return None
        before = (
            state.layout.entries[target].item_id
            if target < len(state.layout.entries)
            else None
        )
        try:
            candidate = state.move_items(ids, before)
        except ValueError:
            return None
        return candidate if candidate.layout != state.layout else None

    @Slot()
    def _update_action_states(self) -> None:
        running = self._adapter.is_running
        editable = not self._legacy_mode and not running and self._plan is not None
        ids = self._selected_item_ids() if editable else ()
        state = self._project_state
        if editable and ids and state is None:
            try:
                state = self._build_project_state()
            except RuntimeError:
                state = None

        self.project_save_button.setEnabled(
            not self._legacy_mode and not running and self._plan is not None
        )
        self.move_up_button.setEnabled(
            editable and self._move_candidate(-1, state) is not None
        )
        self.move_down_button.setEnabled(
            editable and self._move_candidate(1, state) is not None
        )

        can_group = False
        if editable and state is not None and len(ids) >= 2:
            try:
                state.create_group(
                    f"group-{state.revision + 1}",
                    f"Группа {state.revision + 1}",
                    ids,
                )
            except ValueError:
                pass
            else:
                can_group = True
        self.group_button.setEnabled(can_group)

        groups: set[str] = set()
        if editable and state is not None and state.layout is not None:
            selected = set(ids)
            groups = {
                entry.group_id
                for entry in state.layout.entries
                if entry.item_id in selected and entry.group_id is not None
            }
        self.ungroup_button.setEnabled(len(groups) == 1)
        single_item = editable and len(ids) == 1
        self.trim_in_spin.setEnabled(single_item)
        self.trim_out_spin.setEnabled(single_item)
        self.trim_apply_button.setEnabled(single_item)
        self.preset_save_version_button.setEnabled(editable)
        self.preset_apply_button.setEnabled(
            editable and state is not None and state.active_preset is not None
        )

    @Slot()
    def _move_selected(self, direction: int) -> None:
        candidate = self._move_candidate(direction)
        if candidate is None:
            return
        self._project_state = candidate
        self._refresh_edited_plan()

    @Slot()
    def _group_selected(self) -> None:
        ids = self._selected_item_ids()
        if len(ids) < 2: return
        state = self._ensure_project_state()
        group_id = f"group-{state.revision + 1}"
        try: self._project_state = state.create_group(group_id, f"Группа {state.revision + 1}", ids)
        except ValueError as exc: QMessageBox.warning(self, "Группа", str(exc)); return
        self._refresh_edited_plan()

    @Slot()
    def _ungroup_selected(self) -> None:
        state = self._ensure_project_state(); assert state.layout is not None
        ids = self._selected_item_ids()
        groups = {entry.group_id for entry in state.layout.entries if entry.item_id in ids and entry.group_id}
        if len(groups) != 1: return
        self._project_state = state.ungroup(next(iter(groups))); self._refresh_edited_plan()

    @Slot()
    def _trim_selected(self) -> None:
        ids = self._selected_item_ids()
        if len(ids) != 1: return
        try: self._project_state = self._ensure_project_state().set_trim(ids[0], TrimRange(self.trim_in_spin.value() * 1000, self.trim_out_spin.value() * 1000))
        except ValueError as exc: QMessageBox.warning(self, "Trim", str(exc)); return
        self._refresh_edited_plan()

    @Slot()
    def _save_preset_version(self) -> None:
        state = self._ensure_project_state()
        try:
            settings = RenderSettings(self._selected_mode(), self._form_overlay_config(resolve_fallback=True), self.crf_spin.value(), self.preset_combo.currentText().strip())
            preset_id = state.active_preset.preset_id if state.active_preset is not None else "gui-default"
            self._project_state = state.save_preset(preset_id, self.preset_combo.currentText().strip() or "Preset", settings)
        except (ValueError, RuntimeError) as exc:
            QMessageBox.warning(self, "Preset", str(exc)); return
        self._refresh_edited_plan()

    @staticmethod
    def _set_combo_data(combo: QComboBox, value: object) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _apply_render_settings_to_form(self, settings: RenderSettings) -> None:
        previous = self._building_ui
        self._building_ui = True
        try:
            self._set_combo_data(self.mode_combo, settings.mode.value)
            overlay = settings.overlay
            self.overlay_enabled.setChecked(overlay.enabled)
            self.overlay_show_date.setChecked(overlay.show_date)
            self.overlay_show_time.setChecked(overlay.show_time)
            self._set_combo_data(self.overlay_format_combo, overlay.date_format)
            self.overlay_custom_date_format.setText(overlay.custom_date_format or "")
            self._set_combo_data(self.overlay_time_format_combo, overlay.time_format)
            self._set_combo_data(self.overlay_layout_combo, overlay.layout)
            self.overlay_separator.setText(overlay.separator)
            self.overlay_position_combo.setCurrentText(overlay.position)
            self.overlay_horizontal_margin.setValue(overlay.horizontal_margin)
            self.overlay_vertical_margin.setValue(overlay.vertical_margin)
            if overlay.font_family is not None and self.overlay_font_combo.findData(overlay.font_family) < 0:
                self.overlay_font_combo.addItem(
                    f"{overlay.font_family} (недоступен — будет fallback)",
                    overlay.font_family,
                )
            self._set_combo_data(self.overlay_font_combo, overlay.font_family)
            self.overlay_font_edit.setText(
                "" if overlay.font_file is None else str(overlay.font_file)
            )
            self.overlay_font_size.setValue(overlay.font_size)
            self.overlay_bold.setChecked(overlay.bold)
            self.overlay_italic.setChecked(overlay.italic)
            self.overlay_text_color.setText(overlay.text_color)
            self.overlay_opacity.setValue(round(overlay.opacity * 100))
            self.overlay_outline_enabled.setChecked(overlay.outline_enabled)
            self.overlay_outline_color.setText(overlay.outline_color)
            self.overlay_outline_width.setValue(overlay.outline_width)
            self.overlay_shadow_enabled.setChecked(overlay.shadow_enabled)
            self.overlay_shadow_opacity.setValue(round(overlay.shadow_opacity * 100))
            self.overlay_shadow_x.setValue(overlay.shadow_offset_x)
            self.overlay_shadow_y.setValue(overlay.shadow_offset_y)
            self.crf_spin.setValue(settings.crf)
            self.preset_combo.setCurrentText(settings.encoder_preset)
        finally:
            self._building_ui = previous
        self._update_overlay_control_state()

    @Slot()
    def _apply_active_preset(self) -> None:
        state = self._ensure_project_state()
        if state.active_preset is None: return
        preset = state.resolve_active_preset()
        self._apply_render_settings_to_form(preset.settings)
        self._project_state = state.apply_preset(preset.ref)
        self._refresh_edited_plan()

    @Slot()
    def _save_project(self) -> None:
        if not isinstance(self._adapter, ApplicationServiceAdapter): return
        state = self._ensure_project_state()
        selected = QFileDialog.getExistingDirectory(
            self, "Папка хранения проектов", str(Path.home())
        )
        if not selected: return
        repository = JsonProjectRepository(Path(selected) / ".video-chronicle-projects")
        self._project_repository = repository
        self._adapter.start_project_save(
            repository,
            state,
            expected_revision=self._persisted_project_revision,
        )

    @Slot()
    def _open_project(self) -> None:
        if not isinstance(self._adapter, ApplicationServiceAdapter): return
        selected, _ = QFileDialog.getOpenFileName(self, "Открыть проект", "", "Video Chronicle project (*.json)")
        if not selected: return
        path = Path(selected); self._project_repository = JsonProjectRepository(path.parent)
        self._adapter.start_project_open(self._project_repository, path.stem)

    @Slot(object)
    def _on_project_ready(self, state: object) -> None:
        if not isinstance(state, ProjectState): return
        self._project_state = state
        self._persisted_project_revision = state.revision
        self._apply_render_settings_to_form(state.resolve_active_preset().settings)
        try: self._refresh_edited_plan()
        except ValueError as exc: QMessageBox.warning(self, "Проект", str(exc))

    def _populate_preview(self, plan: ExportPlan) -> None:
        selected_ids = set(self._selected_item_ids())
        cards_blocked = self.thumbnail_list.blockSignals(True)
        self.thumbnail_list.clear()
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
            item_id = TimelineItem.from_media_item(item).stable_id
            card = QListWidgetItem(f"{index}. {item.path.name}")
            card.setData(Qt.ItemDataRole.UserRole, item_id)
            card.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
            card.setFlags(
                card.flags()
                | Qt.ItemFlag.ItemIsDragEnabled
                | Qt.ItemFlag.ItemIsDropEnabled
            )
            card.setToolTip(str(item.path))
            card_pixmap = self._thumbnail_pixmaps.get(item_id)
            if card_pixmap is None:
                card_pixmap = self._thumbnail_placeholder(
                    failed=item_id in self._thumbnail_failures
                )
            card.setIcon(QIcon(card_pixmap))
            if item_id in self._thumbnail_failures:
                card.setToolTip(
                    f"{item.path}\nМиниатюра недоступна: "
                    f"{self._thumbnail_failures[item_id]}"
                )
            self.thumbnail_list.addItem(card)
            row = QTreeWidgetItem(
                [
                    str(index),
                    "Принят",
                    str(item.path),
                    item.taken_at.strftime("%d.%m.%Y %H:%M:%S"),
                    provenance,
                    timezone,
                    conflicts,
                    "—" if item.source_duration_us is None else f"{item.source_duration_us / 1_000_000:.3f} s",
                    f"{item.trim_in_us / 1_000_000:.3f}–" + ("full" if item.trim_out_us is None else f"{item.trim_out_us / 1_000_000:.3f} s"),
                ]
            )
            row.setData(
                0,
                Qt.ItemDataRole.UserRole,
                item_id,
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
                ["—", "Пропущен", str(path), "—", "—", "—", reason, "—", "—"]
            )
            row.setToolTip(2, str(path))
            row.setToolTip(6, reason)
            self.preview_tree.addTopLevelItem(row)

        self._select_timeline_ids(selected_ids)
        self.thumbnail_list.blockSignals(cards_blocked)

        self.preview_tree.resizeColumnToContents(0)
        self.preview_tree.resizeColumnToContents(1)
        self.preview_tree.resizeColumnToContents(3)
        self.preview_tree.resizeColumnToContents(4)
        self.preview_tree.resizeColumnToContents(5)
        request = plan.request
        self.preview_state_label.setText("План готов")
        if request.mode is ExportMode.JOIN and self._project_state is None:
            self._visual_preview_current = True
            self.visual_preview_state_label.setText("Отключён в режиме Join")
            self.visual_preview_label.setText("Join не добавляет подпись даты")
            self.preview_button.setEnabled(False)
        else:
            self.visual_preview_state_label.setText("Требуется предпросмотр")
            self.visual_preview_label.setText("Обновите кадр перед экспортом")
            self.preview_button.setEnabled(True)
        self._update_plan_summary(plan)
        self._update_action_states()

    def _update_plan_summary(self, plan: ExportPlan) -> None:
        request = plan.request
        self.plan_summary_label.setText(
            f"Режим: {request.mode.value} | Вход: {request.input_dir} | Выход: {request.output} | "
            f"принято: {len(plan.items)}, пропущено: {len(plan.inspection_failures)} | "
            f"CRF {request.crf}, preset {request.preset} | "
            "overwrite: только после отдельного подтверждения"
        )

    @staticmethod
    def _thumbnail_placeholder(*, failed: bool = False) -> QPixmap:
        pixmap = QPixmap(160, 90)
        pixmap.fill(QColor("#eadfdd" if failed else "#dce8e8"))
        painter = QPainter(pixmap)
        painter.setPen(QColor("#7b4942" if failed else "#476363"))
        painter.drawText(
            pixmap.rect(),
            Qt.AlignmentFlag.AlignCenter,
            "Кадр\nнедоступен" if failed else "Кадр\nготовится…",
        )
        painter.end()
        return pixmap

    @Slot(object)
    def _on_thumbnails_ready(self, batch_value: object) -> None:
        if not isinstance(batch_value, ThumbnailBatch):
            return
        self._thumbnail_failures = dict(batch_value.failures)
        for item_id, path in batch_value.images:
            pixmap = QPixmap(str(path))
            if pixmap.isNull():
                self._thumbnail_failures[item_id] = "PNG не удалось загрузить."
                continue
            self._thumbnail_pixmaps[item_id] = pixmap.copy()
        if self._plan is not None:
            self._populate_preview(self._plan)

    def _start_thumbnail_generation(self) -> None:
        if self._legacy_mode or self._plan is None or self._adapter.is_running:
            return
        self.status_label.setText("Создание миниатюр…")
        self._set_running(True)
        try:
            assert isinstance(self._adapter, ApplicationServiceAdapter)
            self._adapter.start_thumbnails(self._plan)
        except RuntimeError as exc:
            self._on_application_completed("thumbnails", False, str(exc))

    @Slot(str, bool, str)
    def _on_application_completed(
        self, operation: str, success: bool, message: str
    ) -> None:
        progress_snapshot = (
            self.progress.minimum(),
            self.progress.maximum(),
            self.progress.value(),
        )
        self._set_running(False)
        self.result_label.setText(message)
        self._append_output(f"\n{message}\n")
        if operation == "analysis":
            terminal_state = (
                self._adapter.last_terminal_state
                if isinstance(self._adapter, ApplicationServiceAdapter)
                else None
            )
            if success and self._plan is not None:
                if self._plan.request.mode is ExportMode.JOIN:
                    self.status_label.setText("План Join готов к экспорту")
                    self.run_button.setEnabled(True)
                    self.preview_button.setEnabled(False)
                else:
                    self.status_label.setText("План готов — обновите предпросмотр")
                    self.run_button.setEnabled(False)
                    self.preview_button.setEnabled(True)
                self.progress.setValue(1)
                self._start_thumbnail_generation()
                return
            self._plan = None
            self.run_button.setEnabled(False)
            self.progress.setValue(0)
            if terminal_state == "cancelled":
                self.preview_state_label.setText("Анализ остановлен")
                self.plan_summary_label.setText("Частичный план отброшен.")
                self.status_label.setText("Анализ остановлен")
            elif "no supported videos or photos found" in message:
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

        if operation == "thumbnails":
            self.status_label.setText(
                "Миниатюры готовы" if success else "Миниатюры недоступны"
            )
            self.progress.setRange(0, 1)
            self.progress.setValue(1 if success else 0)
            if (
                success
                and self._plan is not None
                and self._selected_mode() is not ExportMode.JOIN
            ):
                self._start_visual_preview()
                return
            self.run_button.setEnabled(
                self._plan is not None
            )
            self.preview_button.setEnabled(
                self._plan is not None
                and self._selected_mode() is not ExportMode.JOIN
            )
            return

        if operation == "preview":
            self.preview_button.setEnabled(self._plan is not None)
            if success and self._visual_preview_current:
                self.visual_preview_state_label.setText(
                    "Подпись выключена" if not self._plan.request.overlay.enabled else "Готов"
                )
                self.status_label.setText("План и предпросмотр готовы к экспорту")
                self.run_button.setEnabled(True)
                self.progress.setValue(1)
            else:
                self._visual_preview_current = False
                self.visual_preview_state_label.setText("Ошибка предпросмотра")
                self.visual_preview_label.setText(message)
                self.status_label.setText("Предпросмотр не обновлён")
                self.run_button.setEnabled(self._plan is not None)
                self.progress.setValue(0)
            return

        if operation == "cache-purge":
            self.status_label.setText("Кэш очищен" if success else "Не удалось очистить кэш")
            self.progress.setRange(0, 1)
            self.progress.setValue(1 if success else 0)
            return

        if operation in {"project-save", "project-open", "project-rollback"}:
            self.status_label.setText(
                "Проект сохранён/открыт" if success else "Ошибка проекта"
            )
            self.progress.setRange(0, 1)
            self.progress.setValue(1 if success else 0)
            self.run_button.setEnabled(
                self._plan is not None
            )
            return

        terminal_state = (
            self._adapter.last_terminal_state
            if isinstance(self._adapter, ApplicationServiceAdapter)
            else None
        )
        if terminal_state == "cancelled":
            self.status_label.setText("Экспорт отменён")
        elif terminal_state == "failed":
            self.status_label.setText("Ошибка экспорта")
        else:
            self.status_label.setText(
                "Экспорт завершён" if success else "Экспорт не выполнен"
            )
        if success:
            self.progress.setRange(0, 1)
            self.progress.setValue(1)
        else:
            self.progress.setRange(progress_snapshot[0], progress_snapshot[1])
            self.progress.setValue(progress_snapshot[2])
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
        if self._adapter.is_running:
            return
        # Re-check the watched source set immediately before export so a file
        # change cannot race the passive QFileSystemWatcher notification.
        if not self._check_source_freshness() or self._plan is None:
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
            raw_cache_dir = self.cache_dir_edit.text().strip()
            cache_enabled = self.cache_enabled.isChecked()
            self._adapter.start_export(
                self._plan,
                overwrite=overwrite,
                cache_enabled=cache_enabled,
                cache_dir=(
                    Path(raw_cache_dir).expanduser()
                    if cache_enabled and raw_cache_dir
                    else None
                ),
            )
        except RuntimeError as exc:
            self._on_application_completed("export", False, str(exc))

    @Slot()
    def _start_visual_preview(self) -> None:
        if self._legacy_mode or self._adapter.is_running or self._plan is None:
            return
        try:
            overlay = self._form_overlay_config(resolve_fallback=True)
        except RequestValidationError as exc:
            self.visual_preview_state_label.setText("Ошибка параметров подписи")
            self.visual_preview_label.setText(str(exc))
            self.run_button.setEnabled(self._plan is not None)
            return
        if self._plan.project_snapshot is None:
            self._plan = replace_plan_overlay(self._plan, overlay)
        elif overlay != self._plan.request.overlay:
            self.visual_preview_state_label.setText("Preset проекта изменился")
            self.run_button.setEnabled(self._plan is not None)
            return
        self._visual_preview_current = False
        self.visual_preview_state_label.setText("Загрузка…")
        self.visual_preview_label.setText("FFmpeg создаёт representative frame…")
        self._set_running(True)
        try:
            assert isinstance(self._adapter, ApplicationServiceAdapter)
            self._adapter.start_preview(self._plan)
        except RuntimeError as exc:
            self._on_application_completed("preview", False, str(exc))

    @Slot(object)
    def _on_visual_preview_ready(self, path_value: object) -> None:
        if not isinstance(path_value, Path):
            return
        try:
            pixmap = QPixmap(str(path_value))
            if pixmap.isNull():
                self._visual_preview_current = False
                self.visual_preview_label.setText("Не удалось загрузить PNG preview.")
                return
            self.visual_preview_label.setPixmap(
                pixmap.scaled(
                    640,
                    360,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            self._visual_preview_current = True
        finally:
            path_value.unlink(missing_ok=True)

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
        is_join = self._selected_mode() is ExportMode.JOIN
        self.overlay_group.setEnabled(
            not running and not self._legacy_mode and not is_join
        )
        self.analyze_button.setEnabled(not running)
        self.preview_button.setEnabled(
            not running
            and not self._legacy_mode
            and not is_join
            and self._plan is not None
        )
        if self._legacy_mode:
            self.run_button.setEnabled(not running)
        else:
            self.run_button.setEnabled(
                not running
                and self._plan is not None
            )
        if running:
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, 1)
            self.progress.setTextVisible(False)
        if not running:
            self.analysis_cancel_button.setEnabled(False)
            self.analysis_cancel_button.setVisible(False)
            self.cancel_button.setEnabled(False)
            self.cancel_button.setVisible(False)
        self._update_action_states()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt API
        if (
            self._tool_setup_process is not None
            and self._tool_setup_process.state() != QProcess.ProcessState.NotRunning
        ):
            QMessageBox.warning(
                self,
                "Установка FFmpeg ещё выполняется",
                "Дождитесь завершения автоматической установки FFmpeg.",
            )
            event.ignore()
            return
        if self._adapter.is_running:
            QMessageBox.warning(
                self,
                "Операция ещё выполняется",
                "Дождитесь завершения операции или используйте доступную кнопку остановки.",
            )
            event.ignore()
            return
        event.accept()


STYLE_SHEET = """
QWidget#central { background: #f4f7f8; color: #182528; }
QWidget#mainViewport { background: #f4f7f8; }
QWidget#mainSettingsTab,
QWidget#timelineTab,
QWidget#timelineViewport,
QFrame#timelineContent,
QFrame#logPanel {
    background: #ffffff;
    color: #182528;
    border: 0;
}
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
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTreeWidget, QListWidget {
    background: #ffffff;
    color: #182528;
    border: 1px solid #cbd9da;
    border-radius: 6px;
    padding: 7px 9px;
    selection-background-color: #2f918d;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QPlainTextEdit:focus, QTreeWidget:focus, QListWidget:focus {
    border: 1px solid #278b87;
}
QPushButton {
    background: #e7efef;
    color: #233b3f;
    border: 1px solid transparent;
    border-radius: 7px;
    padding: 8px 14px;
    font-weight: 600;
}
QPushButton:hover { background: #dce9e9; }
QPushButton:focus { border-color: #278b87; }
QPushButton:disabled { color: #8d9b9d; background: #edf1f1; border-color: transparent; }
QPushButton#primary { background: #176f6b; border-color: #176f6b; color: white; padding: 9px 20px; }
QPushButton#primary:hover { background: #0f5f5b; }
QPushButton#primary:disabled { color: #8d9b9d; background: #edf1f1; border-color: transparent; }
QComboBox QAbstractItemView { background: #ffffff; color: #182528; selection-background-color: #2f918d; }
QCheckBox { color: #233b3f; spacing: 8px; }
QTabWidget::pane { background: #ffffff; border: 1px solid #d5e1e2; border-radius: 8px; top: -1px; }
QTabBar::tab { background: #e7efef; color: #40575b; padding: 8px 16px; margin-right: 2px; }
QTabBar::tab:selected { background: #ffffff; color: #176f6b; font-weight: 700; }
QTreeWidget { alternate-background-color: #f5f9f9; }
QListWidget#thumbnailList { padding: 8px; }
QListWidget#thumbnailList::item {
    background: #f5f9f9;
    color: #233b3f;
    border: 1px solid transparent;
    border-radius: 7px;
    padding: 6px;
}
QListWidget#thumbnailList::item:selected {
    background: #d5ebea;
    color: #174e4b;
    border-color: #278b87;
}
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
    QTimer.singleShot(0, window.ensure_encoding_tools)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
