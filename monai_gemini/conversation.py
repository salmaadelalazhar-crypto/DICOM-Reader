"""Gemini conversation state for one MONAI report (the logic of the old ui.py, without any UI library)."""
import mimetypes
import os
from dataclasses import dataclass, field

from desktop.i18n import tr
from .service import Attachment

ATTACHMENT_TYPES = ("pdf", "txt", "csv", "json", "jpg", "jpeg", "png", "webp")


def model_title(label: str) -> str:
    return "Google Gemini " + label.removeprefix("Gemini ").strip()


def resolve_api_key() -> str | None:
    """GEMINI_API_KEY from the environment first, then the key saved on this device."""
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        from desktop.api_key import load_api_key
        key = load_api_key()
        if key:
            os.environ["GEMINI_API_KEY"] = key
    return key or None


def attachment_from_path(path: str) -> Attachment:
    with open(path, "rb") as fh:
        data = fh.read()
    name = os.path.basename(path)
    return Attachment(name, mimetypes.guess_type(name)[0] or "application/octet-stream", data)


@dataclass
class Message:
    role: str  # "user" | "assistant"
    text: str
    files: list[str] = field(default_factory=list)
    audio: bytes | None = None


class Conversation:
    """One report = one conversation. Changing the report means a new Conversation (no mixing of cases)."""

    def __init__(self, monai_report: str):
        self.monai_report = monai_report
        self.analysis: str | None = None
        self.ai_audio: bytes | None = None
        self.messages: list[Message] = []
        self.auto_attempted = False

    def should_auto_send(self, notes: str, files) -> bool:
        """At most one automatic attempt per report (including failures), with the default prompt."""
        return not notes.strip() and not files and not self.auto_attempted

    def context(self) -> str:
        if not self.analysis:
            return self.monai_report
        return self.monai_report + tr('\n\n[تقرير الذكاء الاصطناعي السابق]:\n') + self.analysis

    def ask(self, service, model: str, notes: str, files: tuple[Attachment, ...], speak) -> bool:
        """Runs one request. Returns True when it produced the first AI report, False for a chat reply.
        Raises ServiceError/ValueError with a safe message."""
        first = not self.analysis
        result = service.analyze(self.context(), model, notes, files)
        audio = speak(result)
        if first:
            self.analysis = result
            self.ai_audio = audio
        else:
            self.messages.append(Message("user", notes.strip() or tr('سؤال حول التقرير'), [f.name for f in files]))
            self.messages.append(Message("assistant", result, audio=audio))
        return first
