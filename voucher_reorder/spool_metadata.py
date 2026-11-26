"""Read local spooler metadata in-process; never launch PowerShell while idle."""

import ctypes as c
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
