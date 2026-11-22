"""Real Windows alignment -> printer output -> reorder -> reprint acceptance."""

import json
import subprocess
import sys
import time
from pathlib import Path

from pypdf import PdfReader

from voucher_reorder.alignment import create
from voucher_reorder.bounded import execute
from voucher_reorder.config import Settings
from voucher_reorder.engine import reorder
from voucher_reorder.printing import validate_vector_pdf
from voucher_reorder.queue import Queue
from voucher_reorder.spool import retained_candidate
from voucher_reorder.windows import powershell, print_run


def wait_for(check):
    deadline = time.monotonic() + 30
    while True:
        try:
            result = check()
            if result:
                return result
        except (OSError, ValueError):
            pass
        if time.monotonic() >= deadline:
            raise AssertionError("Windows print output did not become ready")
        time.sleep(0.2)


def main(folder, printer):
    folder.mkdir(parents=True, exist_ok=True)
    settings = Settings(output_mode="pdf", output_folder=str(folder / "saved"))
    original = folder / "alignment.pdf"
    create(original, settings)
    source = folder / "first-reordered.pdf"
    reorder(original, source, settings)
    sizes = {"alignment_input": original.stat().st_size, "direct_output": source.stat().st_size}
    assert sizes["direct_output"] < sizes["alignment_input"] * 2
    if printer == "Voucher Reorder":
        # Actual ctypes ABI, SID/owner checks and idle polling on Windows, with
        # all subprocess launches forbidden during the idle interval.
        launch = subprocess.Popen
        try:

            def forbidden(*args, **kwargs):
                raise AssertionError("Idle spool poll spawned a process")

            subprocess.Popen = forbidden
            for _ in range(10):
                assert retained_candidate(folder / "spool-review.json") is None
        finally:
            subprocess.Popen = launch
    for generation in range(2):
        if printer == "Voucher Reorder":
            # Test-only ingress: production Settings still forbids output loops.
            print_run(
                powershell(
                    "print_pages.ps1", "-Printer", printer, "-PaperKind", 1, "-Pdf", source, "-Pages", 1
                ),
                code=7,
            )
            wait_for(lambda: retained_candidate(folder / "spool-review.json"))
            execute("receive", folder, settings)
            queue = Queue(folder / "jobs")
            job = queue.jobs()[-1].parent
            sizes[f"spool_ps_{generation}"] = (job / "input.ps").stat().st_size
        else:
            execute("print", source, Settings(printer=printer))
            output = folder.parent / "device.pdf"

            def complete():
                if output.exists() and output.read_bytes().rstrip().endswith(b"%%EOF"):
                    return len(PdfReader(output).pages) == 1
                return False

            wait_for(complete)
            job = folder / f"roundtrip-{generation}"
            job.mkdir()
            output.rename(job / "input.pdf")
        execute("prepare", job, settings)
        validate_vector_pdf(job / "output.pdf")
        sizes[f"printer_pdf_{generation}"] = (job / "input.pdf").stat().st_size
        sizes[f"compact_output_{generation}"] = (job / "output.pdf").stat().st_size
        assert sizes[f"compact_output_{generation}"] < sizes[f"printer_pdf_{generation}"] * 2
        source = folder / f"reprinted-{generation}.pdf"
        source.write_bytes((job / "output.pdf").read_bytes())
        execute("inspect", source)
    print(f"PASS: {printer} alignment and two reprints; bytes={json.dumps(sizes)}", flush=True)


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2])
