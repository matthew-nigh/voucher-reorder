"""Event-triggered spool metadata and best-effort serialization of fixed-port jobs.

No RAW payload access, RPC spool-file reads, subprocesses, or periodic probes.
"""

import ctypes as c
import json
from ctypes import wintypes as w

from .config import atomic_json


class Guard:
    def __init__(self, root):
        self.root = root
        self.path = root / "printer-pickup.json"
        self.state = json.loads(self.path.read_text()) if self.path.exists() else {"active": None, "held": []}
        self.document = self.state.get("document")

    def snapshot(self):
        from .spool_metadata import JobInfo, PrinterInfo, _checked, _owner_sid

        api = c.WinDLL("winspool.drv", use_last_error=True)
        api.OpenPrinterW.argtypes = [w.LPWSTR, c.POINTER(w.HANDLE), w.LPVOID]
        api.ClosePrinter.argtypes = [w.HANDLE]
        api.GetPrinterW.argtypes = [w.HANDLE, w.DWORD, w.LPVOID, w.DWORD, c.POINTER(w.DWORD)]
        api.EnumJobsW.argtypes = [
            w.HANDLE,
            w.DWORD,
            w.DWORD,
            w.DWORD,
            w.LPVOID,
            w.DWORD,
            c.POINTER(w.DWORD),
            c.POINTER(w.DWORD),
        ]
        handle = w.HANDLE()
        _checked(api.OpenPrinterW("Voucher Reorder", c.byref(handle), None))
        try:

            def buffer(call):
                size = w.DWORD()
                if not call(None, 0, c.byref(size)) and c.get_last_error() != 122:
                    _checked(False)
                if size.value > 16 * 1024**2:
                    raise ValueError("Printer metadata exceeds limit")
                result = c.create_string_buffer(max(1, size.value))
                _checked(call(result, len(result), c.byref(size)))
                return result

            metadata = buffer(lambda p, n, s: api.GetPrinterW(handle, 2, p, n, s))
            printer = c.cast(metadata, c.POINTER(PrinterInfo)).contents
            if (
                printer.comment != f"VoucherReorder owner={_owner_sid()}"
                or printer.driver != "Microsoft Print To PDF"
                or printer.port.casefold() != str(self.root / "Incoming" / "job.pdf").casefold()
            ):
                raise ValueError("Reconfigure the old or foreign virtual printer in Settings")
            count = w.DWORD()
            data = buffer(lambda p, n, s: api.EnumJobsW(handle, 0, 0xFFFFFFFF, 1, p, n, s, c.byref(count)))
            if count.value * c.sizeof(JobInfo) > len(data):
                raise ValueError("Invalid printer metadata")
            jobs = []
            for j in c.cast(data, c.POINTER(JobInfo))[: count.value]:
                t = j.submitted
                key = f"{j.id}-" + "-".join(
                    str(getattr(t, a)) for a in ("year", "month", "day", "hour", "minute", "second", "ms")
                )
                jobs.append(
                    {
                        "id": j.id,
                        "key": key,
                        "status": j.status,
                        "document": j.document or "job",
                        "position": j.position,
                    }
                )
            return sorted(jobs, key=lambda j: (j["position"], j["id"]))
        finally:
            api.ClosePrinter(handle)

    def control(self, job, command):
        from .spool_metadata import _checked

        api = c.WinDLL("winspool.drv", use_last_error=True)
        api.OpenPrinterW.argtypes = [w.LPWSTR, c.POINTER(w.HANDLE), w.LPVOID]
        api.ClosePrinter.argtypes = [w.HANDLE]
        api.SetJobW.argtypes = [w.HANDLE, w.DWORD, w.DWORD, w.LPVOID, w.DWORD]
        handle = w.HANDLE()
        _checked(api.OpenPrinterW("Voucher Reorder", c.byref(handle), None))
        try:
            _checked(api.SetJobW(handle, job["id"], 0, None, command))
        finally:
            api.ClosePrinter(handle)

    def changed(self):
        jobs = self.snapshot()
        active = self.state["active"]
        held = set(self.state["held"])
        held.intersection_update(j["key"] for j in jobs)
        if active is None and jobs:
            active = jobs[0]["key"]
            self.document = f"{jobs[0]['document']}-{jobs[0]['id']}"
        warning = None
        for job in jobs:
            if job["key"] == active or job["key"] in held:
                continue
            if job["status"] & 0x10:
                warning = "Overlapping fixed-port jobs detected. A PDF may have been overwritten; compare Job status with the source documents before reprinting."
            try:
                if not job["status"] & 1:
                    self.control(job, 1)  # JOB_CONTROL_PAUSE, only this user's jobs
                    held.add(job["key"])
            except OSError:
                warning = "Could not hold a second fixed-port job. Stop sending jobs and compare source documents with Job status; a PDF may have been overwritten."
        self.state.update(active=active, held=sorted(held), document=self.document)
        atomic_json(self.path, self.state)
        if warning:
            atomic_json(self.root / "printer-warning.json", {"error": warning})
        return warning

    def picked_up(self):
        self.state.update(active=None, document=None)
        self.document = None
        # Resume only one job we ourselves held, after the fixed path is free.
        for job in self.snapshot():
            if job["key"] in self.state["held"]:
                self.state.update(active=job["key"], document=f"{job['document']}-{job['id']}")
                self.document = self.state["document"]
                atomic_json(self.path, self.state)
                self.control(job, 2)
                self.state["held"].remove(job["key"])
                break
        atomic_json(self.path, self.state)

    def close(self):
        # Held jobs stay held on shutdown: resuming without a watcher could overwrite job.pdf.
        pass
