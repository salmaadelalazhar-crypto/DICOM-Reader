"""First-run screen: guide the user to create a Gemini API key and save it on this device."""
from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLineEdit, QVBoxLayout

from desktop.api_key import CREATE_KEY_URL, save_api_key
from desktop.i18n import is_arabic
from .widgets import button, label, notice


class ApiKeySetup(QFrame):
    saved = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("card")
        if is_arabic():
            title = "للحصول على تقارير تفصيلية من الذكاء الاصطناعي، أدخل مفتاح API الخاص بك"
            subtitle = "خطوات إنشاء مفتاح API:"
            link_text = "افتح صفحة إنشاء المفتاح في Google AI Studio"
            steps = [
                "اضغط على الرابط بالأسفل لفتح صفحة Google AI Studio.",
                "سجّل الدخول بحساب Gmail الخاص بك إذا طُلب منك ذلك.",
                "اضغط على زر «Create API key».",
                "سيظهر المفتاح، اضغط على زر النسخ بجانبه.",
                "ارجع إلى البرنامج والصق المفتاح في المربع بالأسفل.",
                "اضغط «حفظ». هذا كل شيء، ولن تحتاج إلى إدخاله مرة أخرى.",
            ]
            field, save = "مفتاح API", "حفظ"
            self.ok, self.bad = "تم حفظ المفتاح بنجاح.", "الرجاء لصق المفتاح في المربع أولاً."
        else:
            title = "To get detailed AI reports, enter your API key"
            subtitle = "Steps to create an API key:"
            link_text = "Open the key page in Google AI Studio"
            steps = [
                "Click the link below to open Google AI Studio.",
                "Sign in with your Gmail account if asked.",
                "Click the \"Create API key\" button.",
                "Your key will appear. Click the copy button next to it.",
                "Come back to this program and paste the key into the box below.",
                "Click \"Save\". That's it, you won't need to enter it again.",
            ]
            field, save = "API key", "Save"
            self.ok, self.bad = "Key saved successfully.", "Please paste the key into the box first."

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.addWidget(label(title, "h2"))
        layout.addWidget(label(subtitle, "h3"))
        layout.addWidget(label("\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1))))
        link = button(link_text)
        link.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(CREATE_KEY_URL)))
        layout.addWidget(link)
        layout.addWidget(label(field, "h3"))
        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setEchoMode(QLineEdit.EchoMode.Password)
        self.input.setAccessibleName(field)
        self.save_btn = button(save, "solid")
        row.addWidget(self.input, 5)
        row.addWidget(self.save_btn, 1)
        layout.addLayout(row)
        self.message = QVBoxLayout()
        layout.addLayout(self.message)
        self.save_btn.clicked.connect(self._save)
        self.input.returnPressed.connect(self._save)

    def _save(self):
        while self.message.count():
            w = self.message.takeAt(0).widget()
            if w:
                w.deleteLater()
        if save_api_key(self.input.text()):
            self.message.addWidget(notice(self.ok, "success"))
            self.saved.emit()
        else:
            self.message.addWidget(notice(self.bad, "error"))
