"""Consume retained RAW jobs through local Windows spooler RPC, under the desktop user's token."""

import ctypes as c
import json
import subprocess
from ctypes import wintypes as w

from .queue import MAX_JOB, Queue
from .windows import powershell


def check(ok):
    if not ok:
        raise c.WinError(c.get_last_error())


def receive_one(root, settings):
    info = subprocess.run(powershell("retained_job.ps1"), check=True, capture_output=True, timeout=15,
                          creationflags=subprocess.CREATE_NO_WINDOW)
    job_id = json.loads(info.stdout.decode("utf-8-sig"))
    if job_id is None:
        return
    if type(job_id) is not int or not 0 < job_id <= 0xffffffff:
        raise ValueError("Invalid Windows spool job.")
    api = c.WinDLL("winspool.drv", use_last_error=True)
    api.OpenPrinterW.argtypes = [w.LPWSTR, c.POINTER(w.HANDLE), w.LPVOID]
    api.ReadPrinter.argtypes = [w.HANDLE, w.LPVOID, w.DWORD, c.POINTER(w.DWORD)]
    api.ClosePrinter.argtypes = [w.HANDLE]
    api.SetJobW.argtypes = [w.HANDLE, w.DWORD, w.DWORD, w.LPVOID, w.DWORD]
    handle = w.HANDLE()
    check(api.OpenPrinterW(f"Voucher Reorder, Job {job_id}", c.byref(handle), None))
    try:
        payload = bytearray()
        buf = c.create_string_buffer(65536)
        count = w.DWORD()
        while True:
            check(api.ReadPrinter(handle, buf, len(buf), c.byref(count)))
            if not count.value:
                break
            if len(payload) + count.value > MAX_JOB:
                raise ValueError("Retained job exceeds the size limit.")
            payload.extend(buf.raw[:count.value])
        Queue(root / "jobs").accept_bytes(payload, settings, "ps")
        # Keep the job handle open until the durable copy is acknowledged.
        printer = w.HANDLE()
        check(api.OpenPrinterW("Voucher Reorder", c.byref(printer), None))
        try:
            check(api.SetJobW(printer, job_id, 0, None, 5))  # JOB_CONTROL_DELETE
        finally:
            api.ClosePrinter(printer)
    finally:
        api.ClosePrinter(handle)
