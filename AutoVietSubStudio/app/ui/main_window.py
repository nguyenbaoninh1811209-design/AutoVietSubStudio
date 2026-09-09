from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QThread, QObject, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.models import Project, ProjectStore
from app.core.pipeline import Pipeline, STEPS, render_video
from app.core.settings import SettingsStore
from app.core.srt import (
    parse_srt,
    validate_srt_lines,
    write_srt,
)
from app.core.translation import (
    LANGUAGE_NAMES,
    TranslationContext,
    TranslationEngine,
    TranslationProgress,
    language_display_name,
)
from app.providers.openai_provider import (
    OpenAITranslationProvider,
)


class TranslationWorker(QObject):
    progress = Signal(object)
    completed = Signal(list)
    failed = Signal(str)

    def __init__(
        self,
        provider,
        lines,
        context,
        batch_size: int,
        max_retries: int,
    ):
        super().__init__()
        self.provider = provider
        self.lines = lines
        self.context = context
        self.batch_size = batch_size
        self.max_retries = max_retries

    def run(self) -> None:
        try:
            engine = TranslationEngine(
                self.provider,
                progress_callback=self.progress.emit,
            )

            failures = engine.translate_lines(
                self.lines,
                self.context,
                batch_size=self.batch_size,
                max_retries=self.max_retries,
            )

            self.completed.emit(failures)

        except Exception as exc:
            self.failed.emit(str(exc))


class LanguageDetectionWorker(QObject):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, provider, lines):
        super().__init__()
        self.provider = provider
        self.lines = lines

    def run(self) -> None:
        try:
            engine = TranslationEngine(self.provider)

            result = engine.detect_language(
                self.lines
            )

            self.completed.emit(result)

        except Exception as exc:
            self.failed.emit(str(exc))


