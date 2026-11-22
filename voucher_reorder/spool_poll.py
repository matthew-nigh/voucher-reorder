"""Read local spooler metadata in-process; never launch PowerShell while idle."""

import ctypes as c
import datetime as dt
from ctypes import wintypes as w


class PrinterInfo(c.Structure):
    _fields_ = (
        [(name, w.LPWSTR) for name in ("server", "name", "share", "port", "driver", "comment", "location")]
        + [("devmode", w.LPVOID)]
        + [(name, w.LPWSTR) for name in ("separator", "processor", "datatype", "parameters")]
        + [("security", w.LPVOID)]
        + [
            (name, w.DWORD)
            for name in (
                "attributes",
                "priority",
                "default_priority",
                "start",
                "until",
                "status",
                "jobs",
                "ppm",
            )
        ]
    )


class SystemTime(c.Structure):
    _fields_ = [
        (name, w.WORD) for name in ("year", "month", "weekday", "day", "hour", "minute", "second", "ms")
    ]


class JobInfo(c.Structure):
    _fields_ = (
        [("id", w.DWORD)]
        + [(name, w.LPWSTR) for name in ("printer", "machine", "user", "document", "datatype", "status_text")]
        + [(name, w.DWORD) for name in ("status", "priority", "position", "pages", "printed")]
        + [("submitted", SystemTime)]
    )


def _checked(ok):
    if not ok:
        raise c.WinError(c.get_last_error())


def _owner_sid():
    kernel = c.WinDLL("kernel32", use_last_error=True)
    advapi = c.WinDLL("advapi32", use_last_error=True)
    kernel.GetCurrentProcess.restype = w.HANDLE
    kernel.CloseHandle.argtypes = [w.HANDLE]
    kernel.LocalFree.argtypes = [w.LPVOID]
    kernel.LocalFree.restype = w.LPVOID
    advapi.OpenProcessToken.argtypes = [w.HANDLE, w.DWORD, c.POINTER(w.HANDLE)]
    advapi.GetTokenInformation.argtypes = [w.HANDLE, c.c_int, w.LPVOID, w.DWORD, c.POINTER(w.DWORD)]
    advapi.ConvertSidToStringSidW.argtypes = [w.LPVOID, c.POINTER(w.LPWSTR)]
    token = w.HANDLE()
    _checked(advapi.OpenProcessToken(kernel.GetCurrentProcess(), 8, c.byref(token)))
    try:
        size = w.DWORD()
        advapi.GetTokenInformation(token, 1, None, 0, c.byref(size))
        buf = c.create_string_buffer(size.value)
        _checked(advapi.GetTokenInformation(token, 1, buf, len(buf), c.byref(size)))
        sid = c.cast(buf, c.POINTER(w.LPVOID))[0]
        text = w.LPWSTR()
        _checked(advapi.ConvertSidToStringSidW(sid, c.byref(text)))
        try:
            return text.value
        finally:
            kernel.LocalFree(text)
    finally:
        kernel.CloseHandle(token)


def select_candidate(printer, jobs, sid, excluded):
    """Preserve the owner, retained-job and quarantine checks of the old PS probe."""
    if (
        printer["comment"] != f"VoucherReorder owner={sid}"
        or printer["attributes"] & 8
        or printer["port"] != "NUL:"
        or not printer["attributes"] & 0x100
        or printer["driver"] != "MS Publisher Imagesetter"
    ):
        raise ValueError("Enable the owner-restricted retained printer in Settings.")
    eligible = [
        j for j in jobs if j["status"] & 0x2080 and not j["status"] & 0x18 and j["key"] not in excluded
    ]
    return min(eligible, key=lambda j: (j["ticks"], j["id"])) if eligible else None


def poll(excluded):
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
                raise ValueError("Windows spool metadata size limit exceeded (16 MiB).")
            result = c.create_string_buffer(max(size.value, 1))
            _checked(call(result, len(result), c.byref(size)))
            return result

        printer_buf = buffer(lambda p, n, s: api.GetPrinterW(handle, 2, p, n, s))
        printer = c.cast(printer_buf, c.POINTER(PrinterInfo)).contents
        count = w.DWORD()
        jobs_buf = buffer(lambda p, n, s: api.EnumJobsW(handle, 0, 0xFFFFFFFF, 1, p, n, s, c.byref(count)))
        if count.value * c.sizeof(JobInfo) > len(jobs_buf):
            raise ValueError("Invalid Windows spool metadata.")
        jobs = []
        for j in c.cast(jobs_buf, c.POINTER(JobInfo))[: count.value]:
            t = j.submitted  # JOB_INFO_1.Submitted is UTC, matching .NET UTC ticks.
            submitted = dt.datetime(t.year, t.month, t.day, t.hour, t.minute, t.second, t.ms * 1000)
            delta = submitted - dt.datetime(1, 1, 1)
            ticks = (delta.days * 86400 + delta.seconds) * 10000000 + delta.microseconds * 10
            jobs.append({"id": j.id, "key": f"{j.id}-{ticks}", "ticks": ticks, "status": j.status})
        return select_candidate(
            {name: getattr(printer, name) for name in ("comment", "attributes", "port", "driver")},
            jobs,
            _owner_sid(),
            excluded,
        )
    finally:
        api.ClosePrinter(handle)
