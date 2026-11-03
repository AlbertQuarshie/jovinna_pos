"""Encrypted settings file for secrets (M-Pesa keys).

On Windows the file is encrypted with DPAPI, tied to the logged-in Windows account: copying the file
to another PC or account makes it unreadable. Elsewhere (development only) it falls back to plain
JSON. Secrets never go in the code, the repository or the backups' plain files.
"""
import ctypes
import json
import sys
from ctypes import wintypes
from pathlib import Path

from app import config


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi(data: bytes, protect: bool) -> bytes:
    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = _Blob()
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    ok = fn(ctypes.byref(blob_in), None, None, None, None, 0x1, ctypes.byref(blob_out))  # 0x1: no UI
    if not ok:
        raise OSError("Windows couldn't decrypt the saved settings (was the file copied from another PC?)")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def _path(name: str) -> Path:
    return config.DATA_DIR / f"{name}.secret"


def load(name: str) -> dict:
    path = _path(name)
    if not path.exists():
        return {}
    raw = path.read_bytes()
    if sys.platform == "win32":
        raw = _dpapi(raw, protect=False)
    return json.loads(raw.decode("utf-8"))


def save(name: str, values: dict) -> None:
    raw = json.dumps(values).encode("utf-8")
    if sys.platform == "win32":
        raw = _dpapi(raw, protect=True)
    path = _path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(raw)
    tmp.replace(path)
