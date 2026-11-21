"""One analyzed file: image, technical data, descriptive report, audio and Excel (the original show_result)."""
import hashlib
from datetime import datetime
from html import escape

from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QGridLayout, QHBoxLayout, QHeaderView, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from core.processing import GTTS_OK, build_excel, tts_bytes
from desktop.i18n import tr
from .widgets import AudioPlayer, DeviceVoiceReader, ImageView, button, label, notice, save_bytes
from .workers import run_task

_audio_cache = {}  # report hash -> MP3, like st.session_state["monai_audio_<hash>"]


def meta_table(meta):
    table = QTableWidget(len(meta), 2)
    table.setHorizontalHeaderLabels([tr('الحقل'), tr('القيمة')])
    for row, (k, v) in enumerate(meta.items()):
        table.setItem(row, 0, QTableWidgetItem(str(k)))
        table.setItem(row, 1, QTableWidgetItem(str(v)))
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setMinimumHeight(min(40 + 32 * len(meta), 600))
    table.setAccessibleName(tr('عرض البيانات التقنية الكاملة'))
    return table


class ResultView(QWidget):
    def __init__(self, idx, meta, analysis, report_lines):
        super().__init__()
        self.idx, self.meta, self.analysis, self.lines = idx, meta, analysis, report_lines
        self.text = " ".join(report_lines)
        self.audio_key = hashlib.sha256(self.text.encode("utf-8")).hexdigest()
        self.player = None

        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(24)

        left = QVBoxLayout()
        left.addWidget(label(tr('صورة الأشعة'), "h3"))
        caption = tr('صورة أشعة من نوع {v0} بأبعاد {v1} × {v2}', v0=meta[tr('نوع الجهاز')],
                     v1=meta[tr('عدد الصفوف')], v2=meta[tr('عدد الأعمدة')])
        left.addWidget(ImageView(analysis["norm"], caption))
        left.addWidget(label(caption, "caption"))
        self.meta_toggle = QCheckBox(tr('عرض البيانات التقنية الكاملة'))
        left.addWidget(self.meta_toggle)
        self.table = meta_table(meta)
        self.table.setVisible(False)
        left.addWidget(self.table)
        self.meta_toggle.toggled.connect(self.table.setVisible)
        left.addStretch(1)

        right = QVBoxLayout()
        right.addWidget(label(tr('التقرير الوصفي'), "h3"))
        report = label("<br>".join(escape(line) for line in report_lines), "report", rich=True)
        report.setAccessibleName(tr('التقرير الوصفي'))
        report.setAccessibleDescription(self.text)
        right.addWidget(report)
        right.addWidget(label(tr('زر الاستماع يحوّل التقرير إلى صوت عربي. زر التنزيل يحفظ بيانات هذا الملف في Excel.'), "caption"))
        row = QHBoxLayout()
        self.play_btn = button(tr('🔊 الاستماع للتقرير'), tip=tr('يحوّل نص التقرير إلى كلام مسموع'))
        self.excel_btn = button(tr('⬇️ تنزيل تقرير هذا الملف (Excel)'), "download")
        row.addWidget(self.play_btn)
        row.addWidget(self.excel_btn)
        right.addLayout(row)
        self.status = QVBoxLayout()
        right.addLayout(self.status)
        self.audio_box = QVBoxLayout()
        right.addLayout(self.audio_box)
        right.addWidget(label(tr('قارئ بديل يعمل بأصوات ويندوز دون إنترنت:'), "caption"))
        right.addWidget(DeviceVoiceReader(self.text))
        right.addStretch(1)

        grid.addLayout(left, 0, 0)
        grid.addLayout(right, 0, 1)
        grid.setColumnStretch(0, 10)
        grid.setColumnStretch(1, 13)

        self.play_btn.clicked.connect(self.listen)
        self.excel_btn.clicked.connect(self.save_excel)
        if self.audio_key in _audio_cache:
            self._show_audio(_audio_cache[self.audio_key], autoplay=False)

    def _set_status(self, widget):
        while self.status.count():
            w = self.status.takeAt(0).widget()
            if w:
                w.deleteLater()
        if widget:
            self.status.addWidget(widget)

    def listen(self):
        if not GTTS_OK:
            self._set_status(notice(tr('مكتبة gTTS غير مثبتة، استخدم القارئ البديل أدناه.')))
            return
        self.play_btn.setEnabled(False)
        self._set_status(label(tr('جارٍ تجهيز الصوت...'), "caption"))
        run_task(tts_bytes, self.text, on_done=self._audio_ready, on_error=self._audio_failed)

    def _audio_ready(self, mp3):
        self.play_btn.setEnabled(True)
        self._set_status(None)
        _audio_cache[self.audio_key] = mp3
        self._show_audio(mp3, autoplay=True)

    def _audio_failed(self, _error):
        self.play_btn.setEnabled(True)
        self._set_status(notice(tr('تعذّر الاتصال بخدمة gTTS، استخدم القارئ البديل أدناه.')))

    def _show_audio(self, mp3, autoplay):
        if self.player:
            self.player.stop()
            self.player.deleteLater()
        self.player = AudioPlayer(mp3, tr('تنزيل صوت MONAI (MP3)'), f"monai_report_{self.idx + 1}.mp3",
                                  title=tr('صوت تقرير MONAI الهندسي'), autoplay=autoplay)
        self.audio_box.addWidget(self.player)

    def save_excel(self):
        data = build_excel(self.meta, self.analysis, self.lines)
        save_bytes(self, data, f"dicom_report_{self.idx + 1}_{datetime.now():%Y%m%d_%H%M%S}.xlsx", "Excel (*.xlsx)")
