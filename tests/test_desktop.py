import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from helpers import synthetic_dicom  # noqa: F401  (sets up import path)
from desktop.i18n import device_locale, language, select_language
from monai_gemini.prompt import DEFAULT_PROMPT, build_prompt


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
        with patch.dict(os.environ, {}):
            os.environ.pop('DICOM_DEVICE_LANGUAGE', None)
            actual = device_locale()
            self.assertTrue(actual)
            self.assertEqual(language(), select_language(actual))

    def test_language_follows_the_device(self):
        with patch.dict(os.environ, {}, clear=True), patch('desktop.i18n.device_locale', return_value='ar-EG'):
            self.assertEqual(language(), 'ar')
        with patch.dict(os.environ, {}, clear=True), patch('desktop.i18n.device_locale', return_value='de-DE'):
            self.assertEqual(language(), 'en')

    def test_english_prompt_preserves_measurements(self):
        with patch.dict(os.environ, {'DICOM_DEVICE_LANGUAGE': 'es-ES'}):
            prompt = build_prompt('mean=0.125; 12 mm', 'CHEST', ('scan.txt',))
            self.assertIn('mean=0.125; 12 mm', prompt)
            self.assertIn('never provide a definitive or conclusive automated diagnosis', prompt)
            self.assertIn('every conversation reply in English', prompt)
        with patch.dict(os.environ, {'DICOM_DEVICE_LANGUAGE': 'ar'}):
            self.assertEqual(build_prompt('12 mm'), DEFAULT_PROMPT.format(monai_report='12 mm', user_text_or_voice_input='لا توجد مدخلات إضافية.', uploaded_files_context='لا توجد ملفات إضافية.'))



if __name__ == '__main__':
    unittest.main()
