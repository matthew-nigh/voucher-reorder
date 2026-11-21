"""Runs under the installing user's token, never requests elevation."""

import argparse
import subprocess
from pathlib import Path

from voucher_reorder.config import data_dir
from voucher_reorder.deployment import install, prepare_uninstall
from voucher_reorder.windows import powershell, run


def integrate(root, candidate, version):
    import winreg

    if candidate is None:
        run(powershell("user_links.ps1", "-Action", "remove"))
        for subkey, value in [(r"Software\Microsoft\Windows\CurrentVersion\Run", "VoucherReorder")]:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, subkey, 0, winreg.KEY_SET_VALUE) as key:
                    winreg.DeleteValue(key, value)
            except FileNotFoundError:
                pass
        try:
            winreg.DeleteKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Uninstall\VoucherReorder",
            )
        except FileNotFoundError:
            pass
        return
    run(powershell("user_links.ps1", "-Action", "install", "-Candidate", candidate))
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
        winreg.SetValueEx(
            key,
            "VoucherReorder",
            0,
            winreg.REG_SZ,
            subprocess.list2cmdline(
                [str(candidate / "runtime/pythonw.exe"), str(candidate / "app.py"), "worker"]
            ),
        )
    with winreg.CreateKey(
        winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall\VoucherReorder"
    ) as key:
        for name, value in {
            "DisplayName": "Voucher Reorder",
            "DisplayVersion": version,
            "InstallLocation": str(root),
            "Publisher": "Voucher Reorder contributors",
            "UninstallString": f'"{root / "Uninstall.exe"}"',
        }.items():
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
        for name in ("NoModify", "NoRepair"):
            winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, 1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["install", "uninstall"])
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--candidate", type=Path)
    args = parser.parse_args()
    root, data = args.root, data_dir()
    if args.action == "install":
        result = install(root, args.candidate, data, lambda path, ver: integrate(root, path, ver))
        from voucher_reorder.provisioning import check_version

        try:
            check_version(data, result["version"])
        except OSError:
            # Activation has committed: never report a staging failure that makes
            # NSIS delete the now-active deployment. Settings can retry this check.
            print("App updated. Check provisioning version in Settings before virtual printing.")
    else:
        import winreg

        prepare_uninstall(data)
        run(powershell("user_links.ps1", "-Action", "remove"))
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_SET_VALUE,
            ) as key:
                winreg.DeleteValue(key, "VoucherReorder")
        except FileNotFoundError:
            pass
        try:
            winreg.DeleteKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Uninstall\VoucherReorder",
            )
        except FileNotFoundError:
            pass
        (data / "maintenance.json").unlink(missing_ok=True)
        (data / "stop").unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        # Detailed errors can include private local paths; keep a local generic result.
        print(
            "Setup could not finish. A newer version may already be installed, or a print job/app is still running. No downgrade was performed. Wait for printing to finish and run setup again."
        )
        raise SystemExit(1)
