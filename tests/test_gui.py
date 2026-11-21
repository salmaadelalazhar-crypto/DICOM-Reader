import os
import unittest
from unittest.mock import patch

from helpers import qt_app, synthetic_dicom, wait_until


class DesktopWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def setUp(self):
        p = patch.dict(os.environ, {'DICOM_DEVICE_LANGUAGE': 'en-US', 'GEMINI_API_KEY': 'unit-test-only'})
        p.start()
        self.addCleanup(p.stop)

    def service(self, factory, replies):
        service = factory.return_value
        service.available_models.return_value = {'gemini-3.5-flash-lite'}
        service.resolve_model.return_value = 'gemini-3.5-flash-lite'
        service.analyze.side_effect = replies
        return service

    def test_upload_report_auto_ai_question_and_audio(self):
        from gui.main_window import MainWindow
        from gui.result_view import ResultView
        from gui.widgets import AudioPlayer
        with patch('gui.gemini_panel.GeminiPanel.service_factory') as factory, \
                patch('gtts.gTTS.write_to_fp', side_effect=lambda fp: fp.write(b'mp3')):
            service = self.service(factory, ['English report', 'English reply'])
            w = MainWindow()
            w.load_bytes('case.dcm', synthetic_dicom())
            wait_until(lambda: w.gemini.conversation and w.gemini.conversation.analysis and not w.gemini.busy)
            # One automatic request with the default prompt, no notes.
            self.assertEqual(service.analyze.call_count, 1)
            self.assertEqual(service.analyze.call_args.args[2], '')
            self.assertEqual(w.gemini.conversation.ai_audio, b'mp3')
            view = w.findChild(ResultView)
            view.play_btn.click()
            wait_until(lambda: len(w.findChildren(AudioPlayer)) == 2)
            w.gemini.notes.setPlainText('Explain 12 mm')
            w.gemini.send_btn.click()
            wait_until(lambda: len(w.gemini.conversation.messages) == 2 and not w.gemini.busy)
            self.assertEqual(service.analyze.call_args.args[2], 'Explain 12 mm')
            self.assertIn('[Previous artificial intelligence report]', service.analyze.call_args.args[0])
            self.assertEqual(w.gemini.conversation.messages[1].audio, b'mp3')
            self.assertEqual(w.gemini.notes.toPlainText(), '')
            w.close()

    def test_batch_source_switch_starts_a_new_conversation(self):
        import io, zipfile
        from gui.main_window import MainWindow
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as z:
            z.writestr('first.dcm', synthetic_dicom())
            z.writestr('second.dcm', synthetic_dicom(rows=12, cols=10))
        with patch('gui.gemini_panel.GeminiPanel.service_factory') as factory, \
                patch('gtts.gTTS.write_to_fp', side_effect=lambda fp: fp.write(b'mp3')):
            service = self.service(factory, ['first analysis', 'second analysis'])
            w = MainWindow()
            w.load_bytes('batch.zip', buffer.getvalue())
            wait_until(lambda: w.gemini.conversation and w.gemini.conversation.analysis and not w.gemini.busy)
            self.assertIn('first.dcm', service.analyze.call_args.args[0])
            w.source_box.setCurrentIndex(1)
            wait_until(lambda: service.analyze.call_count == 2 and w.gemini.conversation.analysis)
            self.assertIn('second.dcm', service.analyze.call_args.args[0])
            self.assertEqual(w.gemini.conversation.analysis, 'second analysis')
            w.close()

    def test_without_key_the_setup_screen_is_shown(self):
        from gui.api_key_setup import ApiKeySetup
        from gui.main_window import MainWindow
        with patch.dict(os.environ, {'GEMINI_API_KEY': ''}), patch('desktop.api_key.load_api_key', return_value=None):
            w = MainWindow()
            self.assertIsNotNone(w.findChild(ApiKeySetup))
            w.close()

    def test_model_list_failure_offers_retry(self):
        from gui.main_window import MainWindow
        from monai_gemini.service import ServiceError
        with patch('gui.gemini_panel.GeminiPanel.service_factory') as factory:
            factory.return_value.available_models.side_effect = ServiceError('models failed')
            w = MainWindow()
            w.load_bytes('case.dcm', synthetic_dicom())
            from PySide6.QtWidgets import QLabel
            wait_until(lambda: any(l.text() == 'models failed' for l in w.findChildren(QLabel)))
            w.close()

    def test_smoke_check_used_by_the_exe(self):
        from desktop.verification import verify_app
        verify_app(require_monai=False)


if __name__ == '__main__':
    unittest.main()
