# إنشاء برنامج ويندوز / Build the Windows program

## بالعربية

1. فك ضغط حزمة المصدر، وارفع **محتويات مجلد dicom-reader** إلى جذر مستودع GitHub، بما فيها المجلد المخفي `.github`.
2. افتح **Actions → Build Windows desktop EXE → Run workflow** (فعّل Actions أولاً إن طُلب).
3. بعد النجاح نزّل **DICOMReader-Windows-x64** من **Artifacts**. يستغرق البناء وقتاً بسبب PyTorch وMONAI.
4. فك ضغط الحزمة كاملة وشغّل `DICOMReader.exe`. احتفظ بالمجلد `_internal` بجواره.

**المتطلبات:** ويندوز 10/11 ‏64-bit فقط. لا يلزم Python ولا متصفح ولا WebView2. البرنامج نافذة عادية لا تفتح أي منفذ شبكة على الجهاز.

**اللغة:** تُختار من لغة عرض ويندوز: العربية ← عربي، وأي لغة أخرى ← إنجليزي.

**مفتاح Gemini:** عند أول فتح تظهر شاشة بخطوات إنشاء المفتاح من Google AI Studio؛ الصق المفتاح واضغط «حفظ»، ويُحفظ في `%LOCALAPPDATA%\DICOMReader` على جهاز المستخدم فقط. زر «تغيير مفتاح API» يحذفه لإدخال غيره. يمكن أيضاً ضبط متغير البيئة `GEMINI_API_KEY`. لا يوجد أي مفتاح داخل المصدر أو البرنامج.

**الإنترنت والخصوصية:** قراءة DICOM والتحليل محليان. Gemini وgTTS والتحدث بالميكروفون تحتاج الإنترنت وتُرسل التقرير والمؤشرات والمرفقات والكلام إلى Google — لا تُرسل صورة الأشعة نفسها. القارئ البديل يعمل بأصوات ويندوز دون إنترنت (يلزم تثبيت صوت عربي في ويندوز للقراءة بالعربية).

**عند حدوث خطأ في الفتح:** يُكتب السبب في `%LOCALAPPDATA%\DICOMReader\startup.log`.

**التحقق:** GitHub Actions يثبّت المكتبات ويشغّل الاختبارات ويبني البرنامج، ثم يجري اختبار دخان بسيطاً: يفتح البرنامج 30 ثانية فقط دون اختيار ملف أو استخدام الصوت أو المفتاح؛ إن بقي مفتوحاً دون أن يُغلق نفسه يُعدّ البناء ناجحاً. يجب تجربة الصوت والميكروفون والمفتاح على جهاز ويندوز فعلي.

## English

Upload the **contents of dicom-reader** (including `.github`) to the root of a GitHub repository, run **Actions → Build Windows desktop EXE → Run workflow**, download **DICOMReader-Windows-x64** from Artifacts, extract everything and run `DICOMReader.exe` (keep `_internal`).

Requires only 64-bit Windows 10/11 — no Python, browser or WebView2. The interface is a native PySide6 (Qt) window. Language follows the Windows display language. On first launch a setup screen guides each user to create a Gemini API key; it is stored only under `%LOCALAPPDATA%\DICOMReader` (or use the `GEMINI_API_KEY` environment variable). DICOM processing is local; Gemini, gTTS and speech recognition send their inputs (never the image itself) to Google. Startup errors are written to `%LOCALAPPDATA%\DICOMReader\startup.log`. The workflow runs the tests, builds the EXE, then runs a simple smoke test: the program is started for 30 seconds without opening a file, audio or the API key; if it stays open the build passes.
