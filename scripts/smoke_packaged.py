"""Run with the bundled Windows python.exe, not the build host's Python."""

import tempfile
from pathlib import Path

from pypdf import PdfReader

from voucher_reorder.alignment import create
from voucher_reorder.bounded import execute
from voucher_reorder.config import Settings
from voucher_reorder.engine import reorder
from voucher_reorder.windows import ROOT, convert

assert (ROOT / "runtime/python.exe").exists(), "Wrong interpreter/package root"
with tempfile.TemporaryDirectory() as temp:
    folder = Path(temp)
    source, output = folder / "fake.pdf", folder / "output.pdf"
    create(source, Settings())
    reorder(source, output, Settings(order=(2, 1, 0)))
    assert len(PdfReader(output).pages) == 1
    ps = folder / "fake.ps"
    ps.write_text(
        "%!PS-Adobe-3.0\n<< /PageSize [612 792] >> setpagedevice\n/Helvetica findfont 14 scalefont setfont\n72 720 moveto (FAKE SAMPLE VOID) show\nshowpage\n"
    )
    convert(ps, output)
    assert "FAKE SAMPLE VOID" in PdfReader(output).pages[0].extract_text()
print("Packaged Python, pypdf, vector engine and Windows Ghostscript passed.")

# Exercise the same nested Windows Job assignment used by the per-user worker.

with tempfile.TemporaryDirectory() as temp:
    folder = Path(temp)
    create(folder / "input.pdf", Settings())
    execute("inspect", folder / "input.pdf")
    execute("prepare", folder, Settings())
    assert len(PdfReader(folder / "output.pdf").pages) == 1
