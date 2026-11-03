"""Native microphone bridge: recognition stays direct, without saved recordings."""
import threading
import uuid


class SpeechBridge:
    def __init__(self):
        self._lock = threading.Lock()
        self._stop = None
        self._generation = 0
        self._results = []
        self._error = ''

    def start_speech(self, language):
        import speech_recognition as sr
        self.stop_speech()
        recognizer = sr.Recognizer()
        recognizer.operation_timeout = 20
        locale = 'ar-SA' if language == 'ar' else 'en-US'
        try:
            microphone = sr.Microphone()
            with microphone as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.4)
            with self._lock:
                generation = self._generation
                self._error = ''
            def callback(engine, audio):
                try:
                    text = engine.recognize_google(audio, language=locale)
                    with self._lock:
                        if generation == self._generation:
                            self._results.append({'id': uuid.uuid4().hex, 'text': text})
                except sr.UnknownValueError:
                    pass
                except Exception:
                    with self._lock:
                        self._error = 'تعذر تحويل الكلام إلى نص.' if language == 'ar' else 'Unable to transcribe speech.'
            self._stop = recognizer.listen_in_background(microphone, callback, phrase_time_limit=15)
            return {'ok': True}
        except Exception:
            return {'ok': False, 'error': 'تحقق من الميكروفون وإذن الوصول إليه في ويندوز.' if language == 'ar' else 'Check your microphone and Windows microphone permission.'}

    def poll_speech(self):
        with self._lock:
            items, self._results = self._results, []
            error, self._error = self._error, ''
        return {'items': items, 'error': error}

    def stop_speech(self):
        if self._stop:
            self._stop(wait_for_stop=False)
            self._stop = None
        with self._lock:
            self._generation += 1
        return True
