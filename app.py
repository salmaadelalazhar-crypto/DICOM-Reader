# -*- coding: utf-8 -*-
"""
قارئ الأشعة الطبية DICOM - منصة ميسّرة للأطباء وذوي الإعاقة البصرية
التشغيل: streamlit run app.py
"""
import io
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

st.set_page_config(page_title="قارئ أشعة DICOM الميسّر", page_icon="🩻", layout="wide")

# ---------- تنسيق عربي واضح وعالي التباين ----------
st.markdown(
    """
    <style>
    html, body, [class*="css"], .stMarkdown, .stButton, label { direction: rtl; text-align: right; font-size: 1.1rem; }
    .stButton>button, .stDownloadButton>button {
        font-size: 1.2rem; font-weight: 700; padding: .7rem 1.4rem; border-radius: 10px;
        border: 3px solid #0b5394; }
    .stDownloadButton>button { background:#0b6e3a; color:#fff; border-color:#064d28; }
    .stButton>button:focus, .stDownloadButton>button:focus { outline: 4px solid #ffbf00; }
    .report { background:#f5f9ff; border-right:6px solid #0b5394; padding:1rem 1.2rem; border-radius:8px; line-height:2; color:#111; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("🩻 قارئ ومفسّر ملفات الأشعة الطبية (DICOM)")
st.markdown(
    "مرحبًا بك. **الخطوة الأولى:** ارفع ملف أشعة بامتداد ‎.dcm‎. "
    "**الخطوة الثانية:** اقرأ التقرير أو اضغط زر الاستماع. "
    "**الخطوة الثالثة:** نزّل التقرير الكامل بصيغة Excel. "
    "جميع الأزرار مُعنونة نصيًا ومتوافقة مع قارئات الشاشة ويمكن التنقل بينها بمفتاح Tab."
)
st.warning("تنبيه: هذا التحليل آلي وصفي للمساعدة فقط، ولا يُغني عن تشخيص الطبيب المختص.")


# ---------- دوال المعالجة ----------
def safe(ds, tag, default="غير متوفر"):
    v = getattr(ds, tag, None)
    if v is None or str(v).strip() == "":
        return default
    return str(v)


MODALITY_AR = {
    "CT": "أشعة مقطعية (CT)", "MR": "رنين مغناطيسي (MRI)", "CR": "أشعة سينية محوسبة (CR)",
    "DX": "أشعة سينية رقمية (DX)", "US": "موجات فوق صوتية (US)", "MG": "تصوير الثدي (Mammography)",
    "PT": "تصوير مقطعي بالإصدار البوزيتروني (PET)", "NM": "طب نووي (NM)", "XA": "تصوير الأوعية (XA)",
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
        engine = "NumPy (احتياطي - MONAI غير مثبتة)"
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


def level(v, lo, hi, words=("منخفض", "متوسط", "مرتفع")):
    return words[0] if v < lo else (words[2] if v > hi else words[1])


def build_report(meta, a):
    lines = [
        f"نوع الفحص: {meta['نوع الجهاز']}.",
        f"الجزء المفحوص: {meta['الجزء المفحوص']}.",
        f"أبعاد الصورة: {meta['عدد الصفوف']} صفًا في {meta['عدد الأعمدة']} عمودًا، وعدد الشرائح {meta['عدد الشرائح']}.",
        f"متوسط شدة الإضاءة المعيارية {a['mean']:.2f} من واحد، والانحراف المعياري {a['std']:.2f}، أي أن التباين النسيجي {level(a['std'], 0.12, 0.25)}.",
        f"درجة التباين العام {a['contrast']:.2f}، وهي درجة {level(a['contrast'], 0.4, 0.8)}.",
        f"إنتروبيا الصورة {a['entropy']:.2f} بت، ما يدل على تعقيد نسيجي {level(a['entropy'], 3.5, 5.0)}.",
        f"كثافة الحواف {a['edge_density'] * 100:.1f} بالمئة، ما يشير إلى وضوح حدود بنيوية {level(a['edge_density'], 0.02, 0.06)}.",
        f"تشغل البنية الرئيسية الساطعة نحو {a['fg_ratio'] * 100:.1f} بالمئة من مساحة الصورة.",
        f"درجة التماثل بين النصف الأيمن والأيسر {a['symmetry'] * 100:.1f} بالمئة، وهو تماثل {level(a['symmetry'], 0.8, 0.92, ('ضعيف', 'مقبول', 'جيد'))}.",
        f"تم التحليل باستخدام: {a['engine']}.",
        "هذا وصف تقني آلي للمساعدة، ويجب مراجعته من قبل طبيب أشعة مختص.",
    ]
    return lines


def tts_bytes(text):
    buf = io.BytesIO()
    gTTS(text=text, lang="ar").write_to_fp(buf)
    return buf.getvalue()


def browser_tts(text):
    """قارئ صوتي احتياطي مدمج في المتصفح (Web Speech API) يعمل دون إنترنت للخادم."""
    components.html(
        f"""
        <div dir="rtl" style="font-family:sans-serif">
          <button aria-label="تشغيل قراءة التقرير بصوت المتصفح" onclick="s()" style="font-size:18px;padding:10px 18px;margin:4px">🔊 قراءة بصوت المتصفح</button>
          <button aria-label="إيقاف القراءة" onclick="speechSynthesis.cancel()" style="font-size:18px;padding:10px 18px;margin:4px">⏹ إيقاف</button>
        </div>
        <script>
          function s(){{ speechSynthesis.cancel(); const u=new SpeechSynthesisUtterance({json.dumps(text)}); u.lang='ar-SA'; u.rate=0.95; speechSynthesis.speak(u); }}
        </script>
        """,
        height=70,
    )


def build_excel(meta, a, report_lines):
    buf = io.BytesIO()
    meta_df = pd.DataFrame(list(meta.items()), columns=["الحقل", "القيمة"])
    stats = {
        "محرك التحليل": a["engine"], "متوسط الشدة (0-1)": round(a["mean"], 4),
        "الانحراف المعياري": round(a["std"], 4), "المئين 5": round(a["p5"], 4),
        "الوسيط": round(a["median"], 4), "المئين 95": round(a["p95"], 4),
        "درجة التباين (Michelson)": round(a["contrast"], 4), "الإنتروبيا (بت)": round(a["entropy"], 4),
        "كثافة الحواف": round(a["edge_density"], 4), "نسبة البنية الرئيسية": round(a["fg_ratio"], 4),
        "الإطار المحيط (y1,x1,y2,x2)": str(a["bbox"]),
        "مركز الكتلة (y,x)": f"({a['centroid'][0]:.1f}, {a['centroid'][1]:.1f})",
        "درجة التماثل": round(a["symmetry"], 4),
    }
    stats_df = pd.DataFrame(list(stats.items()), columns=["المؤشر", "القيمة"])
    rep_df = pd.DataFrame({"رقم": range(1, len(report_lines) + 1), "الوصف": report_lines})
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        meta_df.to_excel(w, sheet_name="البيانات التقنية", index=False)
        stats_df.to_excel(w, sheet_name="التحليل الهيكلي", index=False)
        rep_df.to_excel(w, sheet_name="التقرير", index=False)
        for ws in w.sheets.values():
            ws.sheet_view.rightToLeft = True
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
        "اسم الملف": name,
        "حجم الملف (كيلوبايت)": f"{len(data) / 1024:.1f}",
        "نوع الجهاز": MODALITY_AR.get(mod, mod),
        "الجزء المفحوص": safe(ds, "BodyPartExamined"),
        "وصف الدراسة": safe(ds, "StudyDescription"),
        "تاريخ الدراسة": safe(ds, "StudyDate"),
        "الشركة المصنعة": safe(ds, "Manufacturer"),
        "عدد الصفوف": safe(ds, "Rows"),
        "عدد الأعمدة": safe(ds, "Columns"),
        "عدد الشرائح": safe(ds, "NumberOfFrames", "1"),
        "أبعاد المصفوفة": str(tuple(arr.shape)),
        "المسافة بين البكسلات (مم)": str(list(spacing)) if spacing else "غير متوفر",
        "سماكة الشريحة (مم)": safe(ds, "SliceThickness"),
        "البتات المخزنة": safe(ds, "BitsStored"),
        "التفسير الضوئي": safe(ds, "PhotometricInterpretation"),
        "أدنى قيمة بكسل": f"{float(arr.min()):.1f}",
        "أعلى قيمة بكسل": f"{float(arr.max()):.1f}",
    }
    return meta, analysis, build_report(meta, analysis)


def build_batch_excel(results):
    """ملف Excel واحد يلخّص كل الملفات: ورقة ملخص + ورقة تقارير."""
    buf = io.BytesIO()
    summary = pd.DataFrame([r[0] for r in results])
    reports = pd.DataFrame([{"اسم الملف": r[0]["اسم الملف"], "التقرير": " ".join(r[2])} for r in results])
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        summary.to_excel(w, sheet_name="ملخص الملفات", index=False)
        reports.to_excel(w, sheet_name="التقارير", index=False)
        for ws in w.sheets.values():
            ws.sheet_view.rightToLeft = True
            for col in ws.columns:
                width = max(len(str(c.value or "")) for c in col) + 4
                ws.column_dimensions[col[0].column_letter].width = min(width, 90)
    return buf.getvalue()


def show_result(idx, meta, analysis, report_lines):
    report_text = " ".join(report_lines)
    col_img, col_rep = st.columns([1, 1.3])
    with col_img:
        st.subheader("صورة الأشعة")
        st.image(
            (analysis["norm"] * 255).astype(np.uint8),
            caption=f"صورة أشعة من نوع {meta['نوع الجهاز']} بأبعاد {meta['عدد الصفوف']} × {meta['عدد الأعمدة']}",
            use_container_width=True,
        )
        if st.toggle("عرض البيانات التقنية الكاملة", key=f"meta_{idx}"):
            st.table(pd.DataFrame(list(meta.items()), columns=["الحقل", "القيمة"]))
    with col_rep:
        st.subheader("التقرير الوصفي")
        st.markdown('<div class="report" role="region" aria-label="التقرير الوصفي">'
                    + "<br>".join(report_lines) + "</div>", unsafe_allow_html=True)
        st.caption("زر الاستماع يحوّل التقرير إلى صوت عربي. زر التنزيل يحفظ بيانات هذا الملف في Excel.")
        b1, b2 = st.columns(2)
        with b1:
            play = st.button("🔊 الاستماع للتقرير", key=f"play_{idx}",
                             help="يحوّل نص التقرير إلى كلام مسموع", use_container_width=True)
        with b2:
            st.download_button(
                "⬇️ تنزيل تقرير هذا الملف (Excel)",
                data=build_excel(meta, analysis, report_lines),
                file_name=f"dicom_report_{idx + 1}_{datetime.now():%Y%m%d_%H%M%S}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"dl_{idx}", use_container_width=True,
            )
        audio_key = "monai_audio_" + hashlib.sha256(report_text.encode("utf-8")).hexdigest()
        if play:
            if GTTS_OK:
                try:
                    with st.spinner("جارٍ تجهيز الصوت..."):
                        st.session_state[audio_key] = tts_bytes(report_text)
                except Exception:
                    st.info("تعذّر الاتصال بخدمة gTTS، استخدم قارئ المتصفح أدناه.")
            else:
                st.info("مكتبة gTTS غير مثبتة، استخدم قارئ المتصفح أدناه.")
        if st.session_state.get(audio_key):
            st.subheader("صوت تقرير MONAI الهندسي")
            st.audio(st.session_state[audio_key], format="audio/mpeg", autoplay=play)
            st.download_button("تنزيل صوت MONAI (MP3)", st.session_state[audio_key],
                               file_name=f"monai_report_{idx + 1}.mp3", mime="audio/mpeg", key=f"monai_audio_dl_{idx}")
        st.caption("قارئ بديل يعمل داخل المتصفح:")
        browser_tts(report_text)


# ---------- الواجهة ----------
uploaded = st.file_uploader(
    "ارفع ملف أشعة ‎.dcm‎ أو ملفاً مضغوطاً ‎.zip‎ يحتوي عدة ملفات أشعة (الحد الأقصى 200 ميجابايت). "
    "اضغط زر Browse files أو اسحب الملف إلى هذه المنطقة.",
    type=["dcm", "zip"],
    help="ملف ‎.dcm‎ يُحلَّل مباشرة. ملف ‎.zip‎ يُفك ضغطه وتُحلَّل كل ملفات DICOM بداخله دفعة واحدة.",
)

if uploaded is None:
    st.info("لم يتم رفع أي ملف بعد. بانتظار ملف الأشعة أو الملف المضغوط.")
    st.stop()

raw = uploaded.getvalue()
if len(raw) > MAX_MB * 1024 * 1024:
    st.error(f"حجم الملف أكبر من {MAX_MB} ميجابايت. الرجاء رفع ملف أصغر.")
    st.stop()

# تجهيز قائمة الملفات المطلوب تحليلها
if uploaded.name.lower().endswith(".zip"):
    try:
        with st.spinner("جارٍ فك ضغط الملف والبحث عن ملفات الأشعة..."):
            files = extract_dicoms_from_zip(raw)
    except Exception as e:
        st.error(f"تعذّر فك ضغط الملف. تأكد أنه ملف ZIP سليم. التفاصيل: {e}")
        st.stop()
    if not files:
        st.warning("لم يُعثر على أي ملف أشعة DICOM داخل الملف المضغوط.")
        st.stop()
    st.success(f"تم العثور على {len(files)} ملف أشعة داخل الملف المضغوط. تبدأ المعالجة الآن.")
else:
    files = [(uploaded.name, raw)]

# معالجة جميع الملفات دفعة واحدة
results, failed = [], []
progress = st.progress(0, text="جارٍ تحليل الملفات...")
for i, (name, data) in enumerate(files):
    try:
        results.append(analyze_one(name, data))
    except Exception as e:
        failed.append((name, str(e)))
    progress.progress((i + 1) / len(files), text=f"تم تحليل {i + 1} من {len(files)}")
progress.empty()

if failed:
    with st.expander(f"⚠️ ملفات تعذّرت قراءتها ({len(failed)})"):
        for name, err in failed:
            st.write(f"- {name}: {err}")

if not results:
    st.error("تعذّرت قراءة الملفات. تأكد أنها ملفات DICOM سليمة تحتوي على صور.")
    st.stop()

st.header("البيانات الطبية المستخرجة")
if len(results) == 1:
    show_result(0, *results[0])
else:
    st.subheader(f"ملخص الدفعة: {len(results)} ملف تم تحليله بنجاح")
    st.dataframe(pd.DataFrame([r[0] for r in results])[
        ["اسم الملف", "نوع الجهاز", "الجزء المفحوص", "عدد الصفوف", "عدد الأعمدة"]],
        use_container_width=True)
    st.download_button(
        "⬇️ تنزيل تقرير جميع الملفات في ملف Excel واحد",
        data=build_batch_excel(results),
        file_name=f"dicom_batch_report_{datetime.now():%Y%m%d_%H%M%S}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        help="ملف Excel يحتوي ملخص كل الملفات وتقاريرها",
        use_container_width=True,
    )
    st.caption("اضغط على اسم أي ملف بالأسفل لفتح صورته وتقريره.")
    for i, (meta, analysis, lines) in enumerate(results):
        with st.expander(f"📄 {i + 1}. {meta['اسم الملف']}"):
            show_result(i, meta, analysis, lines)


# Gemini receives the completed report plus every numeric metric; MONAI remains unchanged.
st.divider()
selected_result = 0
if len(results) > 1:
    selected_result = st.selectbox(
        "ملف الأشعة المطلوب إرساله إلى الذكاء الاصطناعي", range(len(results)),
        format_func=lambda i: results[i][0]["اسم الملف"], key="gemini_source_result",
    )
selected_meta, selected_analysis, selected_lines = results[selected_result]
monai_report = " ".join(selected_lines) + "\n\n[البيانات التقنية الأصلية]:\n" + json.dumps(selected_meta, ensure_ascii=False)
monai_report += "\n\n[جميع المؤشرات الهندسية العددية الأصلية]:\n" + json.dumps(
    {key: value for key, value in selected_analysis.items() if key != "norm"}, ensure_ascii=False,
)
render_gemini_panel(monai_report, show_monai_player=False)
