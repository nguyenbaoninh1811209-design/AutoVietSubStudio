from __future__ import annotations
from pathlib import Path
import logging
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QLineEdit,QComboBox,QTabWidget,
    QTableWidget,QTableWidgetItem,QFileDialog,QMessageBox,QFormLayout,QSpinBox,QGroupBox,QProgressBar,
    QPlainTextEdit,QCheckBox
)
from app.core.models import Project, ProjectStore
from app.core.srt import parse_srt, write_srt
from app.core.settings import SettingsStore
from app.providers.openai_provider import OpenAITranslationProvider
from app.core.translation import TranslationEngine, TranslationContext

class MainWindow(QMainWindow):
    def __init__(self, data_dir: Path):
        super().__init__(); self.setWindowTitle("AutoVietSub Studio"); self.resize(1280,800)
        self.data_dir=data_dir; self.store=ProjectStore(data_dir/'projects'); self.settings_store=SettingsStore(data_dir/'settings.json'); self.settings=self.settings_store.load()
        self.project=Project.new(); self.logger=logging.getLogger('autovietsub'); self._build(); self._autosave=QTimer(self); self._autosave.setInterval(1500); self._autosave.timeout.connect(self._save_quiet); self._autosave.start()
    def _build(self):
        central=QWidget(); root=QVBoxLayout(central)
        header=QHBoxLayout(); title=QLabel("<h2>AutoVietSub Studio</h2>"); header.addWidget(title); header.addStretch()
        self.mode=QComboBox(); self.mode.addItems(["Simple","Advanced"]); header.addWidget(QLabel("Mode")); header.addWidget(self.mode); root.addLayout(header)
        self.tabs=QTabWidget(); root.addWidget(self.tabs)
        self.dashboard=QWidget(); self.projects=QWidget(); self.subtitle=QWidget(); self.translation=QWidget(); self.voice=QWidget(); self.video=QWidget(); self.settings_tab=QWidget(); self.help=QWidget(); self.logs=QWidget()
        for w,n in [(self.dashboard,"Dashboard"),(self.projects,"Dự án"),(self.subtitle,"Subtitle"),(self.translation,"Dịch"),(self.voice,"Giọng đọc"),(self.video,"Video"),(self.settings_tab,"Settings"),(self.help,"Hướng dẫn"),(self.logs,"Logs")]: self.tabs.addTab(w,n)
        self._dashboard(); self._projects(); self._subtitle(); self._translation(); self._voice(); self._video(); self._settings(); self._help(); self._logs(); self.setCentralWidget(central)
        self.setStyleSheet(self._qss())
    def _dashboard(self):
        l=QVBoxLayout(self.dashboard); l.addWidget(QLabel("<h3>Quy trình tự động</h3>")); self.video_label=QLabel("Chưa chọn video"); l.addWidget(self.video_label)
        b=QPushButton("📁 Chọn video"); b.clicked.connect(self._choose_video); l.addWidget(b)
        self.pipeline_progress=QProgressBar(); l.addWidget(self.pipeline_progress)
        self.pipeline_info=QLabel("Sẵn sàng"); l.addWidget(self.pipeline_info); l.addStretch()
    def _projects(self):
        l=QVBoxLayout(self.projects); row=QHBoxLayout()
        new=QPushButton("＋ Dự án mới"); new.clicked.connect(self._new_project); row.addWidget(new)
        op=QPushButton("Mở project"); op.clicked.connect(self._open_project); row.addWidget(op); row.addStretch(); l.addLayout(row)
        self.project_list=QPlainTextEdit(); self.project_list.setReadOnly(True); self.project_list.setPlainText("Project hiện tại: Untitled Project"); l.addWidget(self.project_list)
    def _subtitle(self):
        l=QVBoxLayout(self.subtitle); row=QHBoxLayout(); imp=QPushButton("Nạp SRT"); imp.clicked.connect(self._import_srt); exp=QPushButton("Xuất SRT"); exp.clicked.connect(self._export_srt); row.addWidget(imp); row.addWidget(exp); row.addStretch(); l.addLayout(row)
        self.table=QTableWidget(0,5); self.table.setHorizontalHeaderLabels(["#","Start","End","Original","Translated"]); self.table.horizontalHeader().setStretchLastSection(True); l.addWidget(self.table)
    def _translation(self):
        l=QVBoxLayout(self.translation); form=QFormLayout(); self.trans_mode=QComboBox(); self.trans_mode.addItems(["Bình thường","Hài hước","Ngôn tình","Tu tiên / huyền huyễn","Trung thành nguyên tác"]); form.addRow("Chế độ dịch",self.trans_mode); self.context=QLineEdit(); form.addRow("Ngữ cảnh",self.context); l.addLayout(form)
        b=QPushButton("🤖 Dịch + kiểm tra từng dòng"); b.clicked.connect(self._translate); l.addWidget(b); self.trans_status=QLabel("Chưa chạy"); l.addWidget(self.trans_status); l.addStretch()
    def _voice(self):
        l=QVBoxLayout(self.voice); l.addWidget(QLabel("<h3>Giọng đọc / TTS</h3>")); self.voice_provider=QComboBox(); self.voice_provider.addItems(["None","Local TTS","Official API provider"]); l.addWidget(self.voice_provider); self.voice_name=QLineEdit(); self.voice_name.setPlaceholderText("Tên giọng gốc của provider"); l.addWidget(self.voice_name); l.addWidget(QPushButton("▶ Nghe thử (khi provider khả dụng)")); l.addStretch()
    def _video(self):
        l=QVBoxLayout(self.video); form=QFormLayout(); self.aspect=QComboBox(); self.aspect.addItems(["16:9","9:16","1:1","4:5","4:3"]); form.addRow("Tỷ lệ xuất",self.aspect); self.performance=QComboBox(); self.performance.addItems(["Light","Balanced","Strong"]); form.addRow("Công suất",self.performance); self.blur=QCheckBox("Bật vùng làm mờ (thiết lập nâng cao)"); form.addRow("Blur",self.blur); l.addLayout(form); l.addWidget(QPushButton("🎬 Render preview / export")); l.addStretch()
    def _settings(self):
        l=QVBoxLayout(self.settings_tab); form=QFormLayout(); self.lang=QComboBox(); self.lang.addItems(["vi","en"]); form.addRow("Language",self.lang); self.data_path=QLineEdit(str(self.data_dir)); self.api_key=QLineEdit(self.settings.get("openai_api_key", "")); self.api_key.setEchoMode(QLineEdit.Password); browse=QPushButton("Chọn"); browse.clicked.connect(self._choose_data); h=QHBoxLayout(); h.addWidget(self.data_path); h.addWidget(browse); box=QWidget(); box.setLayout(h); form.addRow("Data folder",box); form.addRow("OpenAI API key",self.api_key); l.addLayout(form); save=QPushButton("Lưu Settings"); save.clicked.connect(self._save_settings); l.addWidget(save); l.addStretch()
    def _help(self):
        l=QVBoxLayout(self.help); txt=QPlainTextEdit(); txt.setReadOnly(True); txt.setPlainText("""QUY TRÌNH NHANH\n\n1. Dự án mới → chọn video.\n2. Subtitle → Nạp SRT hoặc dùng OCR/ASR provider.\n3. Dịch → chọn phong cách → dịch → validator kiểm tra.\n4. Giọng đọc → chọn provider/voice nếu provider khả dụng.\n5. Video → chọn aspect ratio/công suất.\n6. Render/Export.\n\nLƯU Ý\n- ChatGPT Web không được điều khiển bằng cookie/session. Dùng API/OAuth chính thức khi có.\n- Voice độc quyền chỉ tích hợp bằng SDK/API/quyền hợp pháp.\n- Khi provider/model thiếu, app phải báo rõ thay vì giả vờ đã hoạt động.\n- Project tự lưu JSON và checkpoint trong data folder."""); l.addWidget(txt)
    def _logs(self):
        l=QVBoxLayout(self.logs); self.log_view=QPlainTextEdit(); self.log_view.setReadOnly(True); l.addWidget(self.log_view)
    def _choose_video(self):
        p,_=QFileDialog.getOpenFileName(self,"Chọn video","","Video (*.mp4 *.mkv *.mov *.avi *.webm *.m4v)");
        if p: self.project.video_path=p; self.video_label.setText(p); self.project_store_save()
    def _new_project(self): self.project=Project.new(); self.project_list.setPlainText("Project hiện tại: "+self.project.name); self.table.setRowCount(0)
    def _open_project(self):
        p,_=QFileDialog.getOpenFileName(self,"Mở project",str(self.data_dir/'projects'),"Project (*.json)")
        if p:
            try:
                self.project=self.store.load(Path(p)); self._refresh_table(); self.project_list.setPlainText("Project hiện tại: "+self.project.name)
            except Exception as e: QMessageBox.critical(self,"Lỗi",str(e))
    def _import_srt(self):
        p,_=QFileDialog.getOpenFileName(self,"Nạp SRT","","Subtitle (*.srt)")
        if not p:return
        try:
            self.project.subtitle_path=p; self.project.subtitles=parse_srt(Path(p).read_text(encoding='utf-8-sig')); self._refresh_table(); self.project.checkpoints['Subtitle']=True; self.project_store_save()
        except Exception as e: QMessageBox.critical(self,"SRT lỗi",str(e))
    def _export_srt(self):
        p,_=QFileDialog.getSaveFileName(self,"Xuất SRT","translated.srt","Subtitle (*.srt)")
        if p: Path(p).write_text(write_srt(self.project.subtitles,True),encoding='utf-8')
    def _refresh_table(self):
        self.table.setRowCount(len(self.project.subtitles))
        for r,s in enumerate(self.project.subtitles):
            vals=[str(s.index),f"{s.start_ms/1000:.3f}",f"{s.end_ms/1000:.3f}",s.original,s.translated]
            for c,v in enumerate(vals): self.table.setItem(r,c,QTableWidgetItem(v))
    def _translate(self):
        if not self.project.subtitles: QMessageBox.warning(self,"Thiếu subtitle","Hãy nạp subtitle trước."); return
        mode=self.trans_mode.currentText(); provider=OpenAITranslationProvider(api_key=self.settings.get('openai_api_key') or None, model=self.settings.get('translation_model','gpt-5-mini'))
        if not provider.available():
            QMessageBox.warning(self,"Chưa có API","Hãy cấu hình OPENAI_API_KEY trong môi trường hoặc Settings. App không điều khiển ChatGPT Web bằng cookie/session."); return
        self.trans_status.setText("Đang dịch...")
        try:
            engine=TranslationEngine(provider); fails=engine.translate_lines(self.project.subtitles,TranslationContext(mode=mode,extra_context=self.context.text()),batch_size=10)
            self._refresh_table(); self.trans_status.setText("Hoàn tất" if not fails else f"Còn lỗi ở dòng: {fails[:20]}"); self.project.checkpoints['Translate']=not bool(fails); self.project.checkpoints['Validate']=not bool(fails); self.project_store_save()
        except Exception as e: self.trans_status.setText("Lỗi: "+str(e))
    def _choose_data(self):
        p=QFileDialog.getExistingDirectory(self,"Chọn data folder")
        if p: self.data_path.setText(p)
    def _save_settings(self):
        self.settings.update({'language':self.lang.currentText(),'data_root':self.data_path.text(),'translation_mode':self.trans_mode.currentText(),'performance_mode':self.performance.currentText(),'openai_api_key':self.api_key.text()}); self.settings_store.save(self.settings); QMessageBox.information(self,"Saved","Settings đã được lưu.")
    def _save_quiet(self):
        try: self.project_store_save()
        except Exception: pass
    def project_store_save(self):
        self.store.save(self.project)
    def _qss(self):
        return """
        QWidget{font-size:14px;} QTabWidget::pane{border:1px solid #333;} QTabBar::tab{padding:10px 16px;} QPushButton{padding:8px 12px;} QLineEdit,QComboBox,QPlainTextEdit,QTableWidget{padding:5px;}
        """
