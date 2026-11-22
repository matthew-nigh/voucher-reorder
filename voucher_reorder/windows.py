"""Windows process boundaries. No shell interpolation of printer names or print data."""

import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

from .process import background_options

ROOT = Path(__file__).resolve().parent.parent


def run(args, timeout=120):
    return subprocess.run(
        [str(a) for a in args],
        check=True,
        timeout=timeout,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **background_options(),
    )


def convert(source, output):
    gs = ROOT / "vendor/ghostscript/bin/gswin64c.exe" if os.name == "nt" else "gs"
    from .bounded import LimitedOutput

    args = [
        gs,
        "-q",
        "-sstdout=%stderr",
        "-dSAFER",
        "-dBATCH",
        "-dNOPAUSE",
        "-dNOPROMPT",
        "-sDEVICE=pdfwrite",
        "-dCompatibilityLevel=1.7",
        "-dAutoRotatePages=/None",
        "-dEmbedAllFonts=true",
        "-dSubsetFonts=true",
        "-dDownsampleColorImages=false",
        "-dDownsampleGrayImages=false",
        "-dDownsampleMonoImages=false",
        "-sOutputFile=%stdout",
        "-f",
        source,
    ]
    # The supervising worker enforces the deadline for the entire process tree.
    with (
        LimitedOutput(open(output, "wb", buffering=0)) as out,
        subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            **background_options(),
        ) as process,
    ):
        try:
            shutil.copyfileobj(process.stdout, out, length=65536)
            if process.wait():
                raise ValueError("PostScript conversion failed.")
        finally:
            if process.poll() is None:
                process.kill()


class PrintError(RuntimeError):
    def __init__(self, code):
        self.print_code = code
        super().__init__(f"Windows print operation failed (code {code}).")


def print_run(args, code, timeout=120, capture=False):
    from .diagnostics import ErrorCapture

    with subprocess.Popen(
        list(map(str, args)),
        stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        **background_options(),
    ) as child:
        errors = ErrorCapture(child.stderr)
        output = bytearray()

        def drain_output():
            for chunk in iter(lambda: child.stdout.read(4096), b""):
                # Drain excess without retaining it; malformed printer metadata
                # must not exhaust memory or bypass the subprocess deadline.
                if len(output) <= 65536:
                    output.extend(chunk[: 65537 - len(output)])

        reader = threading.Thread(target=drain_output, daemon=True) if capture else None
        if reader:
            reader.start()
        try:
            child.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()
            raise PrintError(8) from None
        finally:
            if reader:
                reader.join(timeout=2)
            detail = errors.finish()
            if detail:
                print(detail, file=sys.stderr)
        if child.returncode or len(output) > 65536:
            raise PrintError(code)
        return bytes(output) if capture else None


def forward(pdf, settings, appdata=None):
    from .bounded import PRINT_PROBE_TIMEOUT, print_timeout
    from .printing import validate_pages

    printer = settings.printer
    pages = validate_pages(pdf, settings)
    result = print_run(
        powershell("printer_info.ps1", "-Printer", printer, "-PaperKind", settings.paper_kind),
        code=6,
        timeout=PRINT_PROBE_TIMEOUT,
        capture=True,
    )
    import json

    info = json.loads(result.decode("utf-8-sig"))
    if info["landscape"]:
        raise ValueError("Set the printer's default orientation to portrait before printing vouchers.")
    if abs(info["width"] - settings.paper_width) > 0.02 or abs(info["height"] - settings.paper_height) > 0.02:
        raise ValueError("Printer paper dimensions changed. Select the paper again in Settings.")
    if settings.tray and settings.tray not in info["trays"]:
        raise ValueError("The selected tray is no longer available.")

    if not printer or printer.casefold() == "voucher reorder":
        raise ValueError("Select a physical printer in Voucher Reorder Settings.")
    print_run(
        powershell(
            "print_pages.ps1",
            "-Printer",
            printer,
            "-PaperKind",
            settings.paper_kind,
            "-Tray",
            settings.tray,
            "-Pdf",
            pdf,
            "-Pages",
            pages,
        ),
        code=7,
        timeout=print_timeout(pages),
    )


def powershell(script, *args):
    return [
        str(Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"),
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(ROOT / "packaging" / script),
        *map(str, args),
    ]


def message(text):
    import ctypes

    ctypes.windll.user32.MessageBoxW(None, text, "Voucher Reorder", 0x40)


def register_user():
    import winreg

    from .config import data_dir

    if (data_dir() / "maintenance.json").exists():
        return
    executable = ROOT / "runtime/pythonw.exe"
    if not executable.exists():
        executable = Path(sys.executable)
    command = subprocess.list2cmdline([str(executable), str(ROOT / "app.py"), "watch"])
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
        try:
            winreg.DeleteValue(key, "VoucherReorder")
        except FileNotFoundError:
            pass
        winreg.SetValueEx(key, "VoucherReorderWatcher", 0, winreg.REG_SZ, command)
    root = data_dir()
    root.mkdir(parents=True, exist_ok=True)
    (root / "wake").touch()
    from .locking import FileLock

    try:
        with FileLock(root / "worker.lock"):
            pass
    except TimeoutError:
        return  # already waiting on the wake file: do not spawn a duplicate
    subprocess.Popen([str(executable), str(ROOT / "app.py"), "watch"], **background_options())
