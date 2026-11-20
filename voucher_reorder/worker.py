"""Per-user background worker, launched at sign-in; no SYSTEM-level document parsing."""
import threading
import time
from .config import data_dir, load, atomic_json
from .engine import reorder
from .lpr import Server
from .queue import Queue
from .windows import convert, forward, message


def process_one(queue, settings, converter=convert, sender=forward):
    if not settings.printer:
        return
    with queue.lock:
        for job in queue.jobs():
            if queue.read(job)["state"] != "queued":
                continue
            try:
                queue.update(job, "converting")
                converter(job.parent / "input.ps", job.parent / "input.pdf")
                reorder(job.parent / "input.pdf", job.parent / "output.pdf", settings)
                # Production forwarding is letter portrait only. Engine supports arbitrary sizes.
                from pypdf import PdfReader
                for page in PdfReader(job.parent / "output.pdf").pages:
                    if abs(float(page.mediabox.width)-612) > 0.1 or abs(float(page.mediabox.height)-792) > 0.1:
                        raise ValueError("Only portrait Letter jobs can be forwarded.")
                queue.update(job, "printing")
                sender(job.parent / "output.pdf", settings.printer, data_dir() / "sumatra")
                queue.update(job, "sent", "Sent to Windows printer queue; verify physical output.")
            except Exception:
                was_printing = queue.read(job)["state"] == "printing"
                queue.update(job, "review" if was_printing else "failed",
                             "Check both Windows queues and physical output before reprinting.")
                return "A job needs attention. Open Voucher Reorder Settings. Check both printer queues and paper before reprinting."
            return


def serve():
    root = data_dir()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Binding is also the single-instance guard. Do not touch the queue until acquired.
    try:
        server = Server(("127.0.0.1", 515), root / "jobs", lambda path: None)
    except OSError:
        return  # installer probes conflicts; a second launcher must not disturb an active worker
    queue = Queue(root / "jobs")
    server.accept_job = queue.accept
    server.timeout = 1
    stop = root / "stop"
    stop.unlink(missing_ok=True)
    atomic_json(root / "worker.json", {"heartbeat": time.time()})
    receiver = threading.Thread(target=server.serve_forever, daemon=True)
    receiver.start()
    try:
        while not stop.exists():
            try:
                settings = load(root / "settings.json")
                warning = process_one(queue, settings)
                queue.expire()
                atomic_json(root / "worker.json", {"heartbeat": time.time()})
                if warning:
                    # UI is visible only for an exceptional failed job.
                    threading.Thread(target=message, args=(warning,), daemon=True).start()
            except Exception:
                atomic_json(root / "worker.json", {"heartbeat": time.time(), "error": "Settings or queue need attention."})
            time.sleep(1)
    finally:
        server.shutdown()
        server.server_close()
        (root / "worker.json").unlink(missing_ok=True)
        stop.unlink(missing_ok=True)
