"""Offline packaged-app smoke check; no credentials, patient data or network AI."""
import io
from unittest.mock import patch

import numpy as np
import pydicom
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, SecondaryCaptureImageStorage, generate_uid
from streamlit.testing.v1 import AppTest
from desktop.runtime import root


def verify_app():
    metadata = FileMetaDataset()
    metadata.TransferSyntaxUID = ExplicitVRLittleEndian
    metadata.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
    metadata.MediaStorageSOPInstanceUID = generate_uid()
    ds = FileDataset('smoke.dcm', {}, file_meta=metadata, preamble=b'\0' * 128)
    ds.Rows = ds.Columns = 16
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = 'MONOCHROME2'
    ds.BitsAllocated = ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 0
    ds.Modality = 'CT'
    ds.PixelData = np.arange(256, dtype=np.uint16).reshape(16, 16).tobytes()
    upload = io.BytesIO()
    ds.save_as(upload, enforce_file_format=True)
    upload.name = 'smoke.dcm'
    def uploader(label, *args, **kwargs):
        return [] if kwargs.get('key') == 'mg_files' else upload
    with patch('streamlit.file_uploader', side_effect=uploader), patch('monai_gemini.ui.GeminiService') as cls, patch('gtts.gTTS.write_to_fp', side_effect=lambda fp: fp.write(b'smoke-mp3')):
        service = cls.return_value
        service.available_models.return_value = {'gemini-3.5-flash-lite'}
        service.resolve_model.return_value = 'gemini-3.5-flash-lite'
        service.analyze.return_value = 'Offline smoke report'
        app = AppTest.from_file(str(root() / 'app.py'), default_timeout=120).run()
        if app.exception or service.analyze.call_count != 1:
            raise RuntimeError('Packaged DICOM report smoke check failed.')
        if 'MONAI + PyTorch' not in service.analyze.call_args.args[0]:
            raise RuntimeError('Packaged MONAI processing is unavailable.')
        app.button(key='play_0').click().run()
        if app.exception or len(app.get('audio')) != 2:
            raise RuntimeError('Packaged report audio smoke check failed.')