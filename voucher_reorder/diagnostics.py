"""Bounded local diagnostics: retain structured errors, never document output."""

import re
import threading

LIMIT = 8192


def sanitize(line):
    if not line.startswith("VRPRINT "):
        return ""
    # Exception messages can contain printer names, document paths or quoted data.
    line = re.sub(r"([\"\']).*?\1", "<redacted>", line)
    line = re.sub(r"(?:[A-Za-z]:[\\/]|/)[^\s,;]*", "<path>", line)
    return "".join(c for c in line if c in "\n\t" or 32 <= ord(c) < 127)[:1024]


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
