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


def forward(pdf, printer, appdata):
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
            "noscale,simplex,paper=letter,disable-auto-rotation",
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

    command = subprocess.list2cmdline([sys.executable, str(ROOT / "app.py"), "worker"])
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
        winreg.SetValueEx(key, "VoucherReorder", 0, winreg.REG_SZ, command)
    subprocess.Popen(
        [sys.executable, str(ROOT / "app.py"), "worker"], creationflags=subprocess.CREATE_NO_WINDOW
    )


def launch_desktop_settings():
    """Drop the installer's elevation using the signed-in Explorer process token.

    Setup already checks that Explorer belongs to the installing account. All handle
    signatures are explicit so this works with 64-bit Python (no truncated handles).
    """
    import ctypes as c
    from ctypes import wintypes as w

    user32, kernel32, advapi32 = c.windll.user32, c.windll.kernel32, c.windll.advapi32

    class StartupInfo(c.Structure):
        _fields_ = [
            ("cb", w.DWORD),
            ("lpReserved", w.LPWSTR),
            ("lpDesktop", w.LPWSTR),
            ("lpTitle", w.LPWSTR),
            ("dwX", w.DWORD),
            ("dwY", w.DWORD),
            ("dwXSize", w.DWORD),
            ("dwYSize", w.DWORD),
            ("dwXCountChars", w.DWORD),
            ("dwYCountChars", w.DWORD),
            ("dwFillAttribute", w.DWORD),
            ("dwFlags", w.DWORD),
            ("wShowWindow", w.WORD),
            ("cbReserved2", w.WORD),
            ("lpReserved2", c.c_void_p),
            ("hStdInput", w.HANDLE),
            ("hStdOutput", w.HANDLE),
            ("hStdError", w.HANDLE),
        ]

    class ProcessInfo(c.Structure):
        _fields_ = [
            ("hProcess", w.HANDLE),
            ("hThread", w.HANDLE),
            ("dwProcessId", w.DWORD),
            ("dwThreadId", w.DWORD),
        ]

    user32.GetShellWindow.restype = w.HWND
    user32.GetWindowThreadProcessId.argtypes = [w.HWND, c.POINTER(w.DWORD)]
    kernel32.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    kernel32.OpenProcess.restype = w.HANDLE
    kernel32.CloseHandle.argtypes = [w.HANDLE]
    advapi32.OpenProcessToken.argtypes = [w.HANDLE, w.DWORD, c.POINTER(w.HANDLE)]
    advapi32.DuplicateTokenEx.argtypes = [
        w.HANDLE,
        w.DWORD,
        c.c_void_p,
        c.c_int,
        c.c_int,
        c.POINTER(w.HANDLE),
    ]
    advapi32.CreateProcessWithTokenW.argtypes = [
        w.HANDLE,
        w.DWORD,
        w.LPCWSTR,
        w.LPWSTR,
        w.DWORD,
        c.c_void_p,
        w.LPCWSTR,
        c.POINTER(StartupInfo),
        c.POINTER(ProcessInfo),
    ]
    pid = w.DWORD()
    user32.GetWindowThreadProcessId(user32.GetShellWindow(), c.byref(pid))
    process = kernel32.OpenProcess(0x1000, False, pid.value)
    token, primary = w.HANDLE(), w.HANDLE()
    info = ProcessInfo()
    try:
        if not process or not advapi32.OpenProcessToken(process, 0x000A, c.byref(token)):
            raise OSError("Could not access the desktop token")
        if not advapi32.DuplicateTokenEx(token, 0x02000000, None, 2, 1, c.byref(primary)):
            raise OSError("Could not duplicate the desktop token")
        startup = StartupInfo()
        startup.cb = c.sizeof(startup)
        startup.lpDesktop = "winsta0\\default"
        command = c.create_unicode_buffer(
            subprocess.list2cmdline([sys.executable, str(ROOT / "app.py"), "settings"])
        )
        if not advapi32.CreateProcessWithTokenW(
            primary, 1, sys.executable, command, 0x08000000, None, str(ROOT), c.byref(startup), c.byref(info)
        ):
            raise OSError("Could not launch settings as the desktop user")
    finally:
        for handle in (info.hThread, info.hProcess, primary, token, process):
            if handle:
                kernel32.CloseHandle(handle)
