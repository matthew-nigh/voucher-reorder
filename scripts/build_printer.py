#!/usr/bin/env python3
"""Build the small privileged components; no runtime compilation or script execution."""

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build(output, installer_payload=None):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    source = ROOT / "packaging/native"
    manifest = source / "admin.manifest"

    def resource(name, contents):
        rc = output / f"{name}.rc"
        rc.write_text(contents, encoding="utf-8")
        obj = output / f"{name}.res"
        if os.name == "nt":
            subprocess.run(["rc.exe", "/nologo", f"/fo{obj}", str(rc)], check=True)
        else:
            subprocess.run(["x86_64-w64-mingw32-windres", str(rc), "-O", "coff", "-o", str(obj)], check=True)
        return obj

    def compile_file(name, target, resources=(), dll=False, gui=False):
        if os.name == "nt":
            command = [
                "cl.exe",
                "/nologo",
                "/std:c++17",
                "/EHsc",
                "/W4",
                "/WX",
                "/MT",
                "/O2",
                "/guard:cf",
                "/DUNICODE",
                "/D_UNICODE",
                "/D_WIN32_WINNT=0x0602",
                str(source / name),
                f"/Fe{output / target}",
                *map(str, resources),
                "/link",
                "/DYNAMICBASE",
                "/NXCOMPAT",
                "/GUARD:CF",
                "/MANIFEST:NO",
                "advapi32.lib",
                "shell32.lib",
                "ole32.lib",
                "winspool.lib",
                "rpcrt4.lib",
                "uuid.lib",
            ]
            if dll:
                command.append("/DLL")
            if gui:
                command.append("/SUBSYSTEM:WINDOWS")
        else:
            command = [
                "x86_64-w64-mingw32-g++",
                "-std=c++17",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-O2",
                "-DUNICODE",
                "-D_UNICODE",
                "-D_WIN32_WINNT=0x0602",
                "-static",
                "-static-libgcc",
                "-static-libstdc++",
                "-shared" if dll else "-municode",
                *(["-mwindows"] if gui else []),
                str(source / name),
                *map(str, resources),
                "-o",
                str(output / target),
                "-ladvapi32",
                "-lshell32",
                "-lole32",
                "-lwinspool",
                "-lrpcrt4",
                "-luuid",
            ]
        subprocess.run(command, cwd=output, check=True)

    admin = resource("admin", f'1 24 "{manifest.as_posix()}"\n')
    compile_file("setup.cpp", "PrinterSetup.exe", [admin])
    compile_file("monitor.cpp", "VoucherReorderPort.dll", dll=True)
    if installer_payload is not None:
        user_manifest = resource(
            "user_manifest",
            f'1 24 "{(source / "user.manifest").as_posix()}"\n'
            f'1 ICON "{(ROOT / "packaging/printer.ico").as_posix()}"\n',
        )
        embedded = resource(
            "embedded",
            f'101 RCDATA "{(output / "PrinterSetup.exe").as_posix()}"\n'
            f'102 RCDATA "{(output / "VoucherReorderPort.dll").as_posix()}"\n'
            f'103 RCDATA "{Path(installer_payload).resolve().as_posix()}"\n',
        )
        compile_file("deploy.cpp", "VoucherReorderSetup.exe", [user_manifest, embedded], gui=True)
    compile_file("security_test.cpp", "PrinterSecurityTest.exe", [admin])
    return output / "VoucherReorderSetup.exe"


if __name__ == "__main__":
    build(ROOT / "build/printer")
