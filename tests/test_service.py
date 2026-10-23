import os
import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
from monai_gemini.prompt import build_prompt
from monai_gemini.service import Attachment, DEFAULT_MODELS, GeminiService, MODEL_SLOTS, ServiceError
from monai_gemini.ui import model_title


class ServiceTests(unittest.TestCase):
    def make_service(self):
        with patch("monai_gemini.service.genai.Client") as constructor:
            service = GeminiService(api_key="unit-test-only")
            return service, constructor.return_value

    def test_default_report_without_extra_inputs(self):
        prompt = build_prompt("الحجم: 12 مل")
        self.assertIn("الحجم: 12 مل", prompt)
        self.assertIn("لا توجد مدخلات إضافية.", prompt)
        self.assertIn("لا توجد ملفات إضافية.", prompt)

    def test_no_definitive_diagnosis_instruction(self):
        self.assertIn("يُمنع منعاً باتاً تقديم أي تشخيص آلي نهائي أو قاطع", build_prompt("تقرير"))

    def test_deep_analysis_instruction(self):
        self.assertIn("قم بتقديم تحليل تفصيلي وعميق للبيانات", build_prompt("تقرير"))

    def test_single_integrated_request(self):
        service, client = self.make_service()
        client.models.generate_content.return_value = NS(text="تحليل")
        attachment = Attachment("data.txt", "text/plain", b"12 ml")
        self.assertEqual(service.analyze("MONAI 12", "real-model", "سؤال صوتي معدل", (attachment,)), "تحليل")
        client.models.generate_content.assert_called_once()
        parts = client.models.generate_content.call_args.kwargs["contents"][0].parts
        self.assertIn("MONAI 12", parts[0].text)
        self.assertIn("سؤال صوتي معدل", parts[0].text)
        self.assertIn("data.txt", parts[0].text)
        self.assertEqual(parts[1].inline_data.data, b"12 ml")

    def test_no_invented_model_alias(self):
        service, _ = self.make_service()
        with patch.dict(os.environ, {"GEMINI_MODEL_35_FLASH_LITE": ""}):
            with self.assertRaises(ServiceError):
                service.resolve_model("Gemini 3.5 Flash-Lite", {"gemini-2.5-flash"})

    def test_requested_models_use_official_ids_by_default(self):
        service, _ = self.make_service()
        expected = {
            "Gemini 3.5 Flash-Lite": "gemini-3.5-flash-lite",
            "Gemini 3.6 Flash": "gemini-3.6-flash",
        }
        with patch.dict(os.environ, {}, clear=True):
            for label, model in expected.items():
                with self.subTest(label=label):
                    self.assertEqual(service.resolve_model(label, set(expected.values())), model)

    def test_selected_model_is_preserved(self):
        service, _ = self.make_service()
        with patch.dict(os.environ, {"GEMINI_MODEL_36_FLASH": "models/actual-model"}):
            self.assertEqual(service.resolve_model("Gemini 3.6 Flash", {"actual-model"}), "actual-model")

    def test_3_8_flash_is_removed_from_the_list(self):
        self.assertNotIn("Gemini 3.8 Flash", MODEL_SLOTS)
        self.assertNotIn("Gemini 3.8 Flash", DEFAULT_MODELS)
        self.assertEqual(list(MODEL_SLOTS), ["Gemini 3.5 Flash-Lite", "Gemini 3.6 Flash"])

    def test_dropdown_names_carry_google_gemini_prefix(self):
        self.assertEqual(model_title("Gemini 3.5 Flash-Lite"), "Google Gemini 3.5 Flash-Lite")
        self.assertEqual(model_title("Gemini 3.6 Flash"), "Google Gemini 3.6 Flash")

    def test_provider_errors_are_not_exposed(self):
        service, client = self.make_service()
        client.models.generate_content.side_effect = RuntimeError("private-provider-details")
        with self.assertRaises(ServiceError) as raised:
            service.analyze("تقرير", "model")
        self.assertNotIn("private-provider-details", str(raised.exception))
        self.assertIsNone(raised.exception.__cause__)
        self.assertTrue(raised.exception.__suppress_context__)

    def test_transcription_returns_editable_text(self):
        service, client = self.make_service()
        client.models.generate_content.return_value = NS(text="النص المنطوق")
        self.assertEqual(service.transcribe(b"audio", "audio/wav", "model"), "النص المنطوق")

    def test_real_mp3_encoding(self):
        service, client = self.make_service()
        audio = NS(data=b"\x00\x00" * 24000, mime_type="audio/L16;codec=pcm;rate=24000")
        client.models.generate_content.return_value = NS(candidates=[NS(content=NS(parts=[NS(inline_data=audio)]))])
        mp3 = service.speech_mp3("تحليل التقرير")
        self.assertGreater(len(mp3), 100)
        self.assertNotEqual(mp3[:4], b"RIFF")
        self.assertTrue(mp3.startswith(b"ID3") or mp3[0] == 255)

    def test_empty_monai_report_is_rejected(self):
        service, client = self.make_service()
        with self.assertRaises(ValueError):
            service.analyze("   ", "model")
        client.models.generate_content.assert_not_called()


if __name__ == "__main__":
    unittest.main()
