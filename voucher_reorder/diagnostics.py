"""Bounded local diagnostics: retain structured errors, never document output."""

import re
import threading

LIMIT = 8192


# Free-form platform exception messages may contain document text. Retain only
# metadata and these application-owned/system explanations, never arbitrary text.
MESSAGES = {
    "Out of memory.",
    "Printer rejected the document or page.",
    "Unavailable printer configuration.",
    "Cannot open the selected printer.",
    "PDFium could not load a page.",
    "PDFium page dimensions differ from selected paper.",
    "Cannot record vector page.",
    "PDFium vector rendering failed.",
    "Vector page unavailable or exceeds limit.",
    "Cannot verify vector page.",
    "Blank vector page refused.",
    "Cannot load bundled PDFium.",
    "Vector print mode unavailable.",
    "PDFium page count mismatch.",
    "Printer rejected vector page.",
    "The selected printer is not installed or accessible.",
    "Select a supported paper size in Settings.",
}


def sanitize(line):
    from .pdf_errors import MESSAGES as PDF_MESSAGES

    if line.strip().startswith("VRPDF "):
        reason = line.strip()[6:]
        return f"VRPDF {reason}\n" if reason in PDF_MESSAGES else ""
    match = re.match(
        r"^(VRPRINT (?:worker )?[A-Za-z][A-Za-z0-9_]{0,79}"
        r"(?: HRESULT=-?[0-9]+ line=[0-9]+| code=[0-9]+)?)(?:: (.*))?",
        line,
    )
    if not match:
        return ""
    metadata, detail = match.groups()
    if detail is None:
        return metadata + "\n"
    if detail not in MESSAGES and not re.fullmatch(
        r"PDF requires raster drawing; vector-only printing refused. EMF record=[0-9]+", detail
    ):
        detail = "Details redacted."
    return metadata + ": " + detail + "\n"


class ErrorCapture:
    def __init__(self, stream):
        self.data = ""
        self.stream = stream
        self.thread = threading.Thread(target=self.read, daemon=True)
        self.thread.start()

    def read(self):
        # readline(size) also bounds a malicious line without a newline.
        for raw in iter(lambda: self.stream.readline(2048), b""):
            line = sanitize(raw.decode("utf-8", errors="replace"))
            self.data = (self.data + line)[-LIMIT:]

    def finish(self):
        self.thread.join(timeout=2)
        return self.data
