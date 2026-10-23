"""Mount this panel after the existing MONAI pipeline finishes; no MONAI changes."""
import hashlib
import io
import mimetypes
import streamlit as st
from .service import Attachment, GeminiService, MODEL_SLOTS, ServiceError

try:
    from gtts import gTTS
    GTTS_OK = True
except Exception:
    GTTS_OK = False

try:
    # Browser speech recognition: text arrives directly without saving a recording.
    from streamlit_mic_recorder import speech_to_text
    STT_OK = True
except Exception:
    STT_OK = False


def gtts_mp3(text: str) -> bytes | None:
    """Same gTTS library used for the MONAI report."""
    if not GTTS_OK or not text.strip():
        return None
    try:
        buf = io.BytesIO()
        gTTS(text=text, lang="ar").write_to_fp(buf)
        return buf.getvalue()
    except Exception:
        return None


def model_title(label: str) -> str:
    return "Google Gemini " + label.removeprefix("Gemini ").strip()


def render_gemini_panel(monai_report: str, monai_audio_mp3: bytes | None = None, show_monai_player: bool = True) -> None:
    if not monai_report.strip():
        st.info("لم يصدر تقرير MONAI بعد.")
        return
    report_key = hashlib.sha256(monai_report.encode()).hexdigest()
    if st.session_state.get("mg_report_key") != report_key:
        for key in tuple(st.session_state):
            if key.startswith("mg_"):
                del st.session_state[key]
        st.session_state["mg_report_key"] = report_key
    if show_monai_player and monai_audio_mp3:
        st.subheader("صوت تقرير MONAI الهندسي")
        st.audio(monai_audio_mp3, format="audio/mpeg")
        st.download_button("تنزيل صوت MONAI", monai_audio_mp3, "monai-report.mp3", "audio/mpeg", key="mg_monai_download")
    try:
        import os
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            try:
                key = st.secrets.get("GEMINI_API_KEY")
            except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
                key = None
        service = GeminiService(api_key=key)
    except ServiceError as error:
        st.error(str(error))
        return
    try:
        if "mg_available" not in st.session_state:
            try:
                st.session_state.mg_available = service.available_models()
            except ServiceError as error:
                st.error(str(error))
                if st.button("إعادة المحاولة", key="mg_retry_models"):
                    st.rerun()
                return

        # ---------- القسم الثاني: تقرير الذكاء الاصطناعي ----------
        st.divider()
        st.header("تقرير الذكاء الاصطناعي")
        report_area = st.container()

        # ---------- القسم الثالث: أضف سؤالاً حول هذا التقرير ----------
        st.divider()
        st.header("أضف سؤالاً حول هذا التقرير")
        label = st.selectbox("النموذج", list(MODEL_SLOTS), format_func=model_title, key="mg_model_label")
        try:
            model = service.resolve_model(label, st.session_state.mg_available)
            configured = True
        except ServiceError as error:
            st.warning(str(error))
            model, configured = "", False
        chat_area = st.container()
        uploads = st.file_uploader("الملفات الإضافية", type=["pdf", "txt", "csv", "json", "jpg", "jpeg", "png", "webp"], accept_multiple_files=True, key="mg_files")
        if STT_OK:
            st.caption("اضغط زر التحدث وتكلم؛ يظهر كلامك نصاً في المربع مباشرة ويمكنك تعديله.")
            spoken = speech_to_text(language="ar", start_prompt="🎤 ابدأ التحدث", stop_prompt="⏹ إيقاف التحدث", just_once=True, key="mg_stt")
            if spoken:
                current = st.session_state.get("mg_notes", "").strip()
                st.session_state.mg_notes = (current + " " + spoken).strip() if current else spoken
        else:
            st.caption("خاصية التحدث غير مثبتة على الخادم؛ اكتب سؤالك في المربع.")
        notes = st.text_area("سؤالك أو النص المنطوق", key="mg_notes", height=160)
        send = st.button("إرسال", disabled=not configured, key="mg_send")

        automatic = not notes.strip() and not uploads and not st.session_state.get("mg_auto_attempted")
        if configured and (send or automatic):
            files = tuple(Attachment(f.name, mimetypes.guess_type(f.name)[0] or f.type or "application/octet-stream", f.getvalue()) for f in uploads)
            first = not st.session_state.get("mg_analysis")
            if automatic:
                # At most one automatic attempt per report, including failures.
                st.session_state.mg_auto_attempted = True
            context = monai_report if first else monai_report + "\n\n[تقرير الذكاء الاصطناعي السابق]:\n" + st.session_state.mg_analysis
            try:
                with st.spinner("جارٍ التحليل…"):
                    result = service.analyze(context, model, notes, files)
                with st.spinner("جارٍ توليد الصوت…"):
                    audio = gtts_mp3(result)
                if first:
                    st.session_state.mg_analysis = result
                    st.session_state.mg_ai_audio = audio
                else:
                    st.session_state.mg_messages = [
                        *st.session_state.get("mg_messages", []),
                        {"role": "user", "text": notes.strip() or "سؤال حول التقرير", "files": [f.name for f in files]},
                        {"role": "assistant", "text": result, "audio": audio},
                    ]
            except (ServiceError, ValueError) as error:
                st.error(str(error))

        with report_area:
            if st.session_state.get("mg_analysis"):
                st.markdown(st.session_state.mg_analysis)
                st.download_button("تنزيل التقرير النصي", st.session_state.mg_analysis.encode("utf-8"), "ai-report.txt", "text/plain", key="mg_text_download")
                if st.session_state.get("mg_ai_audio"):
                    st.subheader("صوت تقرير الذكاء الاصطناعي")
                    st.audio(st.session_state.mg_ai_audio, format="audio/mpeg")
                    st.download_button("تنزيل صوت تقرير الذكاء الاصطناعي", st.session_state.mg_ai_audio, "ai-report.mp3", "audio/mpeg", key="mg_ai_download")
                else:
                    st.caption("تعذر توليد الصوت عبر gTTS حالياً.")
            else:
                st.info("لم يصدر تقرير الذكاء الاصطناعي بعد.")

        with chat_area:
            for i, message in enumerate(st.session_state.get("mg_messages", [])):
                with st.chat_message(message["role"]):
                    st.markdown(message["text"])
                    if message.get("files"):
                        st.caption("، ".join(message["files"]))
                    if message.get("audio"):
                        st.audio(message["audio"], format="audio/mpeg")
                        st.download_button("تنزيل صوت الرد", message["audio"], f"ai-reply-{i}.mp3", "audio/mpeg", key=f"mg_reply_dl_{i}")
    finally:
        service.close()
