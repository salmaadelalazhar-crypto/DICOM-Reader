import io
import os
import unittest
import zipfile
from unittest.mock import patch

import numpy as np
from openpyxl import load_workbook

from helpers import synthetic_dicom
from desktop.i18n import tr


class ProcessingTests(unittest.TestCase):
    def setUp(self):
        p = patch.dict(os.environ, {'DICOM_DEVICE_LANGUAGE': 'ar'})
        p.start()
        self.addCleanup(p.stop)

    def test_single_file_report_and_excel(self):
        from core.processing import analyze_one, build_excel
        meta, analysis, lines = analyze_one('case.dcm', synthetic_dicom())
        self.assertEqual(meta[tr('عدد الصفوف')], '16')
        self.assertEqual(analysis['norm'].shape, (16, 16))
        self.assertEqual(lines[0], 'نوع الفحص: أشعة مقطعية (CT).')
        self.assertAlmostEqual(analysis['mean'], 0.5, places=6)
        self.assertEqual(analysis['bbox'], (8, 0, 15, 15))
        book = load_workbook(io.BytesIO(build_excel(meta, analysis, lines)))
        self.assertEqual(book.sheetnames, [tr('البيانات التقنية'), tr('التحليل الهيكلي'), tr('التقرير')])
        self.assertTrue(book.worksheets[0].sheet_view.rightToLeft)

    def test_zip_batch_keeps_dicoms_only(self):
        from core.processing import analyze_all, build_batch_excel, load_files
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as z:
            z.writestr('first.dcm', synthetic_dicom())
            z.writestr('sub/noext', synthetic_dicom())
            z.writestr('__MACOSX/x.dcm', synthetic_dicom())
            z.writestr('readme.txt', 'hi')
            z.writestr('broken.dcm', b'not a dicom')
        files = load_files('batch.zip', buffer.getvalue())
        self.assertEqual(sorted(n for n, _ in files), ['broken.dcm', 'first.dcm', 'sub/noext'])
        seen = []
        results, failed = analyze_all(files, progress=lambda d, t: seen.append((d, t)))
        self.assertEqual(len(results), 2)
        self.assertEqual([n for n, _ in failed], ['broken.dcm'])
        self.assertEqual(seen[-1], (3, 3))
        self.assertEqual(build_batch_excel(results)[:2], b'PK')

    def test_upload_limit_is_200_mb(self):
        from core.processing import load_files
        with self.assertRaises(ValueError):
            load_files('big.dcm', b'0' * (200 * 1024 * 1024 + 1))

    def test_ai_payload_has_metrics_but_never_pixels(self):
        from core.processing import analyze_one, monai_report_text
        text = monai_report_text(*analyze_one('case.dcm', synthetic_dicom()))
        self.assertIn('"centroid"', text)
        self.assertIn('"p95"', text)
        self.assertNotIn('"norm"', text)

    def test_language_does_not_change_numbers(self):
        from core.processing import analyze_one
        values = []
        for loc in ['ar-EG', 'en-US', 'es-ES']:
            with patch.dict(os.environ, {'DICOM_DEVICE_LANGUAGE': loc}):
                values.append(analyze_one('case.dcm', synthetic_dicom())[1])
        for other in values[1:]:
            np.testing.assert_array_equal(values[0]['norm'], other['norm'])
            self.assertEqual(values[0]['symmetry'], other['symmetry'])


if __name__ == '__main__':
    unittest.main()
