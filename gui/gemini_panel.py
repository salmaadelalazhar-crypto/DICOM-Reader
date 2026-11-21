"""AI report + follow-up questions about the selected MONAI report (replaces monai_gemini/ui.py)."""
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QComboBox, QFileDialog, QFrame, QHBoxLayout, QPlainTextEdit, QVBoxLayout, QWidget

from core.processing import gtts_mp3
from desktop.i18n import language, tr
from monai_gemini.conversation import ATTACHMENT_TYPES, Conversation, attachment_from_path, model_title, resolve_api_key
from monai_gemini.service import GeminiService, MODEL_SLOTS, ServiceError
from .api_key_setup import ApiKeySetup
from .widgets import AudioPlayer, button, clear_layout, label, markdown_label, notice, save_bytes
from .workers import run_task


def _service_factory(key):
    return GeminiService(api_key=key)


class GeminiPanel(QWidget):
    audio_phase = Signal()  # emitted from the worker when the text is ready and audio starts
    service_factory = staticmethod(_service_factory)

    def __init__(self):
        super().__init__()
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(0, 0, 0, 0)
        self.service = None
        self.available = None
        self.conversation = None
        self.report = ""
        self.files = []
        self.busy = False
        self.speech = None
        self.speech_timer = None
        self.audio_phase.connect(self._on_audio_phase)

    def _on_audio_phase(self):
        try:
            self.busy_label.setText(tr('جارٍ توليد الصوت…'))
        except (AttributeError, RuntimeError):
            pass

    # ---------- lifecycle ----------
    def set_report(self, monai_report: str):
        if monai_report == self.report and self.conversation is not None:
            return
        self.report = monai_report
        # Changing to another case clears the conversation and its audio, to avoid mixing cases.
        self.conversation = Conversation(monai_report) if monai_report.strip() else None
        self.files = []
        self._render()

    def _render(self):
        self._stop_speech()
        clear_layout(self.layout_)
        if not resolve_api_key():
            setup = ApiKeySetup()
            setup.saved.connect(self._key_changed)
            self.layout_.addWidget(setup)
            return
        if not self.report.strip():
            self.layout_.addWidget(notice(tr('لم يصدر تقرير MONAI بعد.')))
            return
        if self.service is None:
            try:
                self.service = self.service_factory(resolve_api_key())
            except ServiceError as error:
                self.layout_.addWidget(notice(str(error), "error"))
                return
        if self.available is None:
            self.layout_.addWidget(label(tr('جارٍ تحميل النماذج المتاحة…'), "caption"))
            run_task(self.service.available_models, on_done=self._models_ready, on_error=self._models_failed)
            return
        self._build()

    def _key_changed(self):
        self.close_service()
        QTimer.singleShot(600, self._render)

    def _change_key(self):
        from desktop.api_key import clear_api_key
        clear_api_key()
        self.close_service()
        self._render()

    def close_service(self):
        self._stop_speech()
        if self.service is not None:
            try:
                self.service.close()
            except Exception:
                pass
        self.service = None
        self.available = None

    def _models_ready(self, available):
        self.available = available
        self._render()

    def _models_failed(self, error):
        clear_layout(self.layout_)
        message = str(error) if isinstance(error, ServiceError) else tr('تعذر جلب النماذج؛ تحقق من المفتاح وصلاحيات الخدمة.')
        self.layout_.addWidget(notice(message, "error"))
        row = QHBoxLayout()
        retry = button(tr('إعادة المحاولة'))
        retry.clicked.connect(self._render)
        change = button(tr('تغيير مفتاح API'), "quiet")
        change.clicked.connect(self._change_key)
        row.addWidget(retry)
        row.addWidget(change)
        row.addStretch(1)
        self.layout_.addLayout(row)

    # ---------- UI ----------
    def _build(self):
        L = self.layout_
        # Section 2: AI report
        L.addWidget(label(tr('تقرير الذكاء الاصطناعي'), "h2"))
        self.report_area = QVBoxLayout()
        L.addLayout(self.report_area)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        L.addWidget(line)
        # Section 3: add a question
        L.addWidget(label(tr('أضف سؤالاً حول هذا التقرير'), "h2"))
        L.addWidget(label(tr('النموذج'), "h3"))
        self.model_box = QComboBox()
        for name in MODEL_SLOTS:
            self.model_box.addItem(model_title(name), name)
        self.model_box.setAccessibleName(tr('النموذج'))
        self.model_box.setMinimumWidth(360)
        L.addWidget(self.model_box, 0, Qt.AlignmentFlag.AlignLeft)
        self.model_warning = QVBoxLayout()
        L.addLayout(self.model_warning)
        self.chat_area = QVBoxLayout()
        L.addLayout(self.chat_area)

        L.addWidget(label(tr('الملفات الإضافية'), "h3"))
        files_row = QHBoxLayout()
        add = button(tr('📎 إضافة ملفات'), "quiet")
        clear = button(tr('مسح المرفقات'), "quiet")
        add.clicked.connect(self._add_files)
        clear.clicked.connect(self._clear_files)
        files_row.addWidget(add)
        files_row.addWidget(clear)
        files_row.addStretch(1)
        L.addLayout(files_row)
        self.files_label = label(tr('لا توجد مرفقات.'), "caption")
        L.addWidget(self.files_label)

        self.speech_box = QVBoxLayout()
        L.addLayout(self.speech_box)
        self._build_speech()

        L.addWidget(label(tr('سؤالك أو النص المنطوق'), "h3"))
        self.notes = QPlainTextEdit()
        self.notes.setMinimumHeight(140)
        self.notes.setAccessibleName(tr('سؤالك أو النص المنطوق'))
        L.addWidget(self.notes)
        row = QHBoxLayout()
        self.send_btn = button(tr('إرسال'), "solid")
        self.send_btn.clicked.connect(self.send)
        change = button(tr('تغيير مفتاح API'), "quiet")
        change.clicked.connect(self._change_key)
        row.addWidget(self.send_btn)
        row.addWidget(change)
        row.addStretch(1)
        L.addLayout(row)
        self.busy_label = label("", "caption")
        L.addWidget(self.busy_label)
        self.error_box = QVBoxLayout()
        L.addLayout(self.error_box)

        self.model_box.currentIndexChanged.connect(self._model_changed)
        self._refresh_views()
        self._model_changed()

    def _build_speech(self):
        try:
            import speech_recognition  # noqa: F401
            from desktop.speech import SpeechBridge
            ok = True
        except Exception:
            ok = False
        if not ok:
            self.speech_box.addWidget(label(tr('خاصية التحدث غير مثبتة؛ اكتب سؤالك في المربع.'), "caption"))
            return
        self.speech_box.addWidget(label(tr('اضغط زر التحدث وتكلم؛ يظهر كلامك نصاً في المربع مباشرة ويمكنك تعديله.'), "caption"))
        self.speech_btn = button(tr('🎤 ابدأ التحدث'))
        self.speech_btn.clicked.connect(self._toggle_speech)
        self.speech_box.addWidget(self.speech_btn, 0, Qt.AlignmentFlag.AlignLeft)
        self.speech_error = label("", "caption")
        self.speech_box.addWidget(self.speech_error)

    def _toggle_speech(self):
        from desktop.speech import SpeechBridge
        if self.speech is not None:
            self._stop_speech()
            return
        self.speech = SpeechBridge()
        result = self.speech.start_speech(language())
        if not result.get("ok"):
            self.speech_error.setText(result.get("error", ""))
            self.speech = None
            return
        self.speech_error.setText("")
        self.speech_btn.setText(tr('⏹ إيقاف التحدث'))
        self.speech_timer = QTimer(self)
        self.speech_timer.timeout.connect(self._poll_speech)
        self.speech_timer.start(300)

    def _poll_speech(self):
        if self.speech is None:
            return
        data = self.speech.poll_speech()
        for item in data.get("items", []):
            current = self.notes.toPlainText().strip()
            self.notes.setPlainText((current + " " + item["text"]).strip() if current else item["text"])
        if data.get("error"):
            self.speech_error.setText(data["error"])

    def _stop_speech(self):
        if self.speech_timer is not None:
            self.speech_timer.stop()
            self.speech_timer = None
        if self.speech is not None:
            try:
                self.speech.stop_speech()
            except Exception:
                pass
            self.speech = None
            try:
                self.speech_btn.setText(tr('🎤 ابدأ التحدث'))
            except (AttributeError, RuntimeError):
                pass

    def _add_files(self):
        pattern = " ".join(f"*.{e}" for e in ATTACHMENT_TYPES)
        paths, _ = QFileDialog.getOpenFileNames(self, tr('الملفات الإضافية'), "", tr('ملفات المرفقات (*.pdf *.txt *.csv *.json *.jpg *.jpeg *.png *.webp)').replace(
            "(*.pdf *.txt *.csv *.json *.jpg *.jpeg *.png *.webp)", f"({pattern})"))
        self.files.extend(paths)
        self._show_files()

    def _clear_files(self):
        self.files = []
        self._show_files()

    def _show_files(self):
        import os
        self.files_label.setText(tr('، ').join(os.path.basename(p) for p in self.files) if self.files else tr('لا توجد مرفقات.'))

    def current_model(self):
        label_ = self.model_box.currentData()
        try:
            return self.service.resolve_model(label_, self.available), None
        except ServiceError as error:
            return "", str(error)

    def _model_changed(self):
        clear_layout(self.model_warning)
        model, warning = self.current_model()
        if warning:
            self.model_warning.addWidget(notice(warning, "warning"))
        self.send_btn.setEnabled(bool(model) and not self.busy)
        if model and self.conversation and self.conversation.should_auto_send(self.notes.toPlainText(), self.files):
            # At most one automatic attempt per report, with the default prompt.
            self.conversation.auto_attempted = True
            self._start(model, "", ())

    # ---------- requests ----------
    def send(self):
        model, warning = self.current_model()
        if not model or self.busy:
            return
        try:
            files = tuple(attachment_from_path(p) for p in self.files)
        except OSError:
            self._show_error(tr('أحد المرفقات فارغ أو صيغته غير مدعومة.'))
            return
        self._start(model, self.notes.toPlainText(), files)

    def _start(self, model, notes, files):
        conversation = self.conversation
        self.busy = True
        self.send_btn.setEnabled(False)
        clear_layout(self.error_box)
        self.busy_label.setText(tr('جارٍ التحليل…'))

        def speak(text):
            self.audio_phase.emit()
            return gtts_mp3(text)

        def done(first):
            if conversation is not self.conversation:
                return  # the user switched to another case meanwhile
            self.busy = False
            self.busy_label.setText("")
            self.send_btn.setEnabled(True)
            if not first:
                self.notes.clear()
                self._clear_files()
            self._refresh_views()

        def failed(error):
            if conversation is not self.conversation:
                return
            self.busy = False
            self.busy_label.setText("")
            self.send_btn.setEnabled(True)
            self._show_error(str(error) if isinstance(error, (ServiceError, ValueError)) else
                             tr('تعذر توليد التقرير؛ تحقق من النموذج والاتصال وحصة Google.'))
            self._refresh_views()

        run_task(conversation.ask, self.service, model, notes, files, speak, on_done=done, on_error=failed)

    def _show_error(self, text):
        clear_layout(self.error_box)
        self.error_box.addWidget(notice(text, "error"))

    def _refresh_views(self):
        c = self.conversation
        clear_layout(self.report_area)
        if c and c.analysis:
            self.report_area.addWidget(markdown_label(c.analysis))
            dl = button(tr('تنزيل التقرير النصي'), "download")
            dl.clicked.connect(lambda: save_bytes(self, c.analysis.encode("utf-8"), "ai-report.txt", "Text (*.txt)"))
            self.report_area.addWidget(dl, 0, Qt.AlignmentFlag.AlignLeft)
            if c.ai_audio:
                self.report_area.addWidget(AudioPlayer(c.ai_audio, tr('تنزيل صوت تقرير الذكاء الاصطناعي'), "ai-report.mp3",
                                                       title=tr('صوت تقرير الذكاء الاصطناعي')))
            else:
                self.report_area.addWidget(label(tr('تعذر توليد الصوت عبر gTTS حالياً.'), "caption"))
        else:
            self.report_area.addWidget(notice(tr('لم يصدر تقرير الذكاء الاصطناعي بعد.')))

        clear_layout(self.chat_area)
        for i, m in enumerate(c.messages if c else []):
            frame = QFrame()
            frame.setObjectName("userMsg" if m.role == "user" else "aiMsg")
            box = QVBoxLayout(frame)
            box.addWidget(label(("🧑 " + tr('أنت')) if m.role == "user" else ("🤖 " + tr('الذكاء الاصطناعي')), "caption"))
            box.addWidget(markdown_label(m.text))
            if m.files:
                box.addWidget(label(tr('، ').join(m.files), "caption"))
            if m.audio:
                box.addWidget(AudioPlayer(m.audio, tr('تنزيل صوت الرد'), f"ai-reply-{i}.mp3"))
            self.chat_area.addWidget(frame)
