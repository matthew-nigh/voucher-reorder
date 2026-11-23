"""Validated settings. Distances are inches; positive y is DOWN the paper."""

import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from .filesystem import replace_file


@dataclass(frozen=True)
class Settings:
    printer: str = ""
    output_mode: str = "printer"
    output_folder: str = ""
    mode: str = "pdf"
    virtual_variant: str = "imagesetter"
    watch_inbox: bool = True
    paper_kind: int = 1
    paper_width: float = 8.5
    paper_height: float = 11.0
    tray: int = 0

    source_order: tuple[int, int, int] = (0, 1, 2)
    order: tuple[int, int, int] = (1, 0, 2)
    boundaries: tuple[float, float] | None = None
    offsets: tuple[tuple[float, float], ...] = ((0, 0), (0, 0), (0, 0))

    def __post_init__(self):
        if self.output_mode not in ("printer", "pdf"):
            raise ValueError("Choose printer or PDF file output.")
        if not isinstance(self.output_folder, str) or any(c in self.output_folder for c in "\r\n\0"):
            raise ValueError("Invalid PDF output folder.")
        if self.output_mode == "pdf":
            self.pdf_folder()
        if self.mode not in ("pdf", "virtual") or type(self.watch_inbox) is not bool:
            raise ValueError("Invalid operating mode.")
        if self.virtual_variant not in ("imagesetter", "print_to_pdf"):
            raise ValueError("Invalid virtual printer variant.")
        if type(self.paper_kind) is not int or not 1 <= self.paper_kind <= 65535:
            raise ValueError("Select a paper size supported by your printer.")
        if type(self.tray) is not int or not 0 <= self.tray <= 65535:
            raise ValueError("Invalid paper tray.")
        if any(not math.isfinite(n) or not 2 <= n <= 40 for n in (self.paper_width, self.paper_height)):
            raise ValueError("Paper dimensions must be between 2 and 40 inches.")

        for order in (self.source_order, self.order):
            if sorted(order) != [0, 1, 2] or any(type(i) is not int for i in order):
                raise ValueError("Choose each of Check, Stub 1, and Stub 2 once in each order.")
        if not isinstance(self.printer, str) or any(c in self.printer for c in "\r\n\0"):
            raise ValueError("Invalid printer name.")
        if self.printer.strip().casefold() == "voucher reorder":
            raise ValueError("Voucher Reorder cannot be the output printer (printing loop).")
        if self.boundaries is not None:
            if len(self.boundaries) != 2 or not all(math.isfinite(x) for x in self.boundaries):
                raise ValueError("Enter two finite band boundaries in inches.")
            if not 0 < self.boundaries[0] < self.boundaries[1]:
                raise ValueError("Band boundaries must increase from the top of the sheet.")
        if len(self.offsets) != 3 or any(len(pair) != 2 for pair in self.offsets):
            raise ValueError("Enter x and y nudges for all three source sections.")
        if any(not math.isfinite(n) or abs(n) > 1 for pair in self.offsets for n in pair):
            raise ValueError("Each nudge must be between -1 and +1 inch.")

    @property
    def output_ready(self) -> bool:
        return self.output_mode == "pdf" or bool(self.printer)

    def pdf_folder(self, root=None) -> Path:
        folder = Path(self.output_folder)
        if not self.output_folder or not folder.is_absolute():
            raise ValueError("Choose an absolute folder for reordered PDFs.")
        folder = folder.resolve()
        for name in ("Inbox", "Incoming", "jobs", "Needs attention"):
            private = ((root or data_dir()) / name).resolve()
            if folder == private or private in folder.parents:
                raise ValueError("Save reordered PDFs outside the Inbox and other private job folders.")
        return folder

    def edges(self, height: float) -> tuple[float, float, float, float]:
        a, b = self.boundaries or (height / 216, height / 108)
        if b * 72 >= height:
            raise ValueError("The second band boundary must be inside every page.")
        return 0, a * 72, b * 72, height


def data_dir() -> Path:
    # Never use a shared or repository directory for print data.
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local/share")) / "VoucherReorder"


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix=".tmp-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(value, f, allow_nan=False)
            f.flush()
            os.fsync(f.fileno())
        replace_file(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def load(path: Path) -> Settings:
    if not path.exists():
        return Settings()
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    return from_dict(raw)


def save(path: Path, settings: Settings):
    atomic_json(path, asdict(settings))


def from_dict(raw) -> Settings:
    """Synchronously migrate v0.2.0 settings and immutable queued-job snapshots.

    Defaults and legacy-field removal happen on a copy, before processing can
    start; no watcher, background rewrite, or migration timing is involved.
    """
    raw = dict(raw)
    raw.pop("quickbooks_version", None)
    raw.pop("printer_model", None)
    return Settings(**raw)
