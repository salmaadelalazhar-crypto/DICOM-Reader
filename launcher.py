"""Windows desktop entry point and explicit frozen Streamlit worker mode."""
import multiprocessing
import os
import subprocess
import sys
import time
from urllib.request import urlopen
from desktop.i18n import device_locale, select_language, tr
from desktop.runtime import root, state_dir, child_command, free_port


def worker(port):
    # The EXE re-enters this mode; never run `EXE -m streamlit` recursively.
    from streamlit.web import cli
    os.chdir(root())
    sys.argv = ['streamlit', 'run', str(root() / 'app.py'),
                '--server.address=127.0.0.1', f'--server.port={port}',
                '--server.headless=true', '--server.maxUploadSize=200',
                '--browser.gatherUsageStats=false', '--server.fileWatcherType=none',
                '--client.toolbarMode=minimal']
    cli.main()


def wait_ready(child, url, timeout=180):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if child.poll() is not None:
            raise RuntimeError('The local application process stopped before startup.')
        try:
            with urlopen(url + '/_stcore/health', timeout=2) as response:
                if response.status == 200:
                    return
        except (OSError, TimeoutError):
            pass
        time.sleep(0.25)
    raise TimeoutError('The local application did not start in time.')


def stop_child(child):
    if child and child.poll() is None:
        child.terminate()
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=10)


def launch():
    os.environ['DICOM_DEVICE_LANGUAGE'] = select_language(device_locale())
    os.environ['DICOM_DESKTOP'] = '1'
    # Per-user key only. No developer/provider secret is bundled into the EXE.
    if not os.environ.get('GEMINI_API_KEY') and sys.platform == 'win32':
        try:
            import keyring
            key = keyring.get_password('DICOMReader', 'GEMINI_API_KEY')
            if key:
                os.environ['GEMINI_API_KEY'] = key
        except Exception:
            pass
    state = state_dir()
    os.environ['STREAMLIT_BROWSER_GATHER_USAGE_STATS'] = 'false'
    port = free_port()
    url = f'http://127.0.0.1:{port}'
    child = None
    bridge = None
    try:
        with (state / 'startup.log').open('w', encoding='utf-8') as log:
            child = subprocess.Popen(child_command(port), env=os.environ.copy(),
                stdout=log, stderr=log, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            wait_ready(child, url)
            if '--smoke-test' in sys.argv:
                from desktop.verification import verify_app
                verify_app()
                print('Desktop worker healthy; loopback-only startup verified.')
                return
            import webview
            from desktop.speech import SpeechBridge
            bridge = SpeechBridge()
            webview.settings['ALLOW_DOWNLOADS'] = True
            webview.create_window(tr('قارئ أشعة DICOM الميسّر'), url, js_api=bridge,
                                  width=1280, height=850, min_size=(800, 600))
            webview.start(gui='edgechromium', private_mode=True, storage_path=str(state / 'webview'))
    finally:
        if bridge:
            bridge.stop_speech()
        stop_child(child)


def main():
    multiprocessing.freeze_support()
    if '--streamlit-worker' in sys.argv:
        worker(int(sys.argv[sys.argv.index('--streamlit-worker') + 1]))
        return
    try:
        launch()
    except Exception:
        # Avoid displaying exception/provider details or environment values.
        if '--smoke-test' in sys.argv:
            raise
        message = ('تعذر فتح التطبيق. تحقق من تثبيت Microsoft Edge WebView2 Runtime. '
                   'سجل بدء التشغيل في %LOCALAPPDATA%\\DICOMReader\\startup.log.'
                   if os.environ.get('DICOM_DEVICE_LANGUAGE') == 'ar' else
                   'Unable to open the app. Check Microsoft Edge WebView2 Runtime. '
                   'Startup log: %LOCALAPPDATA%\\DICOMReader\\startup.log.')
        if sys.platform == 'win32':
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, message, 'DICOM Reader', 16)
        else:
            print(message, file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
