"""Offline packaged-app smoke check; no credentials, patient data or network AI."""
import io
import os
import time
from unittest.mock import patch

import numpy as np
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, SecondaryCaptureImageStorage, generate_uid


def synthetic_dicom(name='smoke.dcm', rows=16, cols=16):
    metadata = FileMetaDataset()
    metadata.TransferSyntaxUID = ExplicitVRLittleEndian
    metadata.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
    metadata.MediaStorageSOPInstanceUID = generate_uid()
    ds = FileDataset(name, {}, file_meta=metadata, preamble=b'\0' * 128)
    ds.Rows, ds.Columns = rows, cols
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = 'MONOCHROME2'
    ds.BitsAllocated = ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 0
    ds.Modality = 'CT'
    ds.BodyPartExamined = 'CHEST'
    ds.PixelData = np.arange(rows * cols, dtype=np.uint16).reshape(rows, cols).tobytes()
    out = io.BytesIO()
    ds.save_as(out, enforce_file_format=True)
    return out.getvalue()


def wait_until(predicate, timeout=120):
    """Process Qt events until predicate() is true (background tasks deliver results via the event loop)."""
    from PySide6.QtCore import QCoreApplication, QThreadPool
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        if predicate():
            return
        QThreadPool.globalInstance().waitForDone(20)
    raise TimeoutError('Timed out waiting for the desktop window.')


def verify_app(require_monai=True):
    from gui.main_window import MainWindow
    from gui.result_view import ResultView
    from gui.widgets import AudioPlayer

    # The build machine has no saved key; use a fake one so the report screen is tested.
    os.environ.setdefault('GEMINI_API_KEY', 'smoke-test-only')
    with patch('gui.gemini_panel.GeminiPanel.service_factory') as factory, \
            patch('gtts.gTTS.write_to_fp', side_effect=lambda fp: fp.write(b'smoke-mp3')):
        service = factory.return_value
        service.available_models.return_value = {'gemini-3.5-flash-lite'}
        service.resolve_model.return_value = 'gemini-3.5-flash-lite'
        service.analyze.return_value = 'Offline smoke report'
        window = MainWindow()
        window.show()
        window.load_bytes('smoke.dcm', synthetic_dicom())
        wait_until(lambda: window.gemini.conversation is not None and window.gemini.conversation.analysis)
        if service.analyze.call_count != 1:
            raise RuntimeError('Packaged DICOM report smoke check failed.')
        if require_monai and 'MONAI + PyTorch' not in service.analyze.call_args.args[0]:
            raise RuntimeError('Packaged MONAI processing is unavailable.')
        view = window.findChild(ResultView)
        view.play_btn.click()
        wait_until(lambda: len(window.findChildren(AudioPlayer)) == 2)
        window.close()
    return window
