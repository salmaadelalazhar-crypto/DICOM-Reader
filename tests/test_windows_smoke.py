"""Three simple checks that the app can run on Windows."""
import py_compile
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class WindowsSmokeTest(unittest.TestCase):
    def test_1_running_on_windows(self):
        self.assertTrue(sys.platform.startswith("win"), "Not running on Windows")

    def test_2_main_libraries_load(self):
        import streamlit, pydicom, numpy, webview  # noqa: F401

    def test_3_app_files_are_valid(self):
        for name in ("app.py", "launcher.py"):
            py_compile.compile(str(ROOT / name), doraise=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
