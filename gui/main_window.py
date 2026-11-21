"""Main window: upload, results, batch summary and the Gemini section."""
import os
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QFileDialog, QFrame, QHBoxLayout, QHeaderView,
                               QMainWindow, QProgressBar, QScrollArea, QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

from core.processing import analyze_all, build_batch_excel, load_files, monai_report_text
from desktop.i18n import tr
from monai_gemini.conversation import resolve_api_key
from .api_key_setup import ApiKeySetup
from .gemini_panel import GeminiPanel
from .result_view import ResultView
from .widgets import bold_markdown, button, clear_layout, label, notice, save_bytes
from .workers import run_task


class Collapsible(QWidget):
    """Expander like st.expander; the result view is built only when first opened."""

    def __init__(self, title, factory):
        super().__init__()
        self.factory, self.body = factory, None
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(0, 0, 0, 0)
        self.toggle = button("▸ " + title, "section")
        self.toggle.setCheckable(True)
        self.title = title
        self.toggle.toggled.connect(self._toggled)
        self.box.addWidget(self.toggle)

    def _toggled(self, open_):
        self.toggle.setText(("▾ " if open_ else "▸ ") + self.title)
        if open_ and self.body is None:
            self.body = self.factory()
            self.box.addWidget(self.body)
        if self.body is not None:
            self.body.setVisible(open_)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(tr('قارئ أشعة DICOM الميسّر'))
        self.resize(1280, 860)
        self.setMinimumSize(800, 600)
        self.setAcceptDrops(True)
        self.results, self.failed = [], []
        self.loading = False

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content.setObjectName("content")
        scroll.setWidget(content)
        self.setCentralWidget(scroll)
        root = QVBoxLayout(content)
        root.setContentsMargins(28, 20, 28, 28)
        root.setSpacing(14)

        root.addWidget(label(tr('🩻 قارئ ومفسّر ملفات الأشعة الطبية (DICOM)'), "title"))
        root.addWidget(label(bold_markdown(tr('مرحبًا بك. **الخطوة الأولى:** ارفع ملف أشعة بامتداد \u200e.dcm\u200e. **الخطوة الثانية:** اقرأ التقرير أو اضغط زر الاستماع. **الخطوة الثالثة:** نزّل التقرير الكامل بصيغة Excel. جميع الأزرار مُعنونة نصيًا ومتوافقة مع قارئات الشاشة ويمكن التنقل بينها بمفتاح Tab.')), rich=True))
        root.addWidget(notice(tr('تنبيه: هذا التحليل آلي وصفي للمساعدة فقط، ولا يُغني عن تشخيص الطبيب المختص.'), "warning"))

        drop = QFrame()
        drop.setObjectName("dropzone")
        dz = QVBoxLayout(drop)
        dz.setContentsMargins(18, 16, 18, 16)
        dz.addWidget(label(tr('ارفع ملف أشعة \u200e.dcm\u200e أو ملفاً مضغوطاً \u200e.zip\u200e يحتوي عدة ملفات أشعة (الحد الأقصى 200 ميجابايت). اضغط زر «اختيار ملف» أو اسحب الملف إلى هذه النافذة.')))
        dz.addWidget(label(tr('ملف \u200e.dcm\u200e يُحلَّل مباشرة. ملف \u200e.zip\u200e يُفك ضغطه وتُحلَّل كل ملفات DICOM بداخله دفعة واحدة.'), "caption"))
        row = QHBoxLayout()
        self.open_btn = button(tr('📂 اختيار ملف'), "solid")
        self.open_btn.clicked.connect(self.choose_file)
        self.file_label = label("", wrap=False)
        row.addWidget(self.open_btn)
        row.addWidget(self.file_label, 1)
        dz.addLayout(row)
        root.addWidget(drop)

        self.status = QVBoxLayout()
        root.addLayout(self.status)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        root.addWidget(self.progress)
        self.results_box = QVBoxLayout()
        root.addLayout(self.results_box)

        self.ai_header = QVBoxLayout()
        root.addLayout(self.ai_header)
        self.gemini = GeminiPanel()
        root.addWidget(self.gemini)
        self.idle_box = QVBoxLayout()
        root.addLayout(self.idle_box)
        root.addStretch(1)
        self.gemini.setVisible(False)
        self._show_idle()

    # ---------- input ----------
    def choose_file(self):
        path, _ = QFileDialog.getOpenFileName(self, tr('اختر ملف أشعة'), "", tr('ملفات الأشعة (*.dcm *.zip)') + ";;* (*)")
        if path:
            self.open_path(path)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if urls:
            self.open_path(urls[0])

    def open_path(self, path):
        try:
            with open(path, "rb") as fh:
                raw = fh.read()
        except OSError as e:
            self._set_status(notice(str(e), "error"))
            return
        self.load_bytes(os.path.basename(path), raw)

    def load_bytes(self, name, raw):
        if self.loading:
            return
        self.file_label.setText(f"📄 {name}  ({len(raw) / 1024 / 1024:.1f} MB)")
        self._clear_results()
        clear_layout(self.idle_box)
        try:
            files = load_files(name, raw)
        except ValueError as e:
            self._set_status(notice(str(e), "error"))
            return
        except Exception as e:
            self._set_status(notice(tr('تعذّر فك ضغط الملف. تأكد أنه ملف ZIP سليم. التفاصيل: {v0}', v0=e), "error"))
            return
        if not files:
            self._set_status(notice(tr('لم يُعثر على أي ملف أشعة DICOM داخل الملف المضغوط.'), "warning"))
            return
        if name.lower().endswith(".zip"):
            self._set_status(notice(tr('تم العثور على {v0} ملف أشعة داخل الملف المضغوط. تبدأ المعالجة الآن.', v0=len(files)), "success"))
        else:
            self._set_status(None)
        self.loading = True
        self.open_btn.setEnabled(False)
        self.progress.setRange(0, len(files))
        self.progress.setValue(0)
        self.progress.setFormat(tr('جارٍ تحليل الملفات...'))
        self.progress.setVisible(True)
        run_task(analyze_all, files, on_progress=self._progress, on_done=self._analyzed, on_error=self._analysis_error)

    def _progress(self, done, total):
        self.progress.setValue(done)
        self.progress.setFormat(tr('تم تحليل {v0} من {v1}', v0=done, v1=total))

    def _analysis_error(self, error):
        self._finish_loading()
        self._set_status(notice(str(error), "error"))

    def _finish_loading(self):
        self.loading = False
        self.open_btn.setEnabled(True)
        self.progress.setVisible(False)

    # ---------- results ----------
    def _analyzed(self, outcome):
        self._finish_loading()
        self.results, self.failed = outcome
        box = self.results_box
        if self.failed:
            failed = Collapsible(tr('⚠️ ملفات تعذّرت قراءتها ({v0})', v0=len(self.failed)),
                                 lambda: label("\n".join(f"- {n}: {e}" for n, e in self.failed)))
            box.addWidget(failed)
        if not self.results:
            box.addWidget(notice(tr('تعذّرت قراءة الملفات. تأكد أنها ملفات DICOM سليمة تحتوي على صور.'), "error"))
            return
        box.addWidget(label(tr('البيانات الطبية المستخرجة'), "h2"))
        if len(self.results) == 1:
            box.addWidget(ResultView(0, *self.results[0]))
        else:
            self._batch(box)
        self._gemini_section()

    def _batch(self, box):
        box.addWidget(label(tr('ملخص الدفعة: {v0} ملف تم تحليله بنجاح', v0=len(self.results)), "h3"))
        cols = [tr('اسم الملف'), tr('نوع الجهاز'), tr('الجزء المفحوص'), tr('عدد الصفوف'), tr('عدد الأعمدة')]
        table = QTableWidget(len(self.results), len(cols))
        table.setHorizontalHeaderLabels(cols)
        for r, (meta, _a, _l) in enumerate(self.results):
            for c, col in enumerate(cols):
                table.setItem(r, c, QTableWidgetItem(str(meta.get(col, ""))))
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setMinimumHeight(min(60 + 32 * len(self.results), 360))
        box.addWidget(table)
        excel = button(tr('⬇️ تنزيل تقرير جميع الملفات في ملف Excel واحد'), "download", tr('ملف Excel يحتوي ملخص كل الملفات وتقاريرها'))
        excel.clicked.connect(lambda: save_bytes(self, build_batch_excel(self.results),
                                                 f"dicom_batch_report_{datetime.now():%Y%m%d_%H%M%S}.xlsx", "Excel (*.xlsx)"))
        box.addWidget(excel, 0, Qt.AlignmentFlag.AlignLeft)
        box.addWidget(label(tr('اضغط على اسم أي ملف بالأسفل لفتح صورته وتقريره.'), "caption"))
        for i, (meta, analysis, lines) in enumerate(self.results):
            box.addWidget(Collapsible(f"📄 {i + 1}. {meta[tr('اسم الملف')]}",
                                      lambda i=i, m=meta, a=analysis, l=lines: ResultView(i, m, a, l)))

    def _gemini_section(self):
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        self.ai_header.addWidget(line)
        if len(self.results) > 1:
            self.ai_header.addWidget(label(tr('ملف الأشعة المطلوب إرساله إلى الذكاء الاصطناعي'), "h3"))
            self.source_box = QComboBox()
            self.source_box.setAccessibleName(tr('ملف الأشعة المطلوب إرساله إلى الذكاء الاصطناعي'))
            for meta, _a, _l in self.results:
                self.source_box.addItem(meta[tr('اسم الملف')])
            self.source_box.currentIndexChanged.connect(self._select_source)
            self.source_box.setMinimumWidth(360)
            self.ai_header.addWidget(self.source_box, 0, Qt.AlignmentFlag.AlignLeft)
        self.gemini.setVisible(True)
        self._select_source(0)

    def _select_source(self, index):
        meta, analysis, lines = self.results[index]
        self.gemini.set_report(monai_report_text(meta, analysis, lines))

    def _clear_results(self):
        clear_layout(self.results_box)
        clear_layout(self.ai_header)
        self.gemini.set_report("")
        self.gemini.setVisible(False)
        self.results, self.failed = [], []

    def _set_status(self, widget):
        clear_layout(self.status)
        if widget is not None:
            self.status.addWidget(widget)

    def _show_idle(self):
        self._set_status(notice(tr('لم يتم رفع أي ملف بعد. بانتظار ملف الأشعة أو الملف المضغوط.')))
        clear_layout(self.idle_box)
        if not resolve_api_key():
            setup = ApiKeySetup()
            self.idle_box.addWidget(setup)

    def closeEvent(self, event):
        self.gemini.close_service()
        super().closeEvent(event)
