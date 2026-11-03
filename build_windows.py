"""Run on Windows after installing requirements-desktop.txt."""
import sys
from pathlib import Path
import PyInstaller.__main__

if sys.platform != 'win32':
    raise SystemExit('Windows EXE must be built on Windows (use GitHub Actions).')
root = Path(__file__).resolve().parent
args = ['--noconfirm', '--clean', '--onedir', '--windowed', '--name=DICOMReader',
        '--paths=' + str(root), '--add-data=' + str(root / 'app.py') + ';.',
        '--add-data=' + str(root / 'desktop') + ';desktop',
        '--add-data=' + str(root / 'monai_gemini') + ';monai_gemini',
        '--add-data=' + str(root / '.streamlit') + ';.streamlit',
        '--copy-metadata=streamlit', '--copy-metadata=google-genai',
        '--copy-metadata=monai', '--hidden-import=streamlit.web.cli',
        '--hidden-import=desktop.speech_ui', '--hidden-import=desktop.speech',
        '--hidden-import=monai_gemini.ui', '--hidden-import=openpyxl',
        '--hidden-import=keyring.backends.Windows', '--hidden-import=webview.platforms.edgechromium',
        '--hidden-import=pyaudio', '--hidden-import=speech_recognition',
        '--hidden-import=pydicom.pixels.decoders.pylibjpeg']
# app.py runs dynamically through Streamlit, so explicitly collect its runtime graph.
for package in ['streamlit', 'streamlit_mic_recorder', 'monai', 'pydicom',
                'pylibjpeg', 'libjpeg', 'webview', 'imageio_ffmpeg', 'google.genai',
                'gtts', 'openpyxl', 'numpy', 'pandas', 'torch', 'keyring', 'speech_recognition']:
    args += ['--collect-all=' + package]
args += [str(root / 'launcher.py')]
PyInstaller.__main__.run(args)
