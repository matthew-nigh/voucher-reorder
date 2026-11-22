"""Both input modes share one per-user, serial, crash-aware print worker."""

import time

from .bounded import ERRORS, execute
from .config import atomic_json, data_dir, from_dict, load
from .locking import FileLock
from .pdf_errors import MESSAGES as PDF_MESSAGES
from .printing import save_pdf
from .queue import Queue
from .windows import convert, forward


def process_one(queue, settings, converter=convert, sender=forward):
    if not settings.output_ready or (queue.root.parent / "maintenance.json").exists():
        return
    with queue.lock:
        for job in queue.jobs():
            state = queue.read(job)
            if state["state"] != "queued":
                continue
            # Existing alpha jobs have no immutable settings snapshot.
            config = from_dict(state["settings"]) if "settings" in state else settings
            try:
                with queue.transaction():
                    if queue.read(job)["state"] != "queued":
                        continue
                    queue.reconcile(job, state)
                    queue.update(job, "converting")
            except OSError:
                continue  # Keep this job queued until its receipt is durable.
            try:
                if state.get("kind", "ps") == "ps" and converter is not convert:
                    converter(job.parent / "input.ps", job.parent / "input.pdf")
                execute("prepare", job.parent, config)
                queue.update(job, "printing")
                if config.output_mode == "pdf":
                    destination = save_pdf(job.parent / "output.pdf", config, queue.root.parent)
                    queue.update(job, "sent", f"Saved reordered PDF: {destination}")
                    return
                if sender is forward:
                    execute("print", job.parent / "output.pdf", config)
                else:
                    sender(job.parent / "output.pdf", config, queue.root.parent / "sumatra")
                receipt = job.parent / "windows-job-id"
                job_id = receipt.read_text() if receipt.exists() else ""
                suffix = f" (job {job_id})" if job_id.isdecimal() else ""
                queue.update(job, "sent", f"Sent to Windows printer queue{suffix}; verify physical output.")
            except Exception as error:
                attempted = queue.read(job)["state"] == "printing"
                # Only controlled validation messages may reach status; never raw PDF/parser data.
                detail = (
                    str(error)
                    if isinstance(error, ValueError)
                    and (
                        str(error) in ERRORS.values()
                        or str(error) in PDF_MESSAGES.values()
                        or str(error).startswith(
                            (
                                "Flatten optional",
                                "PDF page size",
                                "Printer paper",
                                "Set the printer",
                                "The selected tray",
                            )
                        )
                    )
                    else "Inspect the real printer queue and paper before reprinting."
                )
                if config.output_mode == "pdf" and attempted:
                    detail = "Could not confirm PDF save. Check the output folder and its permissions before retrying."
                queue.update(job, "review" if attempted else "failed", detail)
                return "A job needs attention. Open Voucher Reorder Job status before reprinting."
            return


def serve():
    root = data_dir()
    try:
        with FileLock(root / "processor.lock"):
            if not (root / "maintenance.json").exists():
                _serve(root)
    except TimeoutError:
        return


def _serve(root):
    """Drain durable jobs once, then exit. The broker owns all notifications."""
    from .watcher import stopped

    queue = Queue(root / "jobs", recover=True)
    settings = load(root / "settings.json")
    attempted = set()
    warning = None
    try:
        while settings.output_ready and not stopped(root):
            jobs = [j for j in queue.jobs() if queue.read(j)["state"] == "queued" and j not in attempted]
            if not jobs:
                break
            attempted.add(jobs[0])
            warning = process_one(queue, settings) or warning
    except Exception:
        warning = "Settings or queue need attention."
    finally:
        atomic_json(root / "worker.json", {"updated": time.time(), "state": "idle", "error": warning})
