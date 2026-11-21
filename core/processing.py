# -*- coding: utf-8 -*-
"""
معالجة ملفات الأشعة DICOM: القراءة، تحليل MONAI، التقرير الوصفي، Excel، والصوت.
هذه الدوال منقولة كما هي من app.py الأصلي، بدون أي مكتبة واجهة.
"""
import io
import json
import zipfile

import numpy as np
import pandas as pd
import pydicom

from desktop.i18n import is_arabic, language, tr

try:
    import torch
    from monai.transforms import Compose, EnsureChannelFirst, ScaleIntensity, ToTensor
    MONAI_OK = True
except Exception:  # يعمل البرنامج حتى لو تعذّر تحميل MONAI
    MONAI_OK = False

try:
    from gtts import gTTS
    GTTS_OK = True
except Exception:
    GTTS_OK = False

MAX_MB = 200


def safe(ds, tag, default=None):
    if default is None:
        default = tr('غير متوفر')
    v = getattr(ds, tag, None)
    if v is None or str(v).strip() == "":
        return default
    return str(v)


def modality_names():
    return {
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
    return [
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


def tts_bytes(text):
    """صوت MP3 للتقرير عبر gTTS (يتطلب الإنترنت)."""
    buf = io.BytesIO()
    gTTS(text=text, lang=language()).write_to_fp(buf)
    return buf.getvalue()


def _autosize(writer):
    for ws in writer.sheets.values():
        ws.sheet_view.rightToLeft = is_arabic()
        for col in ws.columns:
            width = max(len(str(c.value or "")) for c in col) + 4
            ws.column_dimensions[col[0].column_letter].width = min(width, 90)


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
        _autosize(w)
    return buf.getvalue()


def extract_dicoms_from_zip(zip_bytes):
    """يفك ضغط ملف ZIP في الذاكرة ويعيد قائمة (اسم الملف، محتواه) لكل ملفات DICOM بداخله."""
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
        tr('نوع الجهاز'): modality_names().get(mod, mod),
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
        _autosize(w)
    return buf.getvalue()


def load_files(file_name, raw):
    """يحوّل الملف المرفوع إلى قائمة ملفات DICOM: ملف واحد أو محتويات ZIP."""
    if len(raw) > MAX_MB * 1024 * 1024:
        raise ValueError(tr('حجم الملف أكبر من {v0} ميجابايت. الرجاء رفع ملف أصغر.', v0=MAX_MB))
    if file_name.lower().endswith(".zip"):
        return extract_dicoms_from_zip(raw)
    return [(file_name, raw)]


def analyze_all(files, progress=None):
    """يحلل كل الملفات دفعة واحدة؛ يعيد (النتائج، الملفات الفاشلة)."""
    results, failed = [], []
    for i, (name, data) in enumerate(files):
        try:
            results.append(analyze_one(name, data))
        except Exception as e:
            failed.append((name, str(e)))
        if progress:
            progress(i + 1, len(files))
    return results, failed


def monai_report_text(meta, analysis, lines):
    """النص المرسل إلى Gemini: التقرير + البيانات التقنية + كل المؤشرات العددية (بدون مصفوفة البكسلات)."""
    text = " ".join(lines) + tr('\n\n[البيانات التقنية الأصلية]:\n') + json.dumps(meta, ensure_ascii=False)
    text += tr('\n\n[جميع المؤشرات الهندسية العددية الأصلية]:\n') + json.dumps(
        {key: value for key, value in analysis.items() if key != "norm"}, ensure_ascii=False,
    )
    return text


def gtts_mp3(text):
    """Same gTTS voice as the MONAI report; returns None instead of raising (used for AI replies)."""
    if not GTTS_OK or not text.strip():
        return None
    try:
        return tts_bytes(text)
    except Exception:
        return None
