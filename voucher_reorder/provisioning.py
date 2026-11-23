"""Migrate old retained-printer installations without requiring elevation to upgrade."""

from dataclasses import replace

from .config import load, save


def check_version(data, version, protected=None):
    settings = load(data / "settings.json")
    if settings.mode != "virtual" or (data / "secure-port-installed").exists():
        return True
    save(data / "settings.json", replace(settings, mode="pdf"))
    (data / "mode-status.txt").write_text(
        "The old virtual printer needs migration. PDF mode is ready. Enable virtual printer in "
        "Settings after an administrator verifies and runs the separate PrinterDeploy package. "
        "If setup is blocked or declined, continue saving PDFs in Inbox.",
        encoding="utf-8",
    )
    return False
