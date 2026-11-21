"""DICOM Reader desktop program (PySide6). Run: python main.py  — or the packaged DICOMReader.exe."""
import multiprocessing
import os
import sys
import traceback


def _show_fatal(message):
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
        QApplication.instance() or QApplication(sys.argv)
        QMessageBox.critical(None, "DICOM Reader", message)
    except Exception:
        print(message, file=sys.stderr)


def main(argv=None):
    argv = list(sys.argv if argv is None else argv)
    multiprocessing.freeze_support()
    smoke = "--smoke-test" in argv
    if smoke:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from desktop.i18n import device_locale, select_language, is_arabic, tr
    os.environ.setdefault("DICOM_DEVICE_LANGUAGE", select_language(device_locale()))
    from desktop.runtime import state_dir
    log_path = state_dir() / "startup.log"
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QFont
        from PySide6.QtWidgets import QApplication
        from gui.style import stylesheet

        app = QApplication.instance() or QApplication(argv)
        app.setApplicationName("DICOMReader")
        app.setLayoutDirection(Qt.LayoutDirection.RightToLeft if is_arabic() else Qt.LayoutDirection.LeftToRight)
        app.setFont(QFont("Segoe UI", 11))
        app.setStyleSheet(stylesheet(is_arabic()))

        if smoke:
            from desktop.verification import verify_app
            verify_app()
            print("Desktop app healthy: DICOM -> MONAI report -> Gemini panel -> audio verified.")
            return 0

        from gui.main_window import MainWindow
        window = MainWindow()
        window.show()
        # Opening a file with the program (e.g. double-click on a .dcm) loads it directly.
        paths = [a for a in argv[1:] if not a.startswith("--") and os.path.isfile(a)]
        if paths:
            window.open_path(paths[0])
        return app.exec()
    except Exception:
        with open(log_path, "w", encoding="utf-8") as log:
            log.write(traceback.format_exc())
        if smoke:
            raise
        _show_fatal(("تعذر فتح البرنامج. سجل الخطأ في %LOCALAPPDATA%\\DICOMReader\\startup.log."
                     if is_arabic() else
                     "Unable to open the program. Error log: %LOCALAPPDATA%\\DICOMReader\\startup.log."))
        return 1


if __name__ == "__main__":
    sys.exit(main())
