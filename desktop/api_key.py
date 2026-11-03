"""User's own Gemini API key, stored in a private file on the user's device (never in the code)."""
import os
from .runtime import state_dir

KEY_FILE_NAME = 'gemini_api_key.txt'
CREATE_KEY_URL = 'https://aistudio.google.com/app/apikey'


def key_file():
    return state_dir() / KEY_FILE_NAME


def load_api_key() -> str | None:
    try:
        key = key_file().read_text(encoding='utf-8').strip()
        return key or None
    except OSError:
        return None


def save_api_key(key: str) -> bool:
    key = (key or '').strip()
    if not key:
        return False
    try:
        key_file().write_text(key, encoding='utf-8')
    except OSError:
        return False
    os.environ['GEMINI_API_KEY'] = key
    return True
