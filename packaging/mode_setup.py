"""Only this optional action requests UAC. Refusal always leaves PDF mode usable."""

import subprocess
import sys
from dataclasses import replace

from voucher_reorder.config import data_dir, load, save
from voucher_reorder.lifecycle import stop_worker
from voucher_reorder.windows import message, powershell, register_user


def main(action, ui=False):
    root = data_dir()
    root.mkdir(parents=True, exist_ok=True)
    config = root / "settings.json"
    initialized = root / "mode-initialized"
    if action == "auto" and initialized.exists():
        return 0
    remove = action in ("pdf", "remove")
    settings = load(config)
    installed_marker = root / "virtual-installed"
    if remove and settings.mode == "pdf" and not installed_marker.exists():
        (root / "mode-status.txt").write_text("PDF handoff mode is ready.", encoding="utf-8")
        return 0
    try:
        stop_worker(root)
        result = subprocess.run(
            powershell("request_printer.ps1", "-Action", "remove" if remove else "install"),
            timeout=300,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if not remove and result.returncode == 0:
            installed_marker.touch()
            (root / "fixed-port-installed").touch()
            save(config, replace(settings, mode="virtual"))
            detail = "Virtual printer mode is ready. Print to Voucher Reorder while signed in."
        else:
            save(config, replace(settings, mode="pdf"))
            detail = (
                "PDF handoff mode is ready. Save QuickBooks PDFs in the Inbox shown in Settings. "
                "No administrator access is needed for this mode."
            )
            if not remove and result.returncode:
                detail += " Virtual printer setup was blocked, declined or failed; rerun setup and select the virtual printer option."
            if remove and result.returncode:
                detail += (
                    " The optional Windows printer was not removed; an administrator can remove it later."
                )
        if remove and result.returncode == 0:
            installed_marker.unlink(missing_ok=True)
            (root / "fixed-port-installed").unlink(missing_ok=True)
        initialized.touch()
        if action not in ("remove", "setup"):
            register_user()
        (root / "mode-status.txt").write_text(detail, encoding="utf-8")
        if action == "setup" or ui:
            print(detail)
        else:
            message(detail)
        return 0
    except Exception:
        # No elevation/setup failure may make the no-admin application unusable.
        save(config, replace(settings, mode="pdf"))
        initialized.touch()
        if action not in ("remove", "setup"):
            register_user()
        detail = "Virtual printer setup was unavailable. PDF handoff mode is ready; open Voucher Reorder from Start."
        (root / "mode-status.txt").write_text(detail, encoding="utf-8")
        if action == "setup" or ui:
            print(detail)
        else:
            message(detail)
        return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "auto", ui="--ui" in sys.argv[2:]))
