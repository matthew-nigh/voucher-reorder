"""Both input modes share one per-user, serial, crash-aware print worker."""

import threading
import time

from .config import Settings, atomic_json, data_dir, load
from .bounded import execute
from .inbox import Inbox
from .locking import FileLock
from .queue import Queue
from .windows import convert, forward, message


def process_one(queue, settings, converter=convert, sender=forward):
    if not settings.printer or (queue.root.parent / "maintenance.json").exists():
        return
    with queue.lock, queue.transaction():
        for job in queue.jobs():
            state = queue.read(job)
            if state["state"] != "queued":
                continue
            # Existing alpha jobs have no immutable settings snapshot.
            config = Settings(**state["settings"]) if "settings" in state else settings
            try:
                queue.update(job, "converting")
                if state.get("kind", "ps") == "ps" and converter is not convert:
                    converter(job.parent / "input.ps", job.parent / "input.pdf")
                execute("prepare", job.parent, config)
                queue.update(job, "printing")
                if sender is forward:
                    execute("print", job.parent / "output.pdf", config)
                else:
                    sender(job.parent / "output.pdf", config, queue.root.parent / "sumatra")
                queue.update(job, "sent", "Sent to Windows printer queue; verify physical output.")
            except Exception as error:
                attempted = queue.read(job)["state"] == "printing"
                # Only controlled validation messages may reach status; never raw PDF/parser data.
                detail = (
                    str(error)
                    if type(error) is ValueError
                    and str(error).startswith(
                        ("Flatten optional", "PDF page size", "Printer paper", "Set the printer", "The selected tray")
                    )
                    else "Inspect the real printer queue and paper before reprinting."
                )
                queue.update(job, "review" if attempted else "failed", detail)
                return "A job needs attention. Open Voucher Reorder Job status before reprinting."
            return


def accept_virtual(queue, path, root):
    settings = load(root / "settings.json")
    if not settings.printer:
        raise ValueError("Choose a physical printer before receiving virtual jobs.")
    return queue.accept(path, settings)


def serve():
    root = data_dir()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        with FileLock(root / "worker.lock"):
            if (root / "maintenance.json").exists():
                return
            _serve(root)
    except TimeoutError:
        return


def _serve(root):
    queue = Queue(root / "jobs", recover=True)
    inbox = Inbox(root)
    stop = root / "stop"
    stop.unlink(missing_ok=True)
    try:
        while not stop.exists() and not (root / "maintenance.json").exists():
            warning = None
            try:
                settings = load(root / "settings.json")
                virtual_ready = False
                if settings.mode == "virtual" and settings.printer:
                    try:
                        execute("receive", root, settings)
                        virtual_ready = True
                    except (OSError, ValueError):
                        warning = "Virtual job retained or printer unavailable. Check the Windows queue and provisioning."
                if settings.printer and settings.watch_inbox:
                    warning = inbox.scan(queue, settings) or warning
                alert = process_one(queue, settings)
                if alert:
                    threading.Thread(target=message, args=(alert,), daemon=True).start()
                with queue.lock, queue.transaction():
                    queue.expire()
                atomic_json(
                    root / "worker.json",
                    {
                        "heartbeat": time.time(),
                        "mode": settings.mode,
                        "virtual_ready": virtual_ready,
                        "error": warning,
                    },
                )
            except Exception:
                atomic_json(
                    root / "worker.json",
                    {"heartbeat": time.time(), "error": "Settings or queue need attention."},
                )
            time.sleep(1)
    finally:
        (root / "worker.json").unlink(missing_ok=True)
        stop.unlink(missing_ok=True)
