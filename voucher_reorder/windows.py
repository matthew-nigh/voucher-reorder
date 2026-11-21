"""Windows process boundaries. No shell interpolation of printer names or print data."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(args, timeout=120):
    return subprocess.run(
        [str(a) for a in args],
        check=True,
        timeout=timeout,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def convert(source, output):
    gs = ROOT / "vendor/ghostscript/bin/gswin64c.exe" if os.name == "nt" else "gs"
    run(
        [
            gs,
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
            f"-sOutputFile={output}",
            "-f",
            source,
        ]
    )


def forward(pdf, settings, appdata):
    from .printing import validate_pages

    printer = settings.printer
    validate_pages(pdf, settings)
    result = subprocess.run(
        powershell("printer_info.ps1", "-Printer", printer, "-PaperKind", settings.paper_kind),
        capture_output=True,
        check=True,
        timeout=30,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    import json

    info = json.loads(result.stdout.decode("utf-8-sig"))
    if info["landscape"]:
        raise ValueError("Set the printer's default orientation to portrait before printing vouchers.")
    if abs(info["width"] - settings.paper_width) > 0.02 or abs(info["height"] - settings.paper_height) > 0.02:
        raise ValueError("Printer paper dimensions changed. Select the paper again in Settings.")
    if settings.tray and settings.tray not in info["trays"]:
        raise ValueError("The selected tray is no longer available.")

    if not printer or printer.casefold() == "voucher reorder":
        raise ValueError("Select a physical printer in Voucher Reorder Settings.")
    appdata = Path(appdata)
    appdata.mkdir(parents=True, exist_ok=True, mode=0o700)
    preferences = appdata / "SumatraPDF-settings.txt"
    if not preferences.exists():
        preferences.write_text(
            "RememberOpenedFiles = false\nRememberStatePerDocument = false\n"
            "CheckForUpdates = false\nReuseInstance = false\n",
            encoding="utf-8",
        )
    run(
        [
            ROOT / "vendor/sumatra/SumatraPDF.exe",
            "-appdata",
            appdata,
            "-print-to",
            printer,
            "-print-settings",
            f"noscale,simplex,1x,paperkind={settings.paper_kind},disable-auto-rotation"
            + (f",bin={settings.tray}" if settings.tray else ""),
            "-silent",
            pdf,
        ]
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
    command = subprocess.list2cmdline([str(executable), str(ROOT / "app.py"), "worker"])
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
        winreg.SetValueEx(key, "VoucherReorder", 0, winreg.REG_SZ, command)
    subprocess.Popen(
        [str(executable), str(ROOT / "app.py"), "worker"], creationflags=subprocess.CREATE_NO_WINDOW
    )
