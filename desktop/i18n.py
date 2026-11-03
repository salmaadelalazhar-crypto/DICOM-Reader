"""Device locale, stable translations and formatting without altering user data."""
import ctypes
import json
import locale
import os
import re
import sys
from functools import lru_cache
from pathlib import Path


def select_language(device_locale: str | None) -> str:
    code = (device_locale or '').replace('_', '-').lower()
    return 'ar' if code.split('-')[0] == 'ar' else 'en'


def device_locale() -> str:
    if sys.platform == 'win32':
        try:
            # Windows display/UI language, NOT the browser language or regional format.
            lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            buffer = ctypes.create_unicode_buffer(85)
            if ctypes.windll.kernel32.LCIDToLocaleName(lang_id, buffer, len(buffer), 0):
                return buffer.value
        except (AttributeError, OSError):
            pass
    try:
        return locale.getlocale()[0] or ''
    except (ValueError, TypeError):
        return ''


def language() -> str:
    override = os.environ.get('DICOM_DEVICE_LANGUAGE')
    if override:
        return select_language(override)
    # Preserve the original Arabic cloud presentation; auto-detection is desktop-only.
    return select_language(device_locale()) if os.environ.get('DICOM_DESKTOP') == '1' else 'ar'


def is_arabic() -> bool:
    return language() == 'ar'


@lru_cache(maxsize=1)
def catalog() -> dict[str, str]:
    return json.loads(Path(__file__).with_name('translations.json').read_text(encoding='utf-8'))


def tr(arabic: str, **values) -> str:
    text = arabic if is_arabic() else catalog().get(arabic, arabic)
    # Only generated interpolation slots are formatted; JS/CSS braces remain literal.
    return re.sub(r'\{v\d+(?::[^{}]+)?\}', lambda match: match.group().format(**values), text)
