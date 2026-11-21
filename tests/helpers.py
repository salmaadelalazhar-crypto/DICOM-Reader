import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from desktop.verification import synthetic_dicom, wait_until  # noqa: E402,F401


def qt_app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])
