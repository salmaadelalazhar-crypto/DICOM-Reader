# -*- coding: utf-8 -*-
"""
قارئ الأشعة الطبية DICOM - منصة ميسّرة للأطباء وذوي الإعاقة البصرية
التشغيل: streamlit run app.py
"""
import io
from desktop.i18n import tr, language, is_arabic
import json
import hashlib
from monai_gemini.ui import render_gemini_panel
from datetime import datetime

import numpy as np
import pandas as pd
import pydicom
import streamlit as st
import streamlit.components.v1 as components

try:
    import torch
    from monai.transforms import Compose, EnsureChannelFirst, ScaleIntensity, ToTensor
    MONAI_OK = True
except Exception:  # يعمل التطبيق حتى لو تعذّر تحميل MONAI
    MONAI_OK = False

try:
    from gtts import gTTS
    GTTS_OK = True
except Exception:
    GTTS_OK = False

st.set_page_config(page_title=tr('قارئ أشعة DICOM الميسّر'), page_icon="🩻", layout="wide")

# ---------- تنسيق عربي واضح وعالي التباين ----------
st.markdown(
    """
    <style>
    html, body, [class*="css"], .stMarkdown, .stButton, label { direction: APP_DIRECTION; text-align: APP_ALIGN; font-size: 1.1rem; }
    .stButton>button, .stDownloadButton>button {
        font-size: 1.2rem; font-weight: 700; padding: .7rem 1.4rem; border-radius: 10px;
        border: 3px solid #0b5394; }
    .stDownloadButton>button { background:#0b6e3a; color:#fff; border-color:#064d28; }
    .stButton>button:focus, .stDownloadButton>button:focus { outline: 4px solid #ffbf00; }
    .report { background:#f5f9ff; border-right:6px solid #0b5394; padding:1rem 1.2rem; border-radius:8px; line-height:2; color:#111; }
    </style>
    """.replace("APP_DIRECTION", "rtl" if is_arabic() else "ltr").replace("APP_ALIGN", "right" if is_arabic() else "left"),
    unsafe_allow_html=True,
)

st.title(tr('🩻 قارئ ومفسّر ملفات الأشعة الطبية (DICOM)'))
st.markdown(
    tr('مرحبًا بك. **الخطوة الأولى:** ارفع ملف أشعة بامتداد \u200e.dcm\u200e. **الخطوة الثانية:** اقرأ التقرير أو اضغط زر الاستماع. **الخطوة الثالثة:** نزّل التقرير الكامل بصيغة Excel. جميع الأزرار مُعنونة نصيًا ومتوافقة مع قارئات الشاشة ويمكن التنقل بينها بمفتاح Tab.')
)
st.warning(tr('تنبيه: هذا التحليل آلي وصفي للمساعدة فقط، ولا يُغني عن تشخيص الطبيب المختص.'))


# ---------- دوال المعالجة ----------
def safe(ds, tag, default=tr('غير متوفر')):
    v = getattr(ds, tag, None)
    if v is None or str(v).strip() == "":
        return default
    return str(v)


MODALITY_AR = {
    "CT": tr('أشعة مقطعية (CT)'), "MR": tr('رنين مغناطيسي (MRI)'), "CR": tr('أشعة سينية محوسبة (CR)'),
    "DX": tr('أشعة سينية رقمية (DX)'), "US": tr('موجات فوق صوتية (US)'), "MG": tr('تصوير الثدي (Mammography)'),
    "PT": tr('تصوير مقطعي بالإصدار البوزيتروني (PET)'), "NM": tr('طب نووي (NM)'), "XA": tr('تصوير الأوعية (XA)'),
}


def read_dicom(file_bytes):
    ds = pydicom.dcmread(io.BytesIO(file_bytes), force=True)
    arr = ds.pixel_array.astype(np.float32)
    slope = float(getattr(ds, "RescaleSlope", 1) or 1)
    intercept = float(getattr(ds, "RescaleIntercept", 0) or 0)
    arr = arr * slope + intercept
    return ds, arr


