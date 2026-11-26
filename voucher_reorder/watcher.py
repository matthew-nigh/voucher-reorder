"""No-window notification broker; kernel events plus a daily retention deadline."""

import json
import subprocess
import sys
import time
from pathlib import Path

from .config import atomic_json, data_dir, load
from .locking import FileLock
from .notifications import Changes
from .process import background_options


def stopped(root):
    return (root / "stop").exists() or (root / "maintenance.json").exists()


def pending_files(root, settings):
    if not settings.output_ready:
        return ()
    pending = tuple(
        (str(p), p.stat().st_mtime_ns)
        for p in (root / "jobs").glob("*/state.json")
        if json.loads(p.read_text())["state"] in {"queued", "receiving", "converting", "printing"}
    )
    if pending:
        pending += tuple(
            (name, (root / name).stat().st_mtime_ns if (root / name).exists() else 0)
            for name in ("wake", "settings.json")
        )
    return pending


def launch_processor(root):
    app = Path(__file__).resolve().parents[1] / "app.py"
    return subprocess.Popen(
        [sys.executable, str(app), "process"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **background_options(),
    )


def serve():
    root = data_dir()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        with FileLock(root / "worker.lock"):
            if (root / "maintenance.json").exists():
                return
            (root / "stop").unlink(missing_ok=True)
            _serve(root)
    except TimeoutError:
        return


def _serve(root, changes_factory=Changes, launch=launch_processor):
    from .inbox import Inbox
    from .queue import Queue
    from .spool import Guard, incoming_folder

    inbox = Inbox(root)
    queue = Queue(root / "jobs")
    child = None
    guard = Guard(root)
    last_attempt = None
    next_cleanup = 0.0
    pdf_seen = set()
    pdf_collected = 0
    pdf_startup = True
    pdf_pending = False
    with changes_factory(root) as changes:
        sources = {"files", "printer"}
        try:
            while not stopped(root):
                warning = None
                try:
                    if time.monotonic() >= next_cleanup:
                        with queue.lock, queue.transaction():
                            warning = queue.expire()
                        next_cleanup = time.monotonic() + 24 * 3600
                    settings = load(root / "settings.json")
                    virtual = settings.mode == "virtual"
                    pdf_virtual = virtual and settings.virtual_variant == "print_to_pdf"
                    if not pdf_virtual:
                        pdf_pending = False
                    try:
                        attached = changes.watch_printer(virtual)
                        if virtual and (attached or "printer" in sources):
                            jobs = guard.changed("print_to_pdf") if pdf_virtual else guard.changed()
                            if pdf_virtual:
                                pdf_seen.update(job["key"] for job in jobs)
                                if len(jobs) > 1:
                                    warning = "Multiple Print to PDF jobs overlapped in the spooler. Verify every submitted check against Job status."
                    except (OSError, ValueError):
                        warning = "Virtual printer unavailable or needs migration. PDF Inbox remains usable; enable the printer again in Settings."
                        virtual = False
                    if "printer_error" in sources:
                        warning = "Printer notifications interrupted. Reopen Settings before printing again."
                    if "processor" in sources and child is not None:
                        child.wait()
                        if child.returncode:
                            warning = "Processor stopped unexpectedly. Inspect Job status before retrying."
                        child = None
                        changes.child = None
                    if settings.output_ready or pdf_virtual:
                        if virtual:
                            if pdf_virtual:
                                source = root / "Incoming" / "virtual.pdf"
                                if source.exists():
                                    try:
                                        queue.accept_file(source, settings)
                                        pdf_collected += 1
                                        pdf_pending = False
                                        if pdf_startup:
                                            warning = "A PDF was present when the app started. Check it against the Windows print queue for possible overwritten jobs."
                                    except (OSError, ValueError):
                                        pdf_pending = True
                                        warning = "Print to PDF file is open or incomplete. Keep the app running and check Job status."
                                if pdf_startup:
                                    pdf_startup = False
                                if pdf_seen and not pdf_pending:
                                    current = {job["key"] for job in guard.snapshot("print_to_pdf")}
                                    if not current and len(pdf_seen) > pdf_collected:
                                        warning = f"Possible lost PDF print job: observed {len(pdf_seen)} spooler jobs but collected {pdf_collected} files. Check and reprint missing checks."
                                if warning and ("PDF" in warning or "Print to PDF" in warning):
                                    atomic_json(
                                        root / "printer-warning.json",
                                        {"error": warning, "state": "attention", "updated": time.time()},
                                    )
                            else:
                                for source in sorted(incoming_folder().glob("*.ps")):
                                    try:
                                        queue.accept_file(source, settings, protected_spool=True)
                                    except (OSError, ValueError):
                                        warning = "Incoming print job is unavailable. Use Retry pickup in Job status if needed."
                        if settings.watch_inbox:
                            warning = inbox.scan(queue, settings) or warning
                        pending = pending_files(root, settings)
                        if child is None and pending and pending != last_attempt:
                            last_attempt = pending
                            child = launch(root)
                            changes.child = child
                    atomic_json(
                        root / "watcher.json",
                        {
                            "updated": time.time(),
                            "state": "waiting",
                            "error": warning,
                            "mode": settings.mode,
                        },
                    )
                except Exception:
                    atomic_json(
                        root / "watcher.json",
                        {
                            "updated": time.time(),
                            "state": "attention",
                            "error": "Settings, printer or queue need attention. Reopen Settings to retry.",
                        },
                    )
                if stopped(root):
                    break
                timeout = 0.02 if pdf_pending else max(0, next_cleanup - time.monotonic())
                sources = changes.wait(timeout=timeout)
                while not sources and not stopped(root):
                    sources = changes.wait(timeout=timeout)
        finally:
            if child is not None:
                child.wait()
            guard.close()
            atomic_json(root / "watcher.json", {"updated": time.time(), "state": "stopped"})
