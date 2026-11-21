"""Both input modes share one per-user, serial, crash-aware print worker."""

import threading
import time

from .config import Settings, atomic_json, data_dir, load
from .engine import reorder
from .inbox import Inbox
from .locking import FileLock
from .lpr import Server
from .printing import validate_pages
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
                if state.get("kind", "ps") == "ps":
                    converter(job.parent / "input.ps", job.parent / "input.pdf")
                reorder(job.parent / "input.pdf", job.parent / "output.pdf", config)
                validate_pages(job.parent / "output.pdf", config)
                queue.update(job, "printing")
                sender(job.parent / "output.pdf", config, queue.root.parent / "sumatra")
                queue.update(job, "sent", "Sent to Windows printer queue; verify physical output.")
            except Exception as error:
                attempted = queue.read(job)["state"] == "printing"
                # Only controlled validation messages may reach status; never raw PDF/parser data.
                detail = (
                    str(error)
                    if type(error) is ValueError
                    and str(error).startswith(
                        ("PDF page size", "Printer paper", "Set the printer", "The selected tray")
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
    server = None
    stop = root / "stop"
    stop.unlink(missing_ok=True)
    try:
        while not stop.exists() and not (root / "maintenance.json").exists():
            warning = None
            try:
                settings = load(root / "settings.json")
                if settings.mode == "virtual" and server is None:
                    try:
                        server = Server(
                            ("127.0.0.1", 515),
                            root / "jobs",
                            lambda p: accept_virtual(queue, p, root),
                        )
                        threading.Thread(target=server.serve_forever, daemon=True).start()
                    except OSError:
                        warning = "Virtual printer is unavailable: local port 515 is in use. Switch to PDF mode or resolve the conflict."
                if settings.mode == "pdf" and server is not None:
                    server.shutdown()
                    server.server_close()
                    server = None
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
                        "virtual_ready": server is not None,
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
        if server:
            server.shutdown()
            server.server_close()
        (root / "worker.json").unlink(missing_ok=True)
        stop.unlink(missing_ok=True)
