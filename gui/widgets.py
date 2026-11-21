"""Small reusable widgets: notices, image view, audio player, device voice reader, save helpers."""
import atexit
import os
import re
import tempfile

import numpy as np
from PySide6.QtCore import QLocale, Qt, QUrl
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QSizePolicy,
                               QVBoxLayout, QWidget)

from desktop.i18n import is_arabic, tr

_temp_files = []


@atexit.register
def _cleanup():
    for path in _temp_files:
        try:
            os.remove(path)
        except OSError:
            pass


def button(text, kind=None, tip=None):
    b = QPushButton(text)
    if kind:
        b.setProperty("kind", kind)
    if tip:
        b.setToolTip(tip)
    b.setAccessibleName(text)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def label(text="", name=None, wrap=True, rich=False):
    lab = QLabel()
    if rich:
        lab.setTextFormat(Qt.TextFormat.RichText)
    else:
        lab.setTextFormat(Qt.TextFormat.PlainText)
    lab.setText(text)
    lab.setWordWrap(wrap)
    if name:
        lab.setObjectName(name)
    lab.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return lab


def notice(text, tone="info"):
    lab = label(text)
    lab.setProperty("tone", tone)
    lab.setAccessibleName(text)
    return lab


def markdown_label(text):
    lab = QLabel()
    lab.setTextFormat(Qt.TextFormat.MarkdownText)
    lab.setText(text)
    lab.setWordWrap(True)
    lab.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)
    lab.setAccessibleDescription(text)
    return lab


def bold_markdown(text):
    """The intro text uses **bold** markers; render them as HTML."""
    from html import escape
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escape(text))


def clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            w.setParent(None)
            w.deleteLater()
        elif item.layout() is not None:
            clear_layout(item.layout())


def save_bytes(parent, data: bytes, default_name: str, file_filter: str) -> bool:
    path, _ = QFileDialog.getSaveFileName(parent, tr('حفظ الملف'), default_name, file_filter)
    if not path:
        return False
    try:
        with open(path, "wb") as fh:
            fh.write(data)
    except OSError:
        QMessageBox.warning(parent, tr('حفظ الملف'), tr('تعذّر حفظ الملف.'))
        return False
    return True


class ImageView(QLabel):
    """Shows (norm * 255).astype(np.uint8), scaled to the available width."""

    def __init__(self, norm: np.ndarray, caption: str):
        super().__init__()
        img = np.ascontiguousarray((norm * 255).astype(np.uint8))
        h, w = img.shape
        self._buffer = img
        self._pixmap = QPixmap.fromImage(QImage(img.data, w, h, w, QImage.Format.Format_Grayscale8).copy())
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(200, 200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setAccessibleName(caption)
        self.setToolTip(caption)
        self.setStyleSheet("background:#111; border-radius:8px;")
        self._rescale()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._rescale()

    def _rescale(self):
        width = max(200, self.width())
        scaled = self._pixmap.scaledToWidth(min(width, 900), Qt.TransformationMode.SmoothTransformation)
        self.setPixmap(scaled)
        self.setMinimumHeight(min(scaled.height(), 900))

    def hasHeightForWidth(self):
        return False


class AudioPlayer(QWidget):
    """MP3 player with play/pause and a separate save button (st.audio + st.download_button)."""

    def __init__(self, data: bytes, save_label: str, file_name: str, title: str | None = None, autoplay=False):
        super().__init__()
        self.data = data
        self.file_name = file_name
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        if title:
            layout.addWidget(label(title, "h3"))
        row = QHBoxLayout()
        self.play_btn = button(tr('▶ تشغيل'), "quiet")
        self.save_btn = button(save_label, "download")
        row.addWidget(self.play_btn)
        row.addWidget(self.save_btn)
        row.addStretch(1)
        layout.addLayout(row)
        self.status = label("", "caption")
        layout.addWidget(self.status)
        self.save_btn.clicked.connect(lambda: save_bytes(self, self.data, self.file_name, "MP3 (*.mp3)"))
        self.player = None
        try:
            from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
            fd, path = tempfile.mkstemp(suffix=".mp3", prefix="dicom_audio_")
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            _temp_files.append(path)
            self.output = QAudioOutput(self)
            self.player = QMediaPlayer(self)
            self.player.setAudioOutput(self.output)
            self.player.setSource(QUrl.fromLocalFile(path))
            self.player.playbackStateChanged.connect(self._sync)
            self.play_btn.clicked.connect(self.toggle)
            if autoplay:
                self.player.play()
        except Exception:
            self.play_btn.setEnabled(False)
            self.status.setText(tr('تعذّر تشغيل الصوت على هذا الجهاز.'))

    def toggle(self):
        from PySide6.QtMultimedia import QMediaPlayer
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _sync(self, state):
        from PySide6.QtMultimedia import QMediaPlayer
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self.play_btn.setText(tr('⏸ إيقاف مؤقت') if playing else tr('▶ تشغيل'))

    def stop(self):
        if self.player:
            self.player.stop()


class DeviceVoiceReader(QWidget):
    """Offline fallback reader using the Windows voices."""

    def __init__(self, text: str):
        super().__init__()
        self.text = text
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.read_btn = button(tr('🔊 قراءة بصوت الجهاز'), "quiet")
        self.stop_btn = button(tr('⏹ إيقاف'), "quiet")
        layout.addWidget(self.read_btn)
        layout.addWidget(self.stop_btn)
        layout.addStretch(1)
        self.engine = None
        self.read_btn.clicked.connect(self.read)
        self.stop_btn.clicked.connect(self.stop)

    def _ensure(self):
        if self.engine is not None:
            return self.engine
        try:
            from PySide6.QtTextToSpeech import QTextToSpeech
            engine = QTextToSpeech(self)
            wanted = QLocale(QLocale.Language.Arabic) if is_arabic() else QLocale(QLocale.Language.English)
            for loc in engine.availableLocales():
                if loc.language() == wanted.language():
                    engine.setLocale(loc)
                    break
            engine.setRate(-0.05)
            self.engine = engine
        except Exception:
            self.engine = False
        return self.engine

    def read(self):
        engine = self._ensure()
        if not engine:
            QMessageBox.information(self, tr('قارئ بديل يعمل بأصوات ويندوز دون إنترنت:'),
                                    tr('لا يتوفر صوت على هذا الجهاز للقراءة البديلة.'))
            return
        engine.stop()
        engine.say(self.text)

    def stop(self):
        if self.engine:
            self.engine.stop()
