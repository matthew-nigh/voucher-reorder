"""Only this optional action requests UAC. Refusal always leaves PDF mode usable."""

import subprocess
import sys
from dataclasses import replace

from voucher_reorder.config import data_dir, load, save
from voucher_reorder.lifecycle import stop_worker
from voucher_reorder.windows import message, powershell, register_user

STAGES = {
    100: "invalid printer action or account SID",
    110: "protected helper or monitor verification",
    120: "existing printer ownership, pending jobs, or queue removal",
    130: "machine printer owner SID",
    140: "print driver privilege or monitor removal",
    150: "protected Imagesetter spool directory or owner registration",
    160: "Imagesetter monitor installation",
    161: "user profile path for Print to PDF",
    162: "Print to PDF Local Port creation or ownership",
    170: "printer creation or Microsoft Print To PDF driver",
    180: "Imagesetter paper configuration",
}


def failure_reason(code):
    if code >= 1000000:
        stage, error = divmod(code, 10000)
        return f"Printer setup failed at stage {stage} ({STAGES.get(stage, 'native printer operation')}); Windows error {error}."
    return {
        1: "Installer deployment failed: protected destination, file verification, or administrator access.",
        10: "Printer setup was declined or could not be started by Windows.",
        11: "Printer setup image is missing or its location is unsafe.",
        12: "Printer setup could not finish the application preparation.",
    }.get(code, f"Printer setup failed with code {code}.")


def main(action, ui=False):
    root = data_dir()
    root.mkdir(parents=True, exist_ok=True)
    config = root / "settings.json"
    initialized = root / "mode-initialized"
    if action == "auto" and initialized.exists():
        return 0
    if action in ("setup", "setup-pdf"):
        (root / "mode-status.txt").unlink(missing_ok=True)
        (root / "printer-setup-code.txt").unlink(missing_ok=True)
    (root / "printer-setup-error.txt").unlink(missing_ok=True)
    remove = action in ("pdf", "remove")
    settings = load(config)
    if action in ("pdf-printer", "setup-pdf"):
        (root / "Incoming").mkdir(parents=True, exist_ok=True, mode=0o700)
    installed_marker = root / "virtual-installed"
    if remove and settings.mode == "pdf" and not installed_marker.exists():
        (root / "mode-status.txt").write_text("PDF handoff mode is ready.", encoding="utf-8")
        return 0
    try:
        stop_worker(root)
        variant = "print_to_pdf" if action in ("pdf-printer", "setup-pdf") else "imagesetter"
        printer_args = [
            "-Action",
            "remove" if remove else "install-pdf" if variant == "print_to_pdf" else "install",
        ]
        if "--installer" in sys.argv[2:]:
            printer_args.append("-Installer")
        result = subprocess.run(
            powershell("request_printer.ps1", *printer_args),
            timeout=300,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if result.returncode:
            (root / "printer-setup-code.txt").write_text(str(result.returncode), encoding="ascii")
            (root / "printer-setup-error.txt").write_text(
                failure_reason(result.returncode) + "\n", encoding="utf-8"
            )
        if not remove and result.returncode == 0:
            installed_marker.touch()
            (root / "secure-port-installed").touch()
            save(config, replace(settings, mode="virtual", virtual_variant=variant))
            detail = "Virtual printer mode is ready. Print to Voucher Reorder while signed in."
            if variant == "print_to_pdf":
                detail += (
                    " Keep the app running; simultaneous PDF jobs can overlap. Check Job status for warnings."
                )
        else:
            save(config, replace(settings, mode="pdf"))
            detail = (
                "PDF handoff mode is ready. Save QuickBooks PDFs in the Inbox shown in Settings. "
                "No administrator access is needed for this mode."
            )
            if not remove and result.returncode:
                detail += " " + failure_reason(result.returncode)
                detail += " Details: " + str(root / "printer-setup-error.txt")
            if remove and result.returncode:
                detail += " The optional Windows printer was not removed. " + failure_reason(
                    result.returncode
                )
        if remove and result.returncode == 0:
            installed_marker.unlink(missing_ok=True)
            (root / "secure-port-installed").unlink(missing_ok=True)
        initialized.touch()
        if action not in ("remove", "setup", "setup-pdf"):
            register_user()
        if ui or action == "remove":
            (root / "mode-status.txt").write_text(detail, encoding="utf-8")
        if action in ("setup", "setup-pdf") or ui:
            print(detail)
        else:
            message(detail)
        return 1 if result.returncode and (remove or action in ("setup", "setup-pdf", "pdf-printer")) else 0
    except Exception as exc:
        # No elevation/setup failure may make the no-admin application unusable.
        (root / "printer-setup-code.txt").write_text("12", encoding="ascii")
        (root / "printer-setup-error.txt").write_text(
            f"{failure_reason(12)} {type(exc).__name__}: {exc}\n", encoding="utf-8"
        )
        save(config, replace(settings, mode="pdf"))
        initialized.touch()
        if action not in ("remove", "setup", "setup-pdf"):
            register_user()
        detail = (
            "Virtual printer setup was unavailable. PDF handoff mode is ready; "
            f"{failure_reason(12)} Details: {root / 'printer-setup-error.txt'}"
        )
        if ui or action == "remove":
            (root / "mode-status.txt").write_text(detail, encoding="utf-8")
        if action in ("setup", "setup-pdf") or ui:
            print(detail)
        else:
            message(detail)
        return 1 if remove or action in ("setup", "setup-pdf", "pdf-printer") else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "auto", ui="--ui" in sys.argv[2:]))
