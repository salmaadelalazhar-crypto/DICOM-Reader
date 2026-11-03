"""Packaged paths, private local state and child process arguments."""
import os
import socket
import sys
from pathlib import Path


def root() -> Path:
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))


def state_dir() -> Path:
    path = Path(os.environ.get('LOCALAPPDATA') or Path.home()) / 'DICOMReader'
    path.mkdir(parents=True, exist_ok=True)
    return path


def child_command(port: int) -> list[str]:
    entry = [] if getattr(sys, 'frozen', False) else [str(root() / 'launcher.py')]
    return [sys.executable, *entry, '--streamlit-worker', str(port)]


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]
