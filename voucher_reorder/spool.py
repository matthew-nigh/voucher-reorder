"""Consume retained RAW jobs through local Windows spooler RPC, under the desktop user's token."""

import ctypes as c
import hashlib
import json
from ctypes import wintypes as w

from .config import atomic_json
from .queue import MAX_JOB, Queue
from .spool_poll import poll


def check(ok):
    if not ok:
        raise c.WinError(c.get_last_error())


def retained_candidate(quarantine):
    excluded = json.loads(quarantine.read_text()) if quarantine.exists() else []
    candidate = poll(excluded)
    if candidate is None and excluded:
        raise ValueError("Retained Windows job needs review.")
    return candidate


def receive_one(root, settings):
    quarantine = root / "spool-review.json"
    candidate = retained_candidate(quarantine)
    if candidate is None:
        return
    job_id = candidate["id"]
    key = candidate["key"]
    if type(job_id) is not int or not 0 < job_id <= 0xFFFFFFFF:
        raise ValueError("Invalid Windows spool job.")
    api = c.WinDLL("winspool.drv", use_last_error=True)
    api.OpenPrinterW.argtypes = [w.LPWSTR, c.POINTER(w.HANDLE), w.LPVOID]
    api.ReadPrinter.argtypes = [w.HANDLE, w.LPVOID, w.DWORD, c.POINTER(w.DWORD)]
    api.ClosePrinter.argtypes = [w.HANDLE]
    api.SetJobW.argtypes = [w.HANDLE, w.DWORD, w.DWORD, w.LPVOID, w.DWORD]
    # A killed/blocked read must never monopolize the next worker iteration.
    blocked = json.loads(quarantine.read_text()) if quarantine.exists() else []
    atomic_json(quarantine, [*blocked, key])
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
            payload.extend(buf.raw[: count.value])
        Queue(root / "jobs").accept_bytes(
            payload, settings, "ps", source=("spool:" + key, hashlib.sha256(payload).hexdigest())
        )
        # Keep the job handle open until the durable copy is acknowledged.
        printer = w.HANDLE()
        check(api.OpenPrinterW("Voucher Reorder", c.byref(printer), None))
        try:
            check(api.SetJobW(printer, job_id, 0, None, 5))  # JOB_CONTROL_DELETE
        finally:
            api.ClosePrinter(printer)
        if blocked:
            atomic_json(quarantine, blocked)
        else:
            quarantine.unlink()
    finally:
        api.ClosePrinter(handle)
