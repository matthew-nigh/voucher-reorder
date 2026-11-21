"""Six consecutive 10-page jobs through the real worker and bounded print children."""

import ctypes
import gc
import io
import json
import subprocess
import sys
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DecodedStreamObject, NameObject

from voucher_reorder.alignment import create
from voucher_reorder.config import Settings, data_dir
from voucher_reorder.queue import Queue
from voucher_reorder.worker import process_one


def sample_job(first):
    sample = io.BytesIO()
    create(sample, Settings())
    writer = PdfWriter()
    for number in range(first, first + 10):
        page = writer.add_page(PdfReader(io.BytesIO(sample.getvalue())).pages[0])
        # The same vector binary page ID in all three bands survives reordering.
        commands = ["0 g"]
        for band in range(3):
            for bit in range(6):
                if number & (1 << bit):
                    commands.append(f"{480 + bit * 9} {792 - band * 264 - 31} 6 6 re f")
        marker = DecodedStreamObject()
        marker.set_data("\n".join(commands).encode("ascii"))
        page[NameObject("/Contents")] = ArrayObject(
            [page["/Contents"].indirect_reference, writer._add_object(marker)]
        )
    result = io.BytesIO()
    writer.write(result)
    return result.getvalue()


def private_memory():
    from ctypes import wintypes as w

    class Counters(ctypes.Structure):
        _fields_ = [("cb", w.DWORD), ("faults", w.DWORD)] + [
            (name, ctypes.c_size_t)
            for name in (
                "peak_ws",
                "ws",
                "peak_paged",
                "paged",
                "peak_nonpaged",
                "nonpaged",
                "pagefile",
                "peak_pagefile",
                "private",
            )
        ]

    counter = Counters()
    counter.cb = ctypes.sizeof(counter)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes = [w.HANDLE, ctypes.c_void_p, w.DWORD]
    if not psapi.GetProcessMemoryInfo(w.HANDLE(-1), ctypes.byref(counter), counter.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    return counter.private


def main(folder, printer, verifier_python):
    queue = Queue(folder / "jobs")
    settings = Settings(printer=printer)
    # Submit a burst upfront; the same worker must drain it in order.
    for first in range(1, 61, 10):
        assert queue.accept_bytes(sample_job(first), settings)
    jobs = queue.jobs()
    peaks, worker_memory = [], []
    for index, job in enumerate(jobs):
        assert process_one(queue, settings) is None, queue.read(job)
        assert queue.read(job)["state"] == "sent", queue.read(job)
        output = folder / "device.pdf"
        subprocess.run(
            [
                verifier_python,
                str(Path(__file__).with_name("verify_print_output.py")),
                str(output),
                "10",
                "--wait",
                "--first",
                str(index * 10 + 1),
            ],
            check=True,
        )
        output.unlink()  # The next Windows job must create a fresh, complete file.
        peak = json.loads((job.parent / "print-metrics.json").read_text())["peak_job_bytes"]
        assert 0 < peak < 256 * 1024**2, peak
        peaks.append(peak)
        assert not any(p.suffix in (".pdf", ".ps", ".bmp", ".emf") for p in job.parent.iterdir())
        assert sum(queue.read(j)["state"] == "queued" for j in jobs) == 5 - index
        assert not list(folder.rglob("receiving-*"))
        assert not list(job.parent.glob("print-temp-*")), "Compiler scratch files remain"
        gc.collect()
        worker_memory.append(private_memory())
        print(
            f"Job {index + 1}: pages {index * 10 + 1}-{index * 10 + 10}, peak={peak}, worker={worker_memory[-1]}, waiting={5 - index}",
            flush=True,
        )
    # Fresh print children should not accumulate memory; neither should the live worker.
    assert max(peaks) - min(peaks) < 32 * 1024**2, peaks
    assert max(worker_memory) - min(worker_memory) < 16 * 1024**2, worker_memory
    assert all(queue.read(job)["state"] == "sent" for job in jobs)
    print(
        "PASS: six consecutive 10-page vector jobs; all 60 pages in order; flat memory; no payloads or waiting backlog"
    )


if __name__ == "__main__":
    try:
        main(Path(sys.argv[1]), sys.argv[2], sys.argv[3])
    except Exception:
        log = data_dir() / "print-error.log"
        if log.exists():
            print(log.read_text(), file=sys.stderr)
        raise