def to_2d(arr):
    """يأخذ شريحة وسطى للعرض إذا كانت الصورة متعددة الشرائح أو ملونة."""
    if arr.ndim == 3 and arr.shape[-1] in (3, 4):
        return arr[..., :3].mean(axis=-1)
    if arr.ndim == 3:
        return arr[arr.shape[0] // 2]
    if arr.ndim == 4:
        return arr[arr.shape[0] // 2].mean(axis=-1)
    return arr


def monai_analysis(img2d):
    """تحليل هيكلي ونسيجي وهندسي باستخدام MONAI + PyTorch."""
    if MONAI_OK:
        pipe = Compose([EnsureChannelFirst(channel_dim="no_channel"), ScaleIntensity(minv=0.0, maxv=1.0), ToTensor()])
        t = pipe(img2d.copy())
        t = torch.as_tensor(t, dtype=torch.float32)[0]
        engine = "MONAI + PyTorch"
    else:
        rng = img2d.max() - img2d.min()
        t = (img2d - img2d.min()) / (rng if rng else 1)
        engine = tr('NumPy (احتياطي - MONAI غير مثبتة)')
    x = np.asarray(t, dtype=np.float32)

    mean, std = float(x.mean()), float(x.std())
    p5, p50, p95 = np.percentile(x, [5, 50, 95])
    contrast_michelson = float((x.max() - x.min()) / (x.max() + x.min() + 1e-8))
    hist, _ = np.histogram(x, bins=64, range=(0, 1))
    pr = hist / hist.sum()
    entropy = float(-(pr[pr > 0] * np.log2(pr[pr > 0])).sum())
    gy, gx = np.gradient(x)
    grad = np.sqrt(gx ** 2 + gy ** 2)
    edge_density = float((grad > grad.mean() + 2 * grad.std()).mean())
    thr = float(x.mean())
    mask = x > thr
    fg_ratio = float(mask.mean())
    if mask.any():
        ys, xs = np.nonzero(mask)
        bbox = (int(ys.min()), int(xs.min()), int(ys.max()), int(xs.max()))
        cy, cx = float(ys.mean()), float(xs.mean())
    else:
        bbox, cy, cx = (0, 0, 0, 0), 0.0, 0.0
    h, w = x.shape
    left, right = x[:, : w // 2], np.fliplr(x[:, w - w // 2:])
    symmetry = float(1 - np.abs(left - right).mean())

    return {
        "engine": engine, "mean": mean, "std": std, "p5": float(p5), "median": float(p50), "p95": float(p95),
        "contrast": contrast_michelson, "entropy": entropy, "edge_density": edge_density,
        "fg_ratio": fg_ratio, "bbox": bbox, "centroid": (cy, cx), "symmetry": symmetry, "norm": x,
    }


def level(v, lo, hi, words=None):
    if words is None:
        words = (tr("منخفض"), tr("متوسط"), tr("مرتفع"))
    return words[0] if v < lo else (words[2] if v > hi else words[1])


def build_report(meta, a):
    lines = [
        tr('نوع الفحص: {v0}.', v0=meta[tr('نوع الجهاز')]),
        tr('الجزء المفحوص: {v0}.', v0=meta[tr('الجزء المفحوص')]),
        tr('أبعاد الصورة: {v0} صفًا في {v1} عمودًا، وعدد الشرائح {v2}.', v0=meta[tr('عدد الصفوف')], v1=meta[tr('عدد الأعمدة')], v2=meta[tr('عدد الشرائح')]),
        tr('متوسط شدة الإضاءة المعيارية {v0:.2f} من واحد، والانحراف المعياري {v1:.2f}، أي أن التباين النسيجي {v2}.', v0=a['mean'], v1=a['std'], v2=level(a['std'], 0.12, 0.25)),
        tr('درجة التباين العام {v0:.2f}، وهي درجة {v1}.', v0=a['contrast'], v1=level(a['contrast'], 0.4, 0.8)),
        tr('إنتروبيا الصورة {v0:.2f} بت، ما يدل على تعقيد نسيجي {v1}.', v0=a['entropy'], v1=level(a['entropy'], 3.5, 5.0)),
        tr('كثافة الحواف {v0:.1f} بالمئة، ما يشير إلى وضوح حدود بنيوية {v1}.', v0=a['edge_density'] * 100, v1=level(a['edge_density'], 0.02, 0.06)),
        tr('تشغل البنية الرئيسية الساطعة نحو {v0:.1f} بالمئة من مساحة الصورة.', v0=a['fg_ratio'] * 100),
        tr('درجة التماثل بين النصف الأيمن والأيسر {v0:.1f} بالمئة، وهو تماثل {v1}.', v0=a['symmetry'] * 100, v1=level(a['symmetry'], 0.8, 0.92, (tr('ضعيف'), tr('مقبول'), tr('جيد')))),
        tr('تم التحليل باستخدام: {v0}.', v0=a['engine']),
        tr('هذا وصف تقني آلي للمساعدة، ويجب مراجعته من قبل طبيب أشعة مختص.'),
    ]
    return lines


def tts_bytes(text):
    buf = io.BytesIO()
    gTTS(text=text, lang=language()).write_to_fp(buf)
    return buf.getvalue()


def browser_tts(text):
    """قارئ صوتي احتياطي مدمج في المتصفح (Web Speech API) يعمل دون إنترنت للخادم."""
    components.html(
        tr('\n        <div dir="rtl" style="font-family:sans-serif">\n          <button aria-label="تشغيل قراءة التقرير بصوت المتصفح" onclick="s()" style="font-size:18px;padding:10px 18px;margin:4px">🔊 قراءة بصوت المتصفح</button>\n          <button aria-label="إيقاف القراءة" onclick="speechSynthesis.cancel()" style="font-size:18px;padding:10px 18px;margin:4px">⏹ إيقاف</button>\n        </div>\n        <script>\n          function s(){ speechSynthesis.cancel(); const u=new SpeechSynthesisUtterance({v0}); u.lang=\'ar-SA\'; u.rate=0.95; speechSynthesis.speak(u); }\n        </script>\n        ', v0=json.dumps(text)),
        height=70,
    )


def build_excel(meta, a, report_lines):
    buf = io.BytesIO()
    meta_df = pd.DataFrame(list(meta.items()), columns=[tr('الحقل'), tr('القيمة')])
    stats = {
        tr('محرك التحليل'): a["engine"], tr('متوسط الشدة (0-1)'): round(a["mean"], 4),
        tr('الانحراف المعياري'): round(a["std"], 4), tr('المئين 5'): round(a["p5"], 4),
        tr('الوسيط'): round(a["median"], 4), tr('المئين 95'): round(a["p95"], 4),
        tr('درجة التباين (Michelson)'): round(a["contrast"], 4), tr('الإنتروبيا (بت)'): round(a["entropy"], 4),
        tr('كثافة الحواف'): round(a["edge_density"], 4), tr('نسبة البنية الرئيسية'): round(a["fg_ratio"], 4),
        tr('الإطار المحيط (y1,x1,y2,x2)'): str(a["bbox"]),
        tr('مركز الكتلة (y,x)'): f"({a['centroid'][0]:.1f}, {a['centroid'][1]:.1f})",
        tr('درجة التماثل'): round(a["symmetry"], 4),
    }
    stats_df = pd.DataFrame(list(stats.items()), columns=[tr('المؤشر'), tr('القيمة')])
    rep_df = pd.DataFrame({tr('رقم'): range(1, len(report_lines) + 1), tr('الوصف'): report_lines})
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        meta_df.to_excel(w, sheet_name=tr('البيانات التقنية'), index=False)
        stats_df.to_excel(w, sheet_name=tr('التحليل الهيكلي'), index=False)
        rep_df.to_excel(w, sheet_name=tr('التقرير'), index=False)
        for ws in w.sheets.values():
            ws.sheet_view.rightToLeft = is_arabic()
            for col in ws.columns:
                width = max(len(str(c.value or "")) for c in col) + 4
                ws.column_dimensions[col[0].column_letter].width = min(width, 90)
    return buf.getvalue()


MAX_MB = 200


def extract_dicoms_from_zip(zip_bytes):
    """يفك ضغط ملف ZIP في الذاكرة ويعيد قائمة (اسم الملف، محتواه) لكل ملفات DICOM بداخله."""
    import zipfile
    found = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for info in zf.infolist():
            if info.is_dir() or "__MACOSX" in info.filename:
                continue
            data = zf.read(info)
            name = info.filename.split("/")[-1]
            # نقبل ملفات .dcm أو الملفات بدون امتداد التي تحمل توقيع DICOM
            if name.lower().endswith(".dcm") or (len(data) > 132 and data[128:132] == b"DICM"):
                found.append((info.filename, data))
    return found


def analyze_one(name, data):
    ds, arr = read_dicom(data)
    img2d = to_2d(arr)
    analysis = monai_analysis(img2d)
    mod = safe(ds, "Modality")
    spacing = getattr(ds, "PixelSpacing", None)
    meta = {
        tr('اسم الملف'): name,
        tr('حجم الملف (كيلوبايت)'): f"{len(data) / 1024:.1f}",
        tr('نوع الجهاز'): MODALITY_AR.get(mod, mod),
        tr('الجزء المفحوص'): safe(ds, "BodyPartExamined"),
        tr('وصف الدراسة'): safe(ds, "StudyDescription"),
        tr('تاريخ الدراسة'): safe(ds, "StudyDate"),
        tr('الشركة المصنعة'): safe(ds, "Manufacturer"),
        tr('عدد الصفوف'): safe(ds, "Rows"),
        tr('عدد الأعمدة'): safe(ds, "Columns"),
        tr('عدد الشرائح'): safe(ds, "NumberOfFrames", "1"),
        tr('أبعاد المصفوفة'): str(tuple(arr.shape)),
        tr('المسافة بين البكسلات (مم)'): str(list(spacing)) if spacing else tr('غير متوفر'),
        tr('سماكة الشريحة (مم)'): safe(ds, "SliceThickness"),
        tr('البتات المخزنة'): safe(ds, "BitsStored"),
        tr('التفسير الضوئي'): safe(ds, "PhotometricInterpretation"),
        tr('أدنى قيمة بكسل'): f"{float(arr.min()):.1f}",
        tr('أعلى قيمة بكسل'): f"{float(arr.max()):.1f}",
    }
    return meta, analysis, build_report(meta, analysis)


def build_batch_excel(results):
    """ملف Excel واحد يلخّص كل الملفات: ورقة ملخص + ورقة تقارير."""
    buf = io.BytesIO()
    summary = pd.DataFrame([r[0] for r in results])
    reports = pd.DataFrame([{tr('اسم الملف'): r[0][tr('اسم الملف')], tr('التقرير'): " ".join(r[2])} for r in results])
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        summary.to_excel(w, sheet_name=tr('ملخص الملفات'), index=False)
        reports.to_excel(w, sheet_name=tr('التقارير'), index=False)
        for ws in w.sheets.values():
            ws.sheet_view.rightToLeft = is_arabic()
            for col in ws.columns:
                width = max(len(str(c.value or "")) for c in col) + 4
                ws.column_dimensions[col[0].column_letter].width = min(width, 90)
    return buf.getvalue()


def show_result(idx, meta, analysis, report_lines):
    report_text = " ".join(report_lines)
    col_img, col_rep = st.columns([1, 1.3])
    with col_img:
        st.subheader(tr('صورة الأشعة'))
        st.image(
            (analysis["norm"] * 255).astype(np.uint8),
            caption=tr('صورة أشعة من نوع {v0} بأبعاد {v1} × {v2}', v0=meta[tr('نوع الجهاز')], v1=meta[tr('عدد الصفوف')], v2=meta[tr('عدد الأعمدة')]),
            use_container_width=True,
        )
        if st.toggle(tr('عرض البيانات التقنية الكاملة'), key=f"meta_{idx}"):
            st.table(pd.DataFrame(list(meta.items()), columns=[tr('الحقل'), tr('القيمة')]))
    with col_rep:
        st.subheader(tr('التقرير الوصفي'))
        st.markdown(tr('<div class="report" role="region" aria-label="التقرير الوصفي">')
                    + "<br>".join(report_lines) + "</div>", unsafe_allow_html=True)
        st.caption(tr('زر الاستماع يحوّل التقرير إلى صوت عربي. زر التنزيل يحفظ بيانات هذا الملف في Excel.'))
        b1, b2 = st.columns(2)
        with b1:
            play = st.button(tr('🔊 الاستماع للتقرير'), key=f"play_{idx}",
                             help=tr('يحوّل نص التقرير إلى كلام مسموع'), use_container_width=True)
        with b2:
            st.download_button(
                tr('⬇️ تنزيل تقرير هذا الملف (Excel)'),
                data=build_excel(meta, analysis, report_lines),
                file_name=f"dicom_report_{idx + 1}_{datetime.now():%Y%m%d_%H%M%S}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"dl_{idx}", use_container_width=True,
            )
        audio_key = "monai_audio_" + hashlib.sha256(report_text.encode("utf-8")).hexdigest()
        if play:
            if GTTS_OK:
                try:
                    with st.spinner(tr('جارٍ تجهيز الصوت...')):
                        st.session_state[audio_key] = tts_bytes(report_text)
                except Exception:
                    st.info(tr('تعذّر الاتصال بخدمة gTTS، استخدم قارئ المتصفح أدناه.'))
            else:
                st.info(tr('مكتبة gTTS غير مثبتة، استخدم قارئ المتصفح أدناه.'))
        if st.session_state.get(audio_key):
            st.subheader(tr('صوت تقرير MONAI الهندسي'))
            st.audio(st.session_state[audio_key], format="audio/mpeg", autoplay=play)
            st.download_button(tr('تنزيل صوت MONAI (MP3)'), st.session_state[audio_key],
                               file_name=f"monai_report_{idx + 1}.mp3", mime="audio/mpeg", key=f"monai_audio_dl_{idx}")
        st.caption(tr('قارئ بديل يعمل داخل المتصفح:'))
        browser_tts(report_text)


# ---------- الواجهة ----------
uploaded = st.file_uploader(
    tr('ارفع ملف أشعة \u200e.dcm\u200e أو ملفاً مضغوطاً \u200e.zip\u200e يحتوي عدة ملفات أشعة (الحد الأقصى 200 ميجابايت). اضغط زر Browse files أو اسحب الملف إلى هذه المنطقة.'),
    type=["dcm", "zip"],
    help=tr('ملف \u200e.dcm\u200e يُحلَّل مباشرة. ملف \u200e.zip\u200e يُفك ضغطه وتُحلَّل كل ملفات DICOM بداخله دفعة واحدة.'),
)

if uploaded is None:
    st.info(tr('لم يتم رفع أي ملف بعد. بانتظار ملف الأشعة أو الملف المضغوط.'))
    from monai_gemini.ui import resolve_api_key, render_api_key_setup
    if not resolve_api_key():
        render_api_key_setup()
    st.stop()

raw = uploaded.getvalue()
if len(raw) > MAX_MB * 1024 * 1024:
    st.error(tr('حجم الملف أكبر من {v0} ميجابايت. الرجاء رفع ملف أصغر.', v0=MAX_MB))
    st.stop()

# تجهيز قائمة الملفات المطلوب تحليلها
if uploaded.name.lower().endswith(".zip"):
    try:
        with st.spinner(tr('جارٍ فك ضغط الملف والبحث عن ملفات الأشعة...')):
            files = extract_dicoms_from_zip(raw)
    except Exception as e:
        st.error(tr('تعذّر فك ضغط الملف. تأكد أنه ملف ZIP سليم. التفاصيل: {v0}', v0=e))
        st.stop()
    if not files:
        st.warning(tr('لم يُعثر على أي ملف أشعة DICOM داخل الملف المضغوط.'))
        st.stop()
    st.success(tr('تم العثور على {v0} ملف أشعة داخل الملف المضغوط. تبدأ المعالجة الآن.', v0=len(files)))
else:
    files = [(uploaded.name, raw)]

# معالجة جميع الملفات دفعة واحدة
results, failed = [], []
progress = st.progress(0, text=tr('جارٍ تحليل الملفات...'))
for i, (name, data) in enumerate(files):
    try:
        results.append(analyze_one(name, data))
    except Exception as e:
        failed.append((name, str(e)))
    progress.progress((i + 1) / len(files), text=tr('تم تحليل {v0} من {v1}', v0=i + 1, v1=len(files)))
progress.empty()

if failed:
    with st.expander(tr('⚠️ ملفات تعذّرت قراءتها ({v0})', v0=len(failed))):
        for name, err in failed:
            st.write(f"- {name}: {err}")

if not results:
    st.error(tr('تعذّرت قراءة الملفات. تأكد أنها ملفات DICOM سليمة تحتوي على صور.'))
    st.stop()

st.header(tr('البيانات الطبية المستخرجة'))
if len(results) == 1:
    show_result(0, *results[0])
else:
    st.subheader(tr('ملخص الدفعة: {v0} ملف تم تحليله بنجاح', v0=len(results)))
    st.dataframe(pd.DataFrame([r[0] for r in results])[
        [tr('اسم الملف'), tr('نوع الجهاز'), tr('الجزء المفحوص'), tr('عدد الصفوف'), tr('عدد الأعمدة')]],
        use_container_width=True)
    st.download_button(
        tr('⬇️ تنزيل تقرير جميع الملفات في ملف Excel واحد'),
        data=build_batch_excel(results),
        file_name=f"dicom_batch_report_{datetime.now():%Y%m%d_%H%M%S}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        help=tr('ملف Excel يحتوي ملخص كل الملفات وتقاريرها'),
        use_container_width=True,
    )
    st.caption(tr('اضغط على اسم أي ملف بالأسفل لفتح صورته وتقريره.'))
    for i, (meta, analysis, lines) in enumerate(results):
        with st.expander(f"📄 {i + 1}. {meta[tr('اسم الملف')]}"):
            show_result(i, meta, analysis, lines)


# Gemini receives the completed report plus every numeric metric; MONAI remains unchanged.
st.divider()
selected_result = 0
if len(results) > 1:
    selected_result = st.selectbox(
        tr('ملف الأشعة المطلوب إرساله إلى الذكاء الاصطناعي'), range(len(results)),
        format_func=lambda i: results[i][0][tr('اسم الملف')], key="gemini_source_result",
    )
selected_meta, selected_analysis, selected_lines = results[selected_result]
monai_report = " ".join(selected_lines) + tr('\n\n[البيانات التقنية الأصلية]:\n') + json.dumps(selected_meta, ensure_ascii=False)
monai_report += tr('\n\n[جميع المؤشرات الهندسية العددية الأصلية]:\n') + json.dumps(
    {key: value for key, value in selected_analysis.items() if key != "norm"}, ensure_ascii=False,
)
render_gemini_panel(monai_report, show_monai_player=False)
