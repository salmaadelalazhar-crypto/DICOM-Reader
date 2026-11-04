import ast
import io
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pandas as pd
import pydicom
import torch
from monai.transforms import Compose, EnsureChannelFirst, ScaleIntensity, ToTensor
from openpyxl import load_workbook
from streamlit.testing.v1 import AppTest

from desktop.i18n import device_locale, is_arabic, language, select_language, tr
from desktop.runtime import child_command
from monai_gemini.prompt import DEFAULT_PROMPT, build_prompt
from test_original_integration import synthetic_dicom, Upload

ROOT = Path(__file__).resolve().parents[1]


def processing():
    wanted = {'safe', 'read_dicom', 'to_2d', 'monai_analysis', 'level',
              'build_report', 'build_excel', 'analyze_one', 'build_batch_excel'}
    tree = ast.parse((ROOT / 'app.py').read_text(encoding='utf-8'))
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in wanted]
    scope = dict(io=io, np=np, pd=pd, pydicom=pydicom, torch=torch, Compose=Compose,
                 EnsureChannelFirst=EnsureChannelFirst, ScaleIntensity=ScaleIntensity,
                 ToTensor=ToTensor, MONAI_OK=True, tr=tr, is_arabic=is_arabic,
                 MODALITY_AR={'CT': tr('أشعة مقطعية (CT)')})
    exec(compile(ast.Module(body=nodes, type_ignores=[]), 'processing', 'exec'), scope)
    return scope


class DesktopTests(unittest.TestCase):
    def test_arabic_devices_use_arabic(self):
        for locale in ['ar', 'ar-EG', 'ar_SA']:
            with self.subTest(locale=locale):
                self.assertEqual(select_language(locale), 'ar')

    def test_english_devices_use_english(self):
        self.assertEqual(select_language('en-US'), 'en')

    def test_other_devices_default_to_english(self):
        for locale in ['es-ES', 'fr-FR', 'zh-CN', '', None]:
            with self.subTest(locale=locale):
                self.assertEqual(select_language(locale), 'en')

    def test_windows_display_language_api(self):
        def fill_buffer(lang_id, buffer, length, flags):
            self.assertEqual(lang_id, 0x0C01)
            buffer.value = 'ar-EG'
            return 6
        kernel = SimpleNamespace(GetUserDefaultUILanguage=lambda: 0x0C01,
                                 LCIDToLocaleName=fill_buffer)
        with patch('desktop.i18n.sys.platform', 'win32'), patch('desktop.i18n.ctypes.windll', SimpleNamespace(kernel32=kernel), create=True):
            self.assertEqual(device_locale(), 'ar-EG')

    @unittest.skipUnless(sys.platform == 'win32', 'Real Windows API requires Windows')
    def test_real_windows_locale_without_override(self):
        with patch.dict(os.environ, {'DICOM_DESKTOP': '1'}):
            os.environ.pop('DICOM_DEVICE_LANGUAGE', None)
            actual = device_locale()
            self.assertTrue(actual)
            self.assertEqual(language(), select_language(actual))

    def test_cloud_keeps_original_language(self):
        with patch.dict(os.environ, {}, clear=True), patch('desktop.i18n.device_locale', return_value='en-US'):
            self.assertEqual(language(), 'ar')

    def test_frozen_child_reenters_explicit_worker(self):
        with patch('desktop.runtime.sys.frozen', True, create=True), patch('desktop.runtime.sys.executable', 'DICOMReader.exe'):
            self.assertEqual(child_command(8509), ['DICOMReader.exe', '--streamlit-worker', '8509'])

    def test_english_prompt_preserves_measurements(self):
        with patch.dict(os.environ, {'DICOM_DEVICE_LANGUAGE': 'es-ES'}):
            prompt = build_prompt('mean=0.125; 12 mm', 'CHEST', ('scan.txt',))
            self.assertIn('mean=0.125; 12 mm', prompt)
            self.assertIn('never provide a definitive or conclusive automated diagnosis', prompt)
            self.assertIn('every conversation reply in English', prompt)
        with patch.dict(os.environ, {'DICOM_DEVICE_LANGUAGE': 'ar'}):
            self.assertEqual(build_prompt('12 mm'), DEFAULT_PROMPT.format(monai_report='12 mm', user_text_or_voice_input='لا توجد مدخلات إضافية.', uploaded_files_context='لا توجد ملفات إضافية.'))

    def test_localization_does_not_change_dicom_numeric_processing(self):
        results = []
        for locale in ['ar-EG', 'en-US', 'es-ES']:
            with patch.dict(os.environ, {'DICOM_DEVICE_LANGUAGE': locale}):
                scope = processing()
                result = scope['analyze_one']('case.dcm', synthetic_dicom())
                self.assertEqual(result[1]['norm'].shape, (16, 16))
                self.assertEqual(result[0][tr('عدد الصفوف')], '16')
                book = load_workbook(io.BytesIO(scope['build_excel'](*result)))
                self.assertEqual(book.sheetnames, [tr('البيانات التقنية'), tr('التحليل الهيكلي'), tr('التقرير')])
                self.assertEqual(book.worksheets[0].sheet_view.rightToLeft, locale.startswith('ar'))
                self.assertEqual(scope['build_batch_excel']([result])[:2], b'PK')
                results.append(result[1])
        for result in results[1:]:
            for key, value in results[0].items():
                if key == 'norm':
                    np.testing.assert_array_equal(value, result[key])
                else:
                    self.assertEqual(value, result[key])

    def test_english_upload_report_chat_and_audio(self):
        original = __import__('streamlit').file_uploader
        def uploader(label, *args, **kwargs):
            if kwargs.get('key') != 'mg_files':
                return Upload(synthetic_dicom(), 'case.dcm')
            return original(label, *args, **kwargs)
        with patch.dict(os.environ, {'DICOM_DEVICE_LANGUAGE': 'en-US', 'GEMINI_API_KEY': 'test-only-fake-key'}), patch('streamlit.file_uploader', side_effect=uploader), patch('monai_gemini.ui.GeminiService') as cls, patch('gtts.gTTS.write_to_fp', side_effect=lambda fp: fp.write(b'mp3')):
            service = cls.return_value
            service.available_models.return_value = {'gemini-3.5-flash-lite'}
            service.resolve_model.return_value = 'gemini-3.5-flash-lite'
            service.analyze.side_effect = ['English report', 'English reply']
            app = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=60).run()
            self.assertEqual(len(app.exception), 0)
            self.assertIn('MONAI + PyTorch', service.analyze.call_args.args[0])
            self.assertEqual(app.session_state['mg_ai_audio'], b'mp3')
            app.button(key='play_0').click().run()
            self.assertEqual(len(app.get('audio')), 2)
            app.text_area(key='mg_notes').input('Explain 12 mm')
            app.button(key='mg_send').click().run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(service.analyze.call_args.args[2], 'Explain 12 mm')
            self.assertEqual(app.session_state['mg_messages'][1]['audio'], b'mp3')


if __name__ == '__main__':
    unittest.main()
