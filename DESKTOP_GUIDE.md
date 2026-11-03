# إنشاء برنامج ويندوز / Build the Windows application

## بالعربية

1. فك ضغط حزمة المصدر. ارفع **محتويات مجلد dicom-reader** إلى جذر مستودع GitHub، بما فيها المجلد المخفي `.github`؛ لا ترفع ZIP وحده ولا تضع الملفات داخل مجلد إضافي.
2. افتح **Actions → Build Windows desktop EXE → Run workflow**. إن طلب GitHub تفعيل Actions، فعّله أولاً.
3. بعد النجاح افتح نتيجة التشغيل ثم نزّل **DICOMReader-Windows-x64** من **Artifacts**. البناء قد يستغرق وقتاً بسبب PyTorch وMONAI.
4. فك ضغط الحزمة الناتجة كاملة ثم شغّل `DICOMReader.exe`. احتفظ بالمجلد `_internal` وكل الملفات بجواره؛ ملف EXE وحده لا يكفي. هذه حزمة تشغيل وليست مُثبّتاً.
5. يلزم Windows 10/11 ‏64-bit وMicrosoft Edge WebView2 Runtime. لا يلزم Python على جهاز المستخدم. بعض أجهزة Windows Server غير مناسبة للصوت؛ راجع أذونات الميكروفون.

يقرأ البرنامج لغة عرض ويندوز عند فتحه: العربية → العربية، الإنجليزية وكل لغة أخرى → الإنجليزية. تظل واجهة Streamlit الأصلية داخل نافذة مستقلة؛ لا تحتاج نشر موقع ولا يُفتح خادم للعامة. العامل المحلي يستمع على `127.0.0.1` فقط ويُغلق عند إغلاق النافذة.

### المفتاح والإنترنت

- **لا يوجد مفتاحك الخاص داخل المصدر أو الحزمة التنفيذية، ولا تنتقل أسرار Lovable إلى GitHub.**
- النسخة الحالية تحافظ على الاتصال المباشر الأصلي: كل مستخدم يحتاج مفتاحه الخاص. في ويندوز افتح «تحرير متغيرات البيئة لحسابك»، أضف متغير مستخدم باسم `GEMINI_API_KEY` وقيمته مفتاح المستخدم، ثم افتح البرنامج من جديد. لا تضع مفتاحاً في مستودع GitHub أو أسرار Actions لبناء البرنامج.
- يمكن للبرنامج أيضاً قراءة مفتاح سبق تخزينه في Windows Credential Manager بواسطة مكتبة `keyring` باسم الخدمة `DICOMReader` واسم الحساب `GEMINI_API_KEY`؛ لا تتضمن الواجهة شاشة إعداد جديدة للمفتاح حفاظاً على الأزرار الأصلية.
- إذا أردتِ إتاحة مفتاحك لجميع المستخدمين دون كشفه، يلزم خادم وسيط محمي؛ هذا غير مضاف في هذه الحزمة.
- قراءة DICOM والتحليل الهندسي محليان. الذكاء الاصطناعي وgTTS وتحويل الكلام إلى نص تتطلب الإنترنت؛ تتلقى Google التقرير والمؤشرات والمرفقات التي تُرسلها والصوت المستخدم في تحويل الكلام. لا تستخدم بيانات مرضى دون الموافقات اللازمة. قارئ الصوت الاحتياطي يعتمد على أصوات ويندوز/WebView2 المتاحة وليس مضموناً دون إنترنت.
- خيارات النموذج الأصلية محفوظة؛ التشغيل الفعلي يعتمد على توفر معرّفات النماذج لدى Google وصلاحية المفتاح والحصة. يمكن ضبط `GEMINI_MODEL_35_FLASH_LITE` أو `GEMINI_MODEL_36_FLASH` بمتغيرات البيئة إذا لزم، دون تغيير المصدر.

### التحقق وحدوده

الاختبارات تستخدم DICOM مُنشأ للاختبار ومعالجة MONAI حقيقية، مع محاكاة خدمة الذكاء الاصطناعي والصوت لتجنب إرسال بيانات أو استخدام المفتاح. GitHub Actions يبني على Windows ويختبر بدء العامل المُجمّع وقراءة ملف DICOM وعرض التقرير في الحزمة. يجب اختبار النافذة الفعلية والميكروفون والتنزيلات وقارئ الشاشة على جهاز ويندوز بعد تنزيلها. لا يُدّعى أن EXE بُني أو اختُبر على ويندوز قبل تشغيل Actions.

## English

Upload the **contents of dicom-reader** to the root of a GitHub repository, including `.github/workflows/build-windows.yml`. Run **Actions → Build Windows desktop EXE → Run workflow**. Download **DICOMReader-Windows-x64** from the successful run's Artifacts, extract everything, and launch `DICOMReader.exe`. Keep `_internal` and all accompanying files. This is a one-folder portable application, not an installer.

Requires 64-bit Windows 10/11 and Microsoft Edge WebView2 Runtime, but not Python. Arabic Windows display language selects Arabic; all other display languages select English. The original Streamlit interface runs inside the desktop window over a loopback-only local worker.

Each user supplies their own `GEMINI_API_KEY` as a Windows user environment variable, or through a preconfigured keyring entry (`DICOMReader` / `GEMINI_API_KEY`). Restart the application after setting it. No shared provider secret is bundled. A protected relay server is required to share a developer-owned key safely and is not included.

DICOM processing is local. AI, gTTS and native speech recognition require internet access and send their relevant inputs to Google. Preserve patient privacy and obtain the required consent. Model availability and quota are checked at runtime. Verify the actual desktop window, microphone, downloads and assistive technology on Windows after the build.