"""Resource-limited document worker. Children inherit the Windows Job or POSIX process group."""

import ctypes
import io
import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path

from .config import Settings

MAX_PAGES = 250
MEMORY = 768 * 1024**2
MAX_OUTPUT = 256 * 1024**2
TIMEOUT = 120
ERRORS = {
    2: "PDF must be unencrypted and contain 1 to 250 pages.",
    3: "PDF page size differs from selected printer paper. Select matching paper.",
    4: "Flatten optional-content layers before sending a PDF print job.",
    5: "PDF processing failed or exceeded the document limits.",
}


class LimitedOutput(io.BufferedWriter):
    """Check every write before extending an intermediate PDF on disk."""

    def write(self, data):
        if self.tell() + len(data) > MAX_OUTPUT:
            raise ValueError("Expanded PDF exceeds processing limit.")
        return super().write(data)


def constrain():
    if os.name != "nt":
        import resource

        for limit, size in ((resource.RLIMIT_AS, MEMORY), (resource.RLIMIT_FSIZE, MAX_OUTPUT)):
            resource.setrlimit(limit, (size, size))
        return
    from ctypes import wintypes as w

    size = ctypes.c_size_t

    class Basic(ctypes.Structure):
        _fields_ = [
            ("process_time", ctypes.c_int64),
            ("job_time", ctypes.c_int64),
            ("flags", w.DWORD),
            ("min_ws", size),
            ("max_ws", size),
            ("processes", w.DWORD),
            ("affinity", size),
            ("priority", w.DWORD),
            ("scheduling", w.DWORD),
        ]

    class Extended(ctypes.Structure):
        _fields_ = [
            ("basic", Basic),
            ("io", ctypes.c_uint64 * 6),
            ("process_memory", size),
            ("job_memory", size),
            ("peak_process", size),
            ("peak_job", size),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [w.LPVOID, w.LPCWSTR]
    kernel.CreateJobObjectW.restype = w.HANDLE
    kernel.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, w.LPVOID, w.DWORD]
    kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
    job = kernel.CreateJobObjectW(None, None)
    info = Extended()
    info.basic.flags = 0x2000 | 0x200  # KILL_ON_JOB_CLOSE | JOB_MEMORY
    info.job_memory = MEMORY
    if not (
        job
        and kernel.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info))
        and kernel.AssignProcessToJobObject(job, w.HANDLE(-1))
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    # Retain the sole non-inheritable handle until exit, including forced termination.


def execute(operation, path, settings=None):
    path = Path(path).resolve()
    args = [
        sys.executable,
        "-m",
        "voucher_reorder.bounded",
        operation,
        str(path),
        json.dumps(asdict(settings or Settings())),
    ]
    child = subprocess.Popen(
        args,
        cwd=Path(__file__).resolve().parents[1],
        start_new_session=os.name != "nt",
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    deadline = time.monotonic() + TIMEOUT
    try:
        while child.poll() is None:
            if operation == "receive" and ((path / "stop").exists() or (path / "maintenance.json").exists()):
                raise ValueError("Spool receipt interrupted.")
            if time.monotonic() >= deadline:
                raise ValueError(ERRORS[5])
            if operation == "prepare" and any(p.stat().st_size > MAX_OUTPUT for p in path.glob("*.pdf")):
                raise ValueError(ERRORS[5])
            if operation == "print":
                bitmap = path.parent / "page.bmp"
                try:
                    size = bitmap.stat().st_size
                except FileNotFoundError:
                    size = 0
                if size > MAX_OUTPUT:
                    raise ValueError(ERRORS[5])
            time.sleep(0.05)
        if child.returncode:
            raise ValueError(ERRORS.get(child.returncode, ERRORS[5]))
    finally:
        if os.name != "nt":
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        elif child.poll() is None:
            child.kill()
        child.wait()


def main(operation, path, config):
    constrain()
    from pypdf import PdfReader

    from .engine import reorder
    from .printing import validate_pages
    from .windows import convert, forward

    settings = Settings(**json.loads(config))
    if operation == "receive":
        from .spool import receive_one

        receive_one(path, settings)
        return 0
    if operation == "inspect":
        reader = PdfReader(path, strict=True)
        return 2 if reader.is_encrypted or not 0 < len(reader.pages) <= MAX_PAGES else 0
    if operation == "prepare":
        if (path / "input.ps").exists() and not (path / "input.pdf").exists():
            convert(path / "input.ps", path / "input.pdf")
        if (path / "input.pdf").stat().st_size > MAX_OUTPUT:
            return 5
        reorder(path / "input.pdf", path / "output.pdf", settings)
        if (path / "output.pdf").stat().st_size > MAX_OUTPUT:
            return 5
        validate_pages(path / "output.pdf", settings)
        return 0
    if operation == "print":
        forward(path, settings, path.parents[2] / "sumatra")
        return 0
    return 5


if __name__ == "__main__":
    try:
        result = main(sys.argv[1], Path(sys.argv[2]), sys.argv[3])
    except ValueError as error:
        result = (
            3
            if str(error).startswith("PDF page size")
            else 4
            if str(error).startswith("Flatten optional")
            else 5
        )
    except Exception:
        result = 5
    sys.exit(result)
