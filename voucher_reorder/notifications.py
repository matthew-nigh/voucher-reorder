"""Windows kernel waits only: overlapped directory and spooler change notifications."""

import ctypes as c
import struct
from ctypes import wintypes as w

INFINITE = 0xFFFFFFFF
INVALID = w.HANDLE(-1).value


class Overlapped(c.Structure):
    _fields_ = [
        ("internal", c.c_size_t),
        ("internal_high", c.c_size_t),
        ("offset", w.DWORD),
        ("offset_high", w.DWORD),
        ("event", w.HANDLE),
    ]


def checked(ok):
    if not ok:
        raise c.WinError(c.get_last_error())
    return ok


def relevant(name):
    name = name.replace("\\", "/").casefold()
    parts = name.split("/")
    return (
        name in {"settings.json", "stop", "maintenance.json", "wake"}
        or (len(parts) == 2 and parts[0] in {"inbox", "incoming"} and parts[1].endswith(".pdf"))
        or (len(parts) == 3 and parts[0] == "jobs" and parts[2] == "state.json")
    )


class Changes:
    def __init__(self, root):
        self.kernel = k = c.WinDLL("kernel32", use_last_error=True)
        self.spool = s = c.WinDLL("winspool.drv", use_last_error=True)
        k.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, w.LPVOID, w.DWORD, w.DWORD, w.HANDLE]
        k.CreateFileW.restype = w.HANDLE
        k.CreateEventW.argtypes = [w.LPVOID, w.BOOL, w.BOOL, w.LPCWSTR]
        k.CreateEventW.restype = w.HANDLE
        k.ReadDirectoryChangesW.argtypes = [
            w.HANDLE,
            w.LPVOID,
            w.DWORD,
            w.BOOL,
            w.DWORD,
            c.POINTER(w.DWORD),
            c.POINTER(Overlapped),
            w.LPVOID,
        ]
        k.GetOverlappedResult.argtypes = [w.HANDLE, c.POINTER(Overlapped), c.POINTER(w.DWORD), w.BOOL]
        k.CancelIoEx.argtypes = [w.HANDLE, c.POINTER(Overlapped)]
        k.ResetEvent.argtypes = [w.HANDLE]
        k.CloseHandle.argtypes = [w.HANDLE]
        k.WaitForMultipleObjects.argtypes = [w.DWORD, c.POINTER(w.HANDLE), w.BOOL, w.DWORD]
        k.WaitForMultipleObjects.restype = w.DWORD
        s.OpenPrinterW.argtypes = [w.LPWSTR, c.POINTER(w.HANDLE), w.LPVOID]
        s.ClosePrinter.argtypes = [w.HANDLE]
        s.FindFirstPrinterChangeNotification.argtypes = [w.HANDLE, w.DWORD, w.DWORD, w.LPVOID]
        s.FindFirstPrinterChangeNotification.restype = w.HANDLE
        s.FindNextPrinterChangeNotification.argtypes = [w.HANDLE, c.POINTER(w.DWORD), w.LPVOID, w.LPVOID]
        s.FindClosePrinterChangeNotification.argtypes = [w.HANDLE]
        self.directory = self.event = self.printer = self.change = None
        self.child = None
        self.pending = False
        self.buffer = c.create_string_buffer(32768)
        self.overlapped = Overlapped()
        try:
            self.directory = k.CreateFileW(str(root), 1, 7, None, 3, 0x42000000, None)
            if self.directory == INVALID:
                self.directory = None
                checked(False)
            self.event = checked(k.CreateEventW(None, True, False, None))
            self.overlapped.event = self.event
            self._arm()
        except BaseException:
            self.close()
            raise

    def _arm(self):
        checked(self.kernel.ResetEvent(self.event))
        checked(
            self.kernel.ReadDirectoryChangesW(
                self.directory,
                self.buffer,
                len(self.buffer),
                True,
                0x1 | 0x2 | 0x8 | 0x10,
                None,
                c.byref(self.overlapped),
                None,
            )
        )
        self.pending = True

    def watch_printer(self, enabled):
        if not enabled:
            self._close_printer()
        elif not self.change:
            handle = w.HANDLE()
            checked(self.spool.OpenPrinterW("Voucher Reorder", c.byref(handle), None))
            self.printer = handle
            self.change = self.spool.FindFirstPrinterChangeNotification(handle, 0x0000FF00, 0, None)
            if self.change == INVALID:
                self.change = None
                self._close_printer()
                checked(False)
            return True
        return False

    def wait(self, timeout=None):
        """Return relevant sources; rearm BEFORE the caller inspects durable work.

        An empty directory result means unrelated internal writes, not a job.
        Buffer overflow requests a full rescan; no filenames or contents are lost silently.
        """
        handles = [self.event] + ([self.change] if self.change else [])
        child_index = len(handles)
        if self.child is not None:
            handles.append(int(self.child._handle))
        result = self.kernel.WaitForMultipleObjects(
            len(handles),
            (w.HANDLE * len(handles))(*handles),
            False,
            INFINITE if timeout is None else max(0, min(int(timeout * 1000), INFINITE - 1)),
        )
        if self.child is not None and result == child_index:
            return {"processor"}
        if result == 258:
            return {"timeout"}
        if result == 1 and self.change:
            flags = w.DWORD()
            if not self.spool.FindNextPrinterChangeNotification(self.change, c.byref(flags), None, None):
                self._close_printer()
                return {"printer_error"}
            return {"printer"}
        if result != 0:
            checked(False)
        count = w.DWORD()
        checked(
            self.kernel.GetOverlappedResult(self.directory, c.byref(self.overlapped), c.byref(count), False)
        )
        self.pending = False
        data = self.buffer.raw[: count.value]
        self._arm()
        if not data:
            return {"files", "printer"}  # overflow: rescan both sources
        offset = 0
        found = set()
        while offset < len(data):
            following, action, size = struct.unpack_from("<III", data, offset)
            name = data[offset + 12 : offset + 12 + size].decode("utf-16-le")
            if relevant(name):
                found.add("files")
            if not following:
                break
            offset += following
        return found

    def _close_printer(self):
        if self.change:
            self.spool.FindClosePrinterChangeNotification(self.change)
            self.change = None
        if self.printer:
            self.spool.ClosePrinter(self.printer)
            self.printer = None

    def close(self):
        self._close_printer()
        if self.directory:
            if self.pending:
                self.kernel.CancelIoEx(self.directory, c.byref(self.overlapped))
                count = w.DWORD()
                self.kernel.GetOverlappedResult(
                    self.directory, c.byref(self.overlapped), c.byref(count), True
                )
            self.kernel.CloseHandle(self.directory)
            self.directory = None
        if self.event:
            self.kernel.CloseHandle(self.event)
            self.event = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
