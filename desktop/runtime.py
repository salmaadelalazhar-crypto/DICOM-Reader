"""Packaged paths and private local state."""
import os
import sys
from pathlib import Path


def root() -> Path:
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))


def state_dir() -> Path:
    path = Path(os.environ.get('LOCALAPPDATA') or Path.home()) / 'DICOMReader'
    path.mkdir(parents=True, exist_ok=True)
    return path