class RenderWorker(QObject):
    completed = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        input_path: str,
        output_path: str,
        aspect_ratio: str,
    ):
        super().__init__()
        self.input_path = input_path
        self.output_path = output_path
        self.aspect_ratio = aspect_ratio

    def run(self) -> None:
        try:
            render_video(
                self.input_path,
                self.output_path,
                aspect_ratio=self.aspect_ratio,
            )

            self.completed.emit(
                self.output_path
            )

        except Exception as exc:
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(
        self,
        data_dir: Path,
    ):
        super().__init__()

        self.setWindowTitle(
            "AutoVietSub Studio"
        )
        self.resize(
            1280,
            820,
        )

        self.data_dir = Path(
            data_dir
        )

        self.store = ProjectStore(
            self.data_dir / "projects"
        )

        self.settings_store = SettingsStore(
            self.data_dir / "settings.json"
        )

        self.settings = (
            self.settings_store.load()
        )

        self.project = Project.new()

        self.logger = logging.getLogger(
            "autovietsub"
        )

        self.translation_thread = None
        self.translation_worker = None

        self.language_thread = None
        self.language_worker = None

        self.render_thread = None
        self.render_worker = None

        self._build()

        self._load_settings()

        self._start_autosave()

    # ============================================================
    # BUILD UI
    # ============================================================

    def _build(self) -> None:
        central = QWidget()
        root = QVBoxLayout(
            central
        )

        header = QHBoxLayout()

        title = QLabel(
            "<h2>AutoVietSub Studio</h2>"
        )

        header.addWidget(title)
        header.addStretch()

        header.addWidget(
            QLabel("Mode")
        )

        self.mode = QComboBox()

        self.mode.addItems(
            [
                "Simple",
                "Advanced",
            ]
        )

        header.addWidget(
            self.mode
        )

        root.addLayout(
            header
        )

        self.tabs = QTabWidget()

        root.addWidget(
            self.tabs
        )

        self.dashboard = QWidget()
        self.projects = QWidget()
        self.subtitle = QWidget()
        self.translation = QWidget()
        self.voice = QWidget()
        self.video = QWidget()
        self.settings_tab = QWidget()
        self.help = QWidget()
        self.logs = QWidget()

        pages = [
            (
                self.dashboard,
                "Dashboard",
            ),
            (
                self.projects,
                "Dự án",
            ),
            (
                self.subtitle,
                "Subtitle",
            ),
            (
                self.translation,
                "Dịch",
            ),
            (
                self.voice,
                "Giọng đọc",
            ),
            (
                self.video,
                "Video",
            ),
            (
                self.settings_tab,
                "Settings",
            ),
            (
                self.help,
                "Hướng dẫn",
            ),
            (
                self.logs,
                "Logs",
            ),
        ]

        for page, name in pages:
            self.tabs.addTab(
                page,
                name,
            )

        self._build_dashboard()
        self._build_projects()
        self._build_subtitle()
        self._build_translation()
        self._build_voice()
        self._build_video()
        self._build_settings()
        self._build_help()
        self._build_logs()

        self.setCentralWidget(
            central
        )

        self._build_menu()

        self.setStyleSheet(
            self._qss()
        )

    # ============================================================
    # MENU
    # ============================================================

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu(
            "File"
        )

        new_action = QAction(
            "Dự án mới",
            self,
        )
        new_action.triggered.connect(
            self._new_project
        )

        file_menu.addAction(
            new_action
        )

        open_action = QAction(
            "Mở project",
            self,
        )
        open_action.triggered.connect(
            self._open_project
        )

        file_menu.addAction(
            open_action
        )

        save_action = QAction(
            "Lưu project",
            self,
        )
        save_action.triggered.connect(
            self.project_store_save
        )

        file_menu.addAction(
            save_action
        )

    # ============================================================
    # DASHBOARD
    # ============================================================

    def _build_dashboard(self) -> None:
        layout = QVBoxLayout(
            self.dashboard
        )

        layout.addWidget(
            QLabel(
                "<h3>Quy trình tự động</h3>"
            )
        )

        self.video_label = QLabel(
            "Chưa chọn video"
        )

        self.video_label.setWordWrap(
            True
        )

        layout.addWidget(
            self.video_label
        )

        select_button = QPushButton(
            "📁 Chọn video"
        )

        select_button.clicked.connect(
            self._choose_video
        )

        layout.addWidget(
            select_button
        )

        self.pipeline_progress = (
            QProgressBar()
        )

        self.pipeline_progress.setRange(
            0,
            len(STEPS),
        )

        self.pipeline_progress.setValue(
            0
        )

        layout.addWidget(
            self.pipeline_progress
        )

        self.pipeline_info = QLabel(
            "Sẵn sàng"
        )

        self.pipeline_info.setWordWrap(
            True
        )

        layout.addWidget(
            self.pipeline_info
        )

        run_button = QPushButton(
            "▶ Chạy pipeline"
        )

        run_button.clicked.connect(
            self._run_pipeline
        )

        layout.addWidget(
            run_button
        )

        layout.addStretch()

    # ============================================================
    # PROJECTS
    # ============================================================

    def _build_projects(self) -> None:
        layout = QVBoxLayout(
            self.projects
        )

        row = QHBoxLayout()

        new_button = QPushButton(
            "＋ Dự án mới"
        )

        new_button.clicked.connect(
            self._new_project
        )

        row.addWidget(
            new_button
        )

        open_button = QPushButton(
            "Mở project"
        )

        open_button.clicked.connect(
            self._open_project
        )

        row.addWidget(
            open_button
        )

        save_button = QPushButton(
            "💾 Lưu"
        )

        save_button.clicked.connect(
            self.project_store_save
        )

        row.addWidget(
            save_button
        )

        row.addStretch()

        layout.addLayout(
            row
        )

        self.project_list = (
            QPlainTextEdit()
        )

        self.project_list.setReadOnly(
            True
        )

        layout.addWidget(
            self.project_list
        )

        self._update_project_info()

    # ============================================================
    # SUBTITLE
    # ============================================================

    def _build_subtitle(self) -> None:
        layout = QVBoxLayout(
            self.subtitle
        )

        row = QHBoxLayout()

        import_button = QPushButton(
            "Nạp SRT"
        )

        import_button.clicked.connect(
            self._import_srt
        )

        row.addWidget(
            import_button
        )

        export_button = QPushButton(
            "Xuất SRT"
        )

        export_button.clicked.connect(
            self._export_srt
        )

        row.addWidget(
            export_button
        )

        validate_button = QPushButton(
            "✅ Kiểm tra SRT"
        )

        validate_button.clicked.connect(
            self._validate_srt
        )

        row.addWidget(
            validate_button
        )

        row.addStretch()

        layout.addLayout(
            row
        )

        self.table = QTableWidget(
            0,
            6,
        )

        self.table.setHorizontalHeaderLabels(
            [
                "#",
                "Start",
                "End",
                "Original",
                "Translated",
                "Status",
            ]
        )

        self.table.horizontalHeader().setStretchLastSection(
            True
        )

        layout.addWidget(
            self.table
        )

    # ============================================================
    # TRANSLATION
    # ============================================================

    def _build_translation(self) -> None:
        layout = QVBoxLayout(
            self.translation
        )

        form = QFormLayout()

        self.source_language = (
            QComboBox()
        )

        self.source_language.addItem(
            "Tự động nhận diện",
            "auto",
        )

        for code, name in LANGUAGE_NAMES.items():
            if code == "auto":
                continue

            self.source_language.addItem(
                name,
                code,
            )

        form.addRow(
            "Ngôn ngữ nguồn",
            self.source_language,
        )

        self.detected_language = QLabel(
            "Chưa nhận diện"
        )

        form.addRow(
            "Đã nhận diện",
            self.detected_language,
        )

        self.target_language = (
            QComboBox()
        )

        self.target_language.addItem(
            "Tiếng Việt",
            "vi",
        )

        self.target_language.addItem(
            "Tiếng Anh",
            "en",
        )

        form.addRow(
            "Ngôn ngữ đích",
            self.target_language,
        )

        self.trans_mode = QComboBox()

        self.trans_mode.addItems(
            [
                "Bình thường",
                "Hài hước",
                "Ngôn tình",
                "Tu tiên / huyền huyễn",
                "Trung thành nguyên tác",
            ]
        )

        form.addRow(
            "Chế độ dịch",
            self.trans_mode,
        )

        self.context = QLineEdit()

        self.context.setPlaceholderText(
            "Ví dụ: phim tu tiên, giữ nguyên tên nhân vật"
        )

        form.addRow(
            "Ngữ cảnh",
            self.context,
        )

        self.batch_size = QSpinBox()

        self.batch_size.setRange(
            1,
            100,
        )

        self.batch_size.setValue(
            10
        )

        form.addRow(
            "Batch",
            self.batch_size,
        )

        self.max_retries = QSpinBox()

        self.max_retries.setRange(
            0,
            10,
        )

        self.max_retries.setValue(
            2
        )

        form.addRow(
            "Retry / dòng",
            self.max_retries,
        )

        layout.addLayout(
            form
        )

        buttons = QHBoxLayout()

        detect_button = QPushButton(
            "🌐 Tự động nhận diện"
        )

        detect_button.clicked.connect(
            self._detect_language
        )

        buttons.addWidget(
            detect_button
        )

        translate_button = QPushButton(
            "🤖 Dịch toàn bộ"
        )

        translate_button.clicked.connect(
            self._translate
        )

        buttons.addWidget(
            translate_button
        )

        buttons.addStretch()

        layout.addLayout(
            buttons
        )

        self.translation_progress = (
            QProgressBar()
        )

        self.translation_progress.setRange(
            0,
            100,
        )

        layout.addWidget(
            self.translation_progress
        )

        self.trans_status = QLabel(
            "Chưa chạy"
        )

        self.trans_status.setWordWrap(
            True
        )

        layout.addWidget(
            self.trans_status
        )

        self.translation_failures = (
            QPlainTextEdit()
        )

        self.translation_failures.setReadOnly(
            True
        )

        self.translation_failures.setPlaceholderText(
            "Dòng dịch lỗi sẽ hiển thị ở đây."
        )

        layout.addWidget(
            self.translation_failures
        )

    # ============================================================
    # TTS
    # ============================================================

    def _build_voice(self) -> None:
        layout = QVBoxLayout(
            self.voice
        )

        layout.addWidget(
            QLabel(
                "<h3>Giọng đọc / TTS</h3>"
            )
        )

        self.voice_provider = (
            QComboBox()
        )

        self.voice_provider.addItems(
            [
                "None",
                "Local TTS",
                "Official API provider",
            ]
        )

        layout.addWidget(
            self.voice_provider
        )

        self.voice_name = QLineEdit()

        self.voice_name.setPlaceholderText(
            "Tên giọng của provider"
        )

        layout.addWidget(
            self.voice_name
        )

        preview_button = QPushButton(
            "▶ Nghe thử"
        )

        preview_button.clicked.connect(
            self._voice_preview
        )

        layout.addWidget(
            preview_button
        )

        layout.addWidget(
            QLabel(
                "TTS cần provider/SDK/API hợp lệ."
            )
        )

        layout.addStretch()

    # ============================================================
    # VIDEO
    # ============================================================

    def _build_video(self) -> None:
        layout = QVBoxLayout(
            self.video
        )

        form = QFormLayout()

        self.aspect = QComboBox()

        self.aspect.addItems(
            [
                "16:9",
                "9:16",
                "1:1",
                "4:5",
                "4:3",
            ]
        )

        form.addRow(
            "Tỷ lệ xuất",
            self.aspect,
        )

        self.performance = QComboBox()

        self.performance.addItems(
            [
                "Light",
                "Balanced",
                "Strong",
            ]
        )

        form.addRow(
            "Công suất",
            self.performance,
        )

        self.blur = QCheckBox(
            "Bật vùng làm mờ"
        )

        form.addRow(
            "Blur",
            self.blur,
        )

        layout.addLayout(
            form
        )

        render_button = QPushButton(
            "🎬 Render / Export"
        )

        render_button.clicked.connect(
            self._render_video
        )

        layout.addWidget(
            render_button
        )

        self.render_status = QLabel(
            "Chưa render"
        )

        self.render_status.setWordWrap(
            True
        )

        layout.addWidget(
            self.render_status
        )

        layout.addStretch()

    # ============================================================
    # SETTINGS
    # ============================================================

    def _build_settings(self) -> None:
        layout = QVBoxLayout(
            self.settings_tab
        )

        form = QFormLayout()

        self.lang = QComboBox()

        self.lang.addItems(
            [
                "vi",
                "en",
            ]
        )

        form.addRow(
            "Language",
            self.lang,
        )

        self.data_path = QLineEdit(
            str(self.data_dir)
        )

        browse_button = QPushButton(
            "Chọn"
        )

        browse_button.clicked.connect(
            self._choose_data
        )

        data_row = QHBoxLayout()

        data_row.addWidget(
            self.data_path
        )

        data_row.addWidget(
            browse_button
        )

        data_box = QWidget()
        data_box.setLayout(
            data_row
        )

        form.addRow(
            "Data folder",
            data_box,
        )

        self.api_key = QLineEdit(
            self.settings.get(
                "openai_api_key",
                "",
            )
        )

        self.api_key.setEchoMode(
            QLineEdit.Password
        )

        form.addRow(
            "OpenAI API key",
            self.api_key,
        )

        self.model = QLineEdit(
            self.settings.get(
                "translation_model",
                "gpt-5-mini",
            )
        )

        form.addRow(
            "Translation model",
            self.model,
        )

        layout.addLayout(
            form
        )

        save_button = QPushButton(
            "Lưu Settings"
        )

        save_button.clicked.connect(
            self._save_settings
        )

        layout.addWidget(
            save_button
        )

        layout.addWidget(
            QLabel(
                "Sử dụng API chính thức. "
                "Không điều khiển ChatGPT Web bằng cookie/session."
            )
        )

        layout.addStretch()

    # ============================================================
    # HELP
    # ============================================================

    def _build_help(self) -> None:
        layout = QVBoxLayout(
            self.help
        )

        text = QPlainTextEdit()

        text.setReadOnly(
            True
        )

        text.setPlainText(
            """QUY TRÌNH NHANH

1. Dự án mới → chọn video.
2. Subtitle → Nạp SRT.
3. Dịch → tự nhận diện ngôn ngữ hoặc chọn thủ công.
4. Dịch sang ngôn ngữ đích.
5. Kiểm tra subtitle.
6. Chọn provider TTS.
7. Chọn tỷ lệ video.
8. Render / Export.

TÍNH NĂNG

- Tự động nhận diện ngôn ngữ.
- Dịch theo batch.
- Retry từng dòng.
- Báo dòng dịch lỗi.
- Giữ nguyên timestamp SRT.
- Autosave project.
- Checkpoint pipeline.
- Khôi phục project từ backup.
- Render video bằng FFmpeg.

LƯU Ý

- Provider/model không khả dụng phải báo lỗi.
- Không dùng cookie/session để điều khiển ChatGPT Web.
- TTS độc quyền chỉ tích hợp bằng API/SDK/quyền hợp pháp.
"""
        )

        layout.addWidget(
            text
        )

    # ============================================================
    # LOGS
    # ============================================================

    def _build_logs(self) -> None:
        layout = QVBoxLayout(
            self.logs
        )

        self.log_view = (
            QPlainTextEdit()
        )

        self.log_view.setReadOnly(
            True
        )

        layout.addWidget(
            self.log_view
        )

    # ============================================================
    # SETTINGS LOAD
    # ============================================================

    def _load_settings(self) -> None:
        self.mode.setCurrentText(
            self.settings.get(
                "ui_mode",
                "Simple",
            )
        )

        self.lang.setCurrentText(
            self.settings.get(
                "language",
                "vi",
            )
        )

        self.data_path.setText(
            self.settings.get(
                "data_root",
                str(self.data_dir),
            )
        )

        self.trans_mode.setCurrentText(
            self.settings.get(
                "translation_mode",
                "Bình thường",
            )
        )

        self.performance.setCurrentText(
            self.settings.get(
                "performance_mode",
                "Balanced",
            )
        )

        self.model.setText(
            self.settings.get(
                "translation_model",
                "gpt-5-mini",
            )
        )

    def _start_autosave(self) -> None:
        from PySide6.QtCore import QTimer

        self.autosave_timer = QTimer(
            self
        )

        self.autosave_timer.setInterval(
            1500
        )

        self.autosave_timer.timeout.connect(
            self._save_quiet
        )

        self.autosave_timer.start()

    # ============================================================
    # PROJECT
    # ============================================================

    def _update_project_info(self) -> None:
        self.project_list.setPlainText(
            f"Project hiện tại: {self.project.name}\n"
            f"Video: {self.project.video_path or 'chưa chọn'}\n"
            f"Subtitle: {len(self.project.subtitles)} dòng"
        )

    def _new_project(self) -> None:
        self.project = Project.new()

        self.table.setRowCount(
            0
        )

        self.video_label.setText(
            "Chưa chọn video"
        )

        self.detected_language.setText(
            "Chưa nhận diện"
        )

        self.trans_status.setText(
            "Chưa chạy"
        )

        self.translation_failures.clear()

        self.translation_progress.setValue(
            0
        )

        self.pipeline_progress.setValue(
            0
        )

        self.pipeline_info.setText(
            "Sẵn sàng"
        )

        self.render_status.setText(
            "Chưa render"
        )

        self._update_project_info()

    def _open_project(self) -> None:
        path, _ = (
            QFileDialog.getOpenFileName(
                self,
                "Mở project",
                str(
                    self.data_dir
                    / "projects"
                ),
                "Project (*.json)",
            )
        )

        if not path:
            return

        try:
            self.project = (
                self.store.load(
                    Path(path)
                )
            )

            self._refresh_table()

            self.video_label.setText(
                self.project.video_path
                or "Chưa chọn video"
            )

            self._update_project_info()

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Lỗi mở project",
                str(exc),
            )

    # ============================================================
    # VIDEO SELECT
    # ============================================================

    def _choose_video(self) -> None:
        path, _ = (
            QFileDialog.getOpenFileName(
                self,
                "Chọn video",
                "",
                (
                    "Video "
                    "(*.mp4 *.mkv *.mov *.avi "
                    "*.webm *.m4v)"
                ),
            )
        )

        if not path:
            return

        self.project.video_path = path

        self.video_label.setText(
            path
        )

        self.project.checkpoints[
            "Analyze"
        ] = False

        self.project.checkpoints[
            "Video"
        ] = False

        self.project.checkpoints[
            "Render"
        ] = False

        self.project.checkpoints[
            "Validate Output"
        ] = False

        self._update_project_info()

        self.project_store_save()

    # ============================================================
    # SRT
    # ============================================================

    def _import_srt(self) -> None:
        path, _ = (
            QFileDialog.getOpenFileName(
                self,
                "Nạp SRT",
                "",
                "Subtitle (*.srt)",
            )
        )

        if not path:
            return

        try:
            text = Path(
                path
            ).read_text(
                encoding="utf-8-sig"
            )

            lines = parse_srt(
                text
            )

            if not lines:
                raise ValueError(
                    "Không tìm thấy subtitle hợp lệ."
                )

            self.project.subtitle_path = (
                path
            )

            self.project.subtitles = (
                lines
            )

            self.project.checkpoints[
                "Subtitle"
            ] = True

            self.project.checkpoints[
                "Translate"
            ] = False

            self.project.checkpoints[
                "Validate"
            ] = False

            self.project.checkpoints[
                "TTS"
            ] = False

            self.project.checkpoints[
                "Sync"
            ] = False

            self.project.checkpoints[
                "Render"
            ] = False

            self.project.checkpoints[
                "Validate Output"
            ] = False

            self._refresh_table()

            self._update_project_info()

            self.trans_status.setText(
                f"Đã nạp {len(lines)} dòng subtitle."
            )

            self.translation_progress.setValue(
                0
            )

            self.project_store_save()

        except Exception as exc:
            QMessageBox.critical(
                self,
                "SRT lỗi",
                str(exc),
            )

    def _export_srt(self) -> None:
        if not self.project.subtitles:
            QMessageBox.warning(
                self,
                "Thiếu subtitle",
                "Chưa có subtitle để xuất.",
            )
            return

        path, _ = (
            QFileDialog.getSaveFileName(
                self,
                "Xuất SRT",
                "translated.srt",
                "Subtitle (*.srt)",
            )
        )

        if not path:
            return

        try:
            output = write_srt(
                self.project.subtitles,
                True,
            )

            Path(path).write_text(
                output,
                encoding="utf-8",
            )

            self.trans_status.setText(
                f"Đã xuất SRT: {path}"
            )

        except OSError as exc:
            QMessageBox.critical(
                self,
                "Lỗi xuất SRT",
                str(exc),
            )

    def _refresh_table(self) -> None:
        self.table.setRowCount(
            len(
                self.project.subtitles
            )
        )

        for row, subtitle in enumerate(
            self.project.subtitles
        ):
            values = [
                str(subtitle.index),
                (
                    f"{subtitle.start_ms / 1000:.3f}"
                ),
                (
                    f"{subtitle.end_ms / 1000:.3f}"
                ),
                subtitle.original,
                subtitle.translated,
                subtitle.status,
            ]

            for column, value in enumerate(
                values
            ):
                self.table.setItem(
                    row,
                    column,
                    QTableWidgetItem(
                        value
                    ),
                )

    def _validate_srt(self) -> None:
        ok, bad = validate_srt_lines(
            self.project.subtitles
        )

        if ok:
            self.project.checkpoints[
                "Validate"
            ] = True

            self.trans_status.setText(
                "✅ SRT hợp lệ."
            )

        else:
            self.project.checkpoints[
                "Validate"
            ] = False

            self.trans_status.setText(
                "❌ SRT lỗi ở vị trí: "
                + ", ".join(
                    map(
                        str,
                        bad[:50],
                    )
                )
            )

        self.project_store_save()

    # ============================================================
    # TRANSLATION PROVIDER
    # ============================================================

    def _provider(
        self,
    ) -> OpenAITranslationProvider:
        return OpenAITranslationProvider(
            api_key=(
                self.settings.get(
                    "openai_api_key"
                )
                or None
            ),
            model=self.settings.get(
                "translation_model",
                "gpt-5-mini",
            ),
        )

    # ============================================================
    # LANGUAGE DETECTION
    # ============================================================

    def _detect_language(self) -> None:
        if not self.project.subtitles:
            QMessageBox.warning(
                self,
                "Thiếu subtitle",
                "Hãy nạp subtitle trước.",
            )
            return

        if self.language_thread is not None:
            QMessageBox.information(
                self,
                "Đang xử lý",
                "Đang có tác vụ nhận diện ngôn ngữ.",
            )
            return

        provider = self._provider()

        if not provider.available():
            QMessageBox.warning(
                self,
                "Chưa có API",
                (
                    "Hãy cấu hình OpenAI API key "
                    "chính thức trong Settings "
                    "hoặc OPENAI_API_KEY."
                ),
            )
            return

        self.trans_status.setText(
            "🌐 Đang nhận diện ngôn ngữ..."
        )

        self.detected_language.setText(
            "Đang nhận diện..."
        )

        self.language_thread = QThread(
            self
        )

        self.language_worker = (
            LanguageDetectionWorker(
                provider,
                self.project.subtitles,
            )
        )

        self.language_worker.moveToThread(
            self.language_thread
        )

        self.language_thread.started.connect(
            self.language_worker.run
        )

        self.language_worker.completed.connect(
            self._language_detected
        )

        self.language_worker.failed.connect(
            self._language_detection_failed
        )

        self.language_worker.completed.connect(
            self.language_thread.quit
        )

        self.language_worker.failed.connect(
            self.language_thread.quit
        )

        self.language_thread.finished.connect(
            self._language_worker_finished
        )

        self.language_thread.start()

    def _language_detected(
        self,
        result,
    ) -> None:
        code = getattr(
            result,
            "language_code",
            "auto",
        )

        name = getattr(
            result,
            "language_name",
            language_display_name(
                code
            ),
        )

        confidence = getattr(
            result,
            "confidence",
            None,
        )

        if confidence is None:
            confidence_text = ""

        else:
            confidence_text = (
                f" — độ tin cậy "
                f"{confidence:.0%}"
            )

        self.detected_language.setText(
            f"{name} ({code})"
            f"{confidence_text}"
        )

        index = (
            self.source_language.findData(
                code
            )
        )

        if index >= 0:
            self.source_language.setCurrentIndex(
                index
            )

        self.project.checkpoints[
            "Analyze"
        ] = True

        self.project_store_save()

        self.trans_status.setText(
            "✅ Nhận diện ngôn ngữ hoàn tất."
        )

    def _language_detection_failed(
        self,
        message: str,
    ) -> None:
        self.detected_language.setText(
            "Nhận diện thất bại"
        )

        self.trans_status.setText(
            f"❌ Lỗi nhận diện: {message}"
        )

    def _language_worker_finished(
        self,
    ) -> None:
        if self.language_worker:
            self.language_worker.deleteLater()

        if self.language_thread:
            self.language_thread.deleteLater()

        self.language_worker = None
        self.language_thread = None

    # ============================================================
    # TRANSLATION
    # ============================================================

    def _translate(self) -> None:
        if not self.project.subtitles:
            QMessageBox.warning(
                self,
                "Thiếu subtitle",
                "Hãy nạp subtitle trước.",
            )
            return

        if self.translation_thread is not None:
            QMessageBox.information(
                self,
                "Đang dịch",
                "Một tác vụ dịch đang chạy.",
            )
            return

        provider = self._provider()

        if not provider.available():
            QMessageBox.warning(
                self,
                "Chưa có API",
                (
                    "Hãy cấu hình OpenAI API key "
                    "chính thức trong Settings "
                    "hoặc OPENAI_API_KEY."
                ),
            )
            return

        source_language = (
            self.source_language.currentData()
            or "auto"
        )

        target_language = (
            self.target_language.currentData()
            or "vi"
        )

        context = TranslationContext(
            source_language=source_language,
            target_language=target_language,
            mode=self.trans_mode.currentText(),
            extra_context=(
                self.context.text().strip()
            ),
        )

        self.translation_progress.setValue(
            0
        )

        self.translation_failures.clear()

        self.trans_status.setText(
            "🤖 Đang dịch..."
        )

        self.translation_thread = QThread(
            self
        )

        self.translation_worker = (
            TranslationWorker(
                provider,
                self.project.subtitles,
                context,
                self.batch_size.value(),
                self.max_retries.value(),
            )
        )

        self.translation_worker.moveToThread(
            self.translation_thread
        )

        self.translation_thread.started.connect(
            self.translation_worker.run
        )

        self.translation_worker.progress.connect(
            self._translation_progress
        )

        self.translation_worker.completed.connect(
            self._translation_completed
        )

        self.translation_worker.failed.connect(
            self._translation_failed
        )

        self.translation_worker.completed.connect(
            self.translation_thread.quit
        )

        self.translation_worker.failed.connect(
            self.translation_thread.quit
        )

        self.translation_thread.finished.connect(
            self._translation_worker_finished
        )

        self.translation_thread.start()

    def _translation_progress(
        self,
        progress: TranslationProgress,
    ) -> None:
        self.translation_progress.setValue(
            int(
                progress.percentage
            )
        )

        self.trans_status.setText(
            progress.message
            or (
                f"Đã xử lý "
                f"{progress.completed}/"
                f"{progress.total} dòng."
            )
        )

        if progress.failed_lines:
            self.translation_failures.setPlainText(
                "Dòng lỗi: "
                + ", ".join(
                    map(
                        str,
                        progress.failed_lines,
                    )
                )
            )

        self._refresh_table()

    def _translation_completed(
        self,
        failures: list[int],
    ) -> None:
        self._refresh_table()

        if failures:
            self.translation_progress.setValue(
                100
            )

            self.project.checkpoints[
                "Translate"
            ] = False

            self.project.checkpoints[
                "Validate"
            ] = False

            self.translation_failures.setPlainText(
                "Dòng dịch lỗi: "
                + ", ".join(
                    map(
                        str,
                        failures,
                    )
                )
            )

            self.trans_status.setText(
                (
                    "⚠️ Hoàn tất nhưng còn "
                    f"{len(failures)} dòng lỗi."
                )
            )

        else:
            self.translation_progress.setValue(
                100
            )

            self.project.checkpoints[
                "Translate"
            ] = True

            ok, bad = validate_srt_lines(
                self.project.subtitles
            )

            self.project.checkpoints[
                "Validate"
            ] = ok

            if ok:
                self.trans_status.setText(
                    "✅ Dịch hoàn tất và "
                    "validator không phát hiện lỗi."
                )

            else:
                self.trans_status.setText(
                    "⚠️ Dịch xong nhưng "
                    "subtitle lỗi ở vị trí: "
                    + ", ".join(
                        map(
                            str,
                            bad[:50],
                        )
                    )
                )

        self.project_store_save()

    def _translation_failed(
        self,
        message: str,
    ) -> None:
        self.trans_status.setText(
            f"❌ Dịch thất bại: {message}"
        )

        self.project.checkpoints[
            "Translate"
        ] = False

        self.project.checkpoints[
            "Validate"
        ] = False

        self.project_store_save()

    def _translation_worker_finished(
        self,
    ) -> None:
        if self.translation_worker:
            self.translation_worker.deleteLater()

        if self.translation_thread:
            self.translation_thread.deleteLater()

        self.translation_worker = None
        self.translation_thread = None

    # ============================================================
    # PIPELINE
    # ============================================================

    def _run_pipeline(self) -> None:
        if not self.project.video_path:
            QMessageBox.warning(
                self,
                "Thiếu video",
                "Hãy chọn video trước.",
            )
            return

        try:
            pipeline = Pipeline(
                self.project,
                logger=self.logger,
            )

            self.pipeline_progress.setValue(
                0
            )

            self.pipeline_info.setText(
                "Đang chạy pipeline..."
            )

            for index, step in pipeline.run():
                if step == "DONE":
                    break

                progress = index + 1

                self.pipeline_progress.setValue(
                    progress
                )

                self.pipeline_info.setText(
                    f"Bước {progress}/"
                    f"{len(STEPS)}: {step}"
                )

                self.logger.info(
                    "Pipeline UI: %s",
                    step,
                )

                if step == "Analyze":
                    success = bool(
                        self.project.video_path
                    )

                    self.project.checkpoints[
                        step
                    ] = success

                elif step == "Subtitle":
                    success = bool(
                        self.project.subtitles
                    )

                    self.project.checkpoints[
                        step
                    ] = success

                elif step == "Translate":
                    success = bool(
                        self.project.subtitles
                    ) and all(
                        bool(
                            line.translated.strip()
                        )
                        for line
                        in self.project.subtitles
                    )

                    self.project.checkpoints[
                        step
                    ] = success

                elif step == "Validate":
                    success, _ = (
                        validate_srt_lines(
                            self.project.subtitles
                        )
                    )

                    self.project.checkpoints[
                        step
                    ] = success

                elif step == "TTS":
                    self.project.checkpoints[
                        step
                    ] = False

                    self.pipeline_info.setText(
                        "TTS chưa có provider thực thi."
                    )

                    break

                elif step == "Sync":
                    self.project.checkpoints[
                        step
                    ] = False

                    break

                elif step == "Video":
                    success = bool(
                        self.project.video_path
                    )

                    self.project.checkpoints[
                        step
                    ] = success

                elif step == "Render":
                    self.project.checkpoints[
                        step
                    ] = False

                    break

                elif step == "Validate Output":
                    self.project.checkpoints[
                        step
                    ] = False

                self.project_store_save()

            completed_count = sum(
                bool(
                    self.project.checkpoints.get(
                        step,
                        False,
                    )
                )
                for step in STEPS
            )

            self.pipeline_progress.setValue(
                completed_count
            )

            self.pipeline_info.setText(
                f"Pipeline: "
                f"{completed_count}/{len(STEPS)} "
                f"bước đã hoàn thành."
            )

        except Exception as exc:
            self.pipeline_info.setText(
                f"❌ Pipeline lỗi: {exc}"
            )

            self.logger.exception(
                "Pipeline failed"
            )

    # ============================================================
    # RENDER
    # ============================================================

    def _render_video(self) -> None:
        if not self.project.video_path:
            QMessageBox.warning(
                self,
                "Thiếu video",
                "Hãy chọn video trước.",
            )
            return

        if self.render_thread is not None:
            QMessageBox.information(
                self,
                "Đang render",
                "Một tác vụ render đang chạy.",
            )
            return

        output_path, _ = (
            QFileDialog.getSaveFileName(
                self,
                "Xuất video",
                str(
                    self.data_dir
                    / "outputs"
                    / "translated_output.mp4"
                ),
                "Video (*.mp4)",
            )
        )

        if not output_path:
            return

        self.render_status.setText(
            "🎬 Đang render..."
        )

        self.render_thread = QThread(
            self
        )

        self.render_worker = RenderWorker(
            self.project.video_path,
            output_path,
            self.aspect.currentText(),
        )

        self.render_worker.moveToThread(
            self.render_thread
        )

        self.render_thread.started.connect(
            self.render_worker.run
        )

        self.render_worker.completed.connect(
            self._render_completed
        )

        self.render_worker.failed.connect(
            self._render_failed
        )

        self.render_worker.completed.connect(
            self.render_thread.quit
        )

        self.render_worker.failed.connect(
            self.render_thread.quit
        )

        self.render_thread.finished.connect(
            self._render_worker_finished
        )

        self.render_thread.start()

    def _render_completed(
        self,
        output_path: str,
    ) -> None:
        self.render_status.setText(
            f"✅ Render xong: {output_path}"
        )

        self.project.checkpoints[
            "Render"
        ] = True

        self.project.checkpoints[
            "Validate Output"
        ] = Path(
            output_path
        ).exists()

        self.project_store_save()

    def _render_failed(
        self,
        message: str,
    ) -> None:
        self.render_status.setText(
            f"❌ Render thất bại: {message}"
        )

        self.project.checkpoints[
            "Render"
        ] = False

        self.project.checkpoints[
            "Validate Output"
        ] = False

        self.project_store_save()

    def _render_worker_finished(
        self,
    ) -> None:
        if self.render_worker:
            self.render_worker.deleteLater()

        if self.render_thread:
            self.render_thread.deleteLater()

        self.render_worker = None
        self.render_thread = None

    # ============================================================
    # TTS
    # ============================================================

    def _voice_preview(self) -> None:
        QMessageBox.information(
            self,
            "TTS",
            (
                "Preview TTS sẽ hoạt động "
                "khi provider/SDK/API chính thức "
                "được tích hợp."
            ),
        )

    # ============================================================
    # SETTINGS
    # ============================================================

    def _choose_data(self) -> None:
        path = (
            QFileDialog.getExistingDirectory(
                self,
                "Chọn data folder",
            )
        )

        if path:
            self.data_path.setText(
                path
            )

    def _save_settings(self) -> None:
        self.settings.update(
            {
                "ui_mode": (
                    self.mode.currentText()
                ),
                "language": (
                    self.lang.currentText()
                ),
                "data_root": (
                    self.data_path.text().strip()
                ),
                "translation_mode": (
                    self.trans_mode.currentText()
                ),
                "performance_mode": (
                    self.performance.currentText()
                ),
                "translation_model": (
                    self.model.text().strip()
                    or "gpt-5-mini"
                ),
                "openai_api_key": (
                    self.api_key.text()
                ),
            }
        )

        self.settings_store.save(
            self.settings
        )

        self.project.settings.translation_mode = (
            self.trans_mode.currentText()
        )

        self.project.settings.performance_mode = (
            self.performance.currentText()
        )

        self.project.settings.aspect_ratio = (
            self.aspect.currentText()
        )

        self.project.settings.voice_provider = (
            self.voice_provider.currentText()
        )

        self.project.settings.voice_name = (
            self.voice_name.text().strip()
        )

        self.project_store_save()

        QMessageBox.information(
            self,
            "Saved",
            "Settings đã được lưu.",
        )

    # ============================================================
    # AUTOSAVE
    # ============================================================

    def _save_quiet(self) -> None:
        try:
            self.project_store_save()

        except Exception as exc:
            self.logger.warning(
                "Autosave failed: %s",
                exc,
            )

    def project_store_save(self) -> None:
        self.store.save(
            self.project
        )

    # ============================================================
    # CLOSE
    # ============================================================

    def closeEvent(
        self,
        event,
    ) -> None:
        try:
            self.project_store_save()

        finally:
            super().closeEvent(
                event
            )

    # ============================================================
    # STYLE
    # ============================================================

    def _qss(self) -> str:
        return """
        QWidget {
            font-size: 14px;
        }

        QTabWidget::pane {
            border: 1px solid #333;
        }

        QTabBar::tab {
            padding: 10px 16px;
        }

        QPushButton {
            padding: 8px 12px;
        }

        QLineEdit,
        QComboBox,
        QPlainTextEdit,
        QTableWidget,
        QSpinBox {
            padding: 5px;
        }

        QTableWidget {
            gridline-color: #444;
        }

        QProgressBar {
            min-height: 20px;
        }
        """
