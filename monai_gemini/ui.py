"""Mount this panel after the existing MONAI pipeline finishes; no MONAI changes."""
import hashlib
import mimetypes
import streamlit as st
from .service import Attachment, GeminiService, MODEL_SLOTS, ServiceError


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
    st.header("التحليل المساعد")
    if show_monai_player and monai_audio_mp3:
        st.subheader("صوت تقرير MONAI الهندسي")
        st.audio(monai_audio_mp3, format="audio/mpeg")
        st.download_button("تنزيل صوت MONAI", monai_audio_mp3, "monai-report.mp3", "audio/mpeg", key="mg_monai_download")
    elif show_monai_player:
        st.caption("لم تُمرَّر نسخة MP3 من التقرير الهندسي.")
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
        with st.sidebar:
            st.subheader("المحادثة والمرفقات")
            label = st.selectbox("النموذج", list(MODEL_SLOTS), key="mg_model_label")
            if label == "Gemini 3.7 Flash":
                st.warning("أوقفت Google إصدار 3.7 وتحول طلباته تلقائياً إلى 3.8.")
            try:
                model = service.resolve_model(label, st.session_state.mg_available)
                configured = True
            except ServiceError as error:
                st.warning(str(error))
                model, configured = "", False
            uploads = st.file_uploader("الملفات الإضافية", type=["pdf", "txt", "csv", "json", "jpg", "jpeg", "png", "webp"], accept_multiple_files=True, key="mg_files")
            recording = st.audio_input("الإدخال الصوتي", key="mg_recording")
            if st.button("تحويل التسجيل إلى نص", disabled=not recording or not configured, key="mg_transcribe"):
                try:
                    with st.spinner("جارٍ تحويل التسجيل…"):
                        st.session_state.mg_notes = service.transcribe(recording.getvalue(), recording.type or "audio/wav", model)
                except ServiceError as error:
                    st.error(str(error))
            notes = st.text_area("ملاحظاتك أو النص المنطوق", key="mg_notes", height=180)
            send = st.button("إرسال التقرير والملاحظات والمرفقات", disabled=not configured, key="mg_send")
        automatic = not notes.strip() and not uploads and not st.session_state.get("mg_auto_attempted")
        if configured and (send or automatic):
            if automatic:
                # At most one automatic attempt per report, including failures.
                st.session_state.mg_auto_attempted = True
            files = tuple(Attachment(f.name, mimetypes.guess_type(f.name)[0] or f.type or "application/octet-stream", f.getvalue()) for f in uploads)
            try:
                with st.spinner("جارٍ تحليل تقرير MONAI…"):
                    result = service.analyze(monai_report, model, notes, files)
                st.session_state.mg_analysis = result
                st.session_state.mg_messages = [*st.session_state.get("mg_messages", []), {"role": "user", "text": notes.strip() or "تحليل تقرير MONAI", "files": [f.name for f in files]}, {"role": "assistant", "text": result}]
                st.session_state.pop("mg_ai_audio", None)
            except (ServiceError, ValueError) as error:
                st.error(str(error))
        if st.session_state.get("mg_analysis"):
            st.subheader("تقرير Gemini")
            st.markdown(st.session_state.mg_analysis)
            st.download_button("تنزيل التقرير النصي", st.session_state.mg_analysis.encode("utf-8"), "gemini-report.txt", "text/plain", key="mg_text_download")
            st.subheader("صوت تقرير Gemini")
            if st.button("توليد صوت تقرير Gemini", key="mg_tts"):
                try:
                    with st.spinner("جارٍ توليد الصوت…"):
                        st.session_state.mg_ai_audio = service.speech_mp3(st.session_state.mg_analysis)
                except ServiceError as error:
                    st.error(str(error))
            if st.session_state.get("mg_ai_audio"):
                st.audio(st.session_state.mg_ai_audio, format="audio/mpeg")
                st.download_button("تنزيل صوت Gemini", st.session_state.mg_ai_audio, "gemini-report.mp3", "audio/mpeg", key="mg_ai_download")
        with st.sidebar:
            for message in st.session_state.get("mg_messages", []):
                with st.chat_message(message["role"]):
                    st.markdown(message["text"])
                    if message.get("files"):
                        st.caption("، ".join(message["files"]))
    finally:
        service.close()
