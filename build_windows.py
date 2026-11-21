"""Build DICOMReader.exe on Windows: python build_windows.py (after installing requirements-desktop.txt)."""
import sys
from pathlib import Path
import PyInstaller.__main__

if sys.platform != 'win32':
    raise SystemExit('Windows EXE must be built on Windows (use GitHub Actions).')
root = Path(__file__).resolve().parent
args = ['--noconfirm', '--clean', '--onedir', '--windowed', '--name=DICOMReader',
        '--paths=' + str(root),
        '--add-data=' + str(root / 'desktop' / 'translations.json') + ';desktop',
        '--copy-metadata=google-genai', '--copy-metadata=monai', '--copy-metadata=pydicom',
        '--hidden-import=pyaudio', '--hidden-import=speech_recognition',
        '--hidden-import=pydicom.pixels.decoders.pylibjpeg',
        '--hidden-import=PySide6.QtMultimedia', '--hidden-import=PySide6.QtTextToSpeech',
        # Unused heavy Qt parts are excluded to keep the program small and fast to start.
        '--exclude-module=PySide6.QtWebEngineCore', '--exclude-module=PySide6.QtWebEngineWidgets',
        '--exclude-module=PySide6.Qt3DCore', '--exclude-module=PySide6.QtQuick3D',
        '--exclude-module=tkinter']
# MONAI, pydicom decoders and gTTS load parts of themselves dynamically; collect them fully.
for package in ['monai', 'pydicom', 'pylibjpeg', 'libjpeg', 'gtts', 'google.genai', 'speech_recognition']:
    args += ['--collect-all=' + package]
args += [str(root / 'main.py')]
PyInstaller.__main__.run(args)
