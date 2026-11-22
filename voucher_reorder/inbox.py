"""Receive closed PDFs without racing the PDF printer or modifying originals."""

import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

from .bounded import execute
from .config import atomic_json
from .queue import MAX_JOB


@contextmanager
def exclusive_read(path, movable=False):
    if os.name == "nt":
        import ctypes as c
        import msvcrt
        from ctypes import wintypes as w

        kernel = c.WinDLL("kernel32", use_last_error=True)
        kernel.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, c.c_void_p, w.DWORD, w.DWORD, w.HANDLE]
        kernel.CreateFileW.restype = w.HANDLE
        handle = kernel.CreateFileW(str(path), 0x80000000, 4 if movable else 0, None, 3, 128, None)
        if handle == w.HANDLE(-1).value:
            raise OSError(c.get_last_error(), "PDF is still open or unavailable")
        try:
            fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
        except Exception:
            kernel.CloseHandle.argtypes = [w.HANDLE]
            kernel.CloseHandle(handle)
            raise
        with os.fdopen(fd, "rb") as stream:
            yield stream
    else:
        with path.open("rb") as stream:
            yield stream


def read_pdf(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError("Choose a regular PDF file.")
    with exclusive_read(path) as stream:
        data = stream.read(MAX_JOB + 1)
        if not 0 < len(data) <= MAX_JOB:
            raise ValueError("PDF must be smaller than 100 MiB.")
        if not data.startswith(b"%PDF-") or b"%%EOF" not in data[-2048:]:
            raise ValueError("PDF is incomplete; wait for saving to finish.")
        with tempfile.TemporaryDirectory() as folder:
            snapshot = Path(folder) / "input.pdf"
            snapshot.write_bytes(data)
            execute("inspect", snapshot)
        return data


def persist_receipt(root, key, signature):
    path = root / "inbox-receipts.json"
    seen = json.loads(path.read_text()) if path.exists() else {}
    seen[key] = signature
    atomic_json(path, seen)


class Inbox:
    def __init__(self, root):
        self.folder = root / "Inbox"
        self.folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.receipts = root / "inbox-receipts.json"

    def scan(self, queue, settings, now=None):
        warning = None
        seen = json.loads(self.receipts.read_text()) if self.receipts.exists() else {}
        for path in sorted(self.folder.glob("*")):
            if path.suffix.lower() != ".pdf":
                continue
            try:
                stat = path.stat()
                # Legacy originals must never be reprinted by an upgrade.
                if seen.get(path.name) == [stat.st_size, stat.st_mtime_ns]:
                    continue
                queue.accept_file(path, settings)
            except (OSError, ValueError):
                warning = "Inbox PDF is open, incomplete or unavailable. Finish saving; use Retry pickup in Job status if needed."
        return warning
