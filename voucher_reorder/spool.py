"""Validate the protected virtual queue; per-job isolation lives in the port monitor."""

import ctypes as c
from ctypes import wintypes as w
from pathlib import Path


def incoming_folder():
    from .spool_metadata import _checked, _owner_sid

    # Resolve the Windows known folder, not a user-controlled environment variable.
    shell = c.WinDLL("shell32", use_last_error=True)
    shell.SHGetFolderPathW.argtypes = [w.HWND, c.c_int, w.HANDLE, w.DWORD, w.LPWSTR]
    path = c.create_unicode_buffer(32768)
    _checked(shell.SHGetFolderPathW(None, 0x23, None, 0, path) == 0)
    return Path(path.value) / "VoucherReorderSpool" / _owner_sid()


class Guard:
    def __init__(self, root):
        self.root = root

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
                or printer.attributes & (0x8 | 0x100)  # shared / keep printed jobs
                or printer.port != f"VoucherReorder:{_owner_sid()}"
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

    def changed(self):
        self.snapshot()

    def close(self):
        pass
