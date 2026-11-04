import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from desktop.speech import SpeechBridge


class SpeechTests(unittest.TestCase):
    def test_recognition_locale_and_returned_editable_text(self):
        for language, locale in [('ar', 'ar-SA'), ('en', 'en-US')]:
            with self.subTest(language=language):
                engine = Mock()
                engine.recognize_google.return_value = 'spoken text'
                callbacks = []
                engine.listen_in_background.side_effect = lambda mic, callback, **kwargs: callbacks.append(callback) or Mock()
                microphone = Mock()
                microphone.__enter__ = Mock(return_value=microphone)
                microphone.__exit__ = Mock(return_value=False)
                module = SimpleNamespace(Recognizer=lambda: engine, Microphone=lambda: microphone, UnknownValueError=ValueError)
                with patch.dict('sys.modules', {'speech_recognition': module}):
                    bridge = SpeechBridge()
                    self.assertTrue(bridge.start_speech(language)['ok'])
                    callbacks[0](engine, b'ephemeral-audio')
                    engine.recognize_google.assert_called_once_with(b'ephemeral-audio', language=locale)
                    self.assertEqual(bridge.poll_speech()['items'][0]['text'], 'spoken text')
                    self.assertEqual(bridge.poll_speech()['items'], [])
                    bridge.stop_speech()


if __name__ == '__main__':
    unittest.main()