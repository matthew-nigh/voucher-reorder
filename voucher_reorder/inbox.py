"""Receive closed PDFs without racing the PDF printer or modifying originals."""

import tempfile
from pathlib import Path
import os
import time
from contextlib import contextmanager

from .bounded import execute

from .config import atomic_json
from .queue import MAX_JOB


@contextmanager
def exclusive_read(path):
    if os.name == "nt":
        import ctypes as c
        import msvcrt
        from ctypes import wintypes as w

        kernel = c.WinDLL("kernel32", use_last_error=True)
        kernel.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, c.c_void_p, w.DWORD, w.DWORD, w.HANDLE]
        kernel.CreateFileW.restype = w.HANDLE
        handle = kernel.CreateFileW(str(path), 0x80000000, 0, None, 3, 128, None)
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


class Inbox:
    def __init__(self, root):
        self.folder = root / "Inbox"
        self.folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.receipts = root / "inbox-receipts.json"
        import json

        self.seen = json.loads(self.receipts.read_text()) if self.receipts.exists() else {}
        self.stable = {}

    def scan(self, queue, settings, now=None):
        now = time.monotonic() if now is None else now
        warning = None
        for path in sorted(self.folder.glob("*.pdf")):
            try:
                stat = path.stat()
                signature = [stat.st_size, stat.st_mtime_ns]
                key = path.name
                if self.seen.get(key) == signature:
                    continue
                prior, since = self.stable.get(key, (None, now))
                if prior != signature:
                    self.stable[key] = (signature, now)
                    continue
                if now - since < 3:
                    continue
                payload = read_pdf(path)  # exclusive Windows handle proves the writer has closed
                queue.accept_bytes(payload, settings)
                self.seen[key] = signature
                atomic_json(self.receipts, self.seen)
            except OSError:
                continue  # still being written/locked; do not enqueue a partial snapshot
            except ValueError:
                warning = "A PDF in Inbox is incomplete, invalid, or waiting for queue space. Open Settings."
        # Preserve receipts while originals exist: expiry must never reprint an old Inbox PDF.
        existing = {p.name for p in self.folder.glob("*.pdf")}
        self.seen = {k: v for k, v in self.seen.items() if k in existing}
        return warning
