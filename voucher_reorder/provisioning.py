"""Keep virtual mode tied to the protected package version; PDF mode is independent."""

import os
from dataclasses import replace
from pathlib import Path

from .config import load, save


def check_version(data, version, protected=None):
    protected = (
        protected
        or Path(os.environ.get("ProgramW6432", os.environ.get("ProgramFiles", "C:/Program Files")))
        / "Voucher Reorder Provisioning"
    )
    settings = load(data / "settings.json")
    if settings.mode != "virtual":
        return True
    try:
        matching = (protected / "version.txt").read_text().strip() == version
    except OSError:
        matching = False
    if not matching:
        save(data / "settings.json", replace(settings, mode="pdf"))
        (data / "mode-status.txt").write_text(
            "The app was upgraded. PDF handoff mode is ready. Select the optional virtual printer "
            "component in setup (or Enable virtual printer in Settings) to update its administrator "
            "package to this app version in one prompt.",
            encoding="utf-8",
        )
    return matching
