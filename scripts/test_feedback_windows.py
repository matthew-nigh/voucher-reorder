"""Real Windows alignment -> printer output -> reorder -> reprint acceptance."""

import importlib.util
import json
import shutil
import sys
import time
from pathlib import Path

from pypdf import PdfReader

from voucher_reorder.alignment import create
from voucher_reorder.bounded import execute
from voucher_reorder.config import Settings
from voucher_reorder.engine import reorder
from voucher_reorder.printing import validate_vector_pdf


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


def move_output_when_released(source, destination):
    """Wait for the print port to close a complete PDF before moving it."""
    return wait_for(lambda: source.rename(destination))


def main(folder, printer):
    folder.mkdir(parents=True, exist_ok=True)
    settings = Settings(output_mode="pdf", output_folder=str(folder / "saved"))
    original = folder / "alignment.pdf"
    create(original, settings)
    source = folder / "first-reordered.pdf"
    reorder(original, source, settings)
    artifacts = (
        Path(__file__).resolve().parents[1]
        / "build/feedback-artifacts"
        / ("retained" if printer == "Voucher Reorder" else "microsoft-pdf")
    )
    artifacts.mkdir(parents=True, exist_ok=True)
    baseline_path = artifacts.parents[1] / "feedback-baseline-engine.py"
    spec = importlib.util.spec_from_file_location("voucher_reorder.feedback_baseline", baseline_path)
    baseline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(baseline)
    baseline.reorder(original, artifacts / "original-legacy.pdf", settings)
    shutil.copyfile(original, artifacts / "original.pdf")
    shutil.copyfile(source, artifacts / "original-compact.pdf")
    sizes = {"alignment_input": original.stat().st_size, "direct_output": source.stat().st_size}
    assert sizes["direct_output"] < sizes["alignment_input"] * 2
    for generation in range(2):
        execute("print", source, Settings(printer=printer))
        output = folder.parent / "device.pdf"

        def complete():
            if output.exists() and output.read_bytes().rstrip().endswith(b"%%EOF"):
                return len(PdfReader(output).pages) == 1
            return False

        wait_for(complete)
        job = folder / f"roundtrip-{generation}"
        job.mkdir()
        # The local port may release its write handle shortly after the PDF is
        # complete and parseable. Keep the validated file and wait for that handle.
        move_output_when_released(output, job / "input.pdf")
        execute("prepare", job, settings)
        validate_vector_pdf(job / "output.pdf")
        sizes[f"printer_pdf_{generation}"] = (job / "input.pdf").stat().st_size
        sizes[f"compact_output_{generation}"] = (job / "output.pdf").stat().st_size
        assert sizes[f"compact_output_{generation}"] < sizes[f"printer_pdf_{generation}"] * 2
        baseline.reorder(job / "input.pdf", artifacts / f"legacy-{generation}.pdf", settings)
        sizes[f"legacy_output_{generation}"] = (artifacts / f"legacy-{generation}.pdf").stat().st_size
        for name in ("input.pdf", "output.pdf"):
            shutil.copyfile(job / name, artifacts / f"{generation}-{name}")
        source = folder / f"reprinted-{generation}.pdf"
        source.write_bytes((job / "output.pdf").read_bytes())
        execute("inspect", source)
    (artifacts / "sizes.json").write_text(json.dumps(sizes, indent=2))
    print(f"PASS: {printer} alignment and two reprints; bytes={json.dumps(sizes)}", flush=True)


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2])
