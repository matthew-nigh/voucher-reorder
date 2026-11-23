"""Durable PDF/PS jobs with immutable settings and conservative print recovery."""

import hashlib
import json
import os
import re
import shutil
import stat
import threading
import time
import uuid
from dataclasses import asdict
from pathlib import Path

from .config import Settings, atomic_json
from .locking import FileLock

RETENTION = 24 * 3600
FAILURE_RETENTION = 7 * 24 * 3600
TERMINAL = {"sent", "review", "failed", "discarded", "expired"}
MAX_JOB = 100 * 1024 * 1024


class Queue:
    def __init__(self, root: Path, recover=False):
        self.root = root
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = threading.RLock()
        if recover:
            with self.transaction():
                for job in self.jobs():
                    if self.read(job)["state"] == "receiving":
                        if (job.parent / "input.pdf").exists():
                            self.update(job, "queued", "Recovered completed pickup")
                        else:
                            shutil.rmtree(job.parent)
                            continue
                    if self.read(job)["state"] in ("converting", "printing"):
                        self.update(
                            job,
                            "review",
                            "Interrupted job: inspect the real printer queue and paper before reprinting.",
                        )
                for folder in root.iterdir():
                    if folder.is_dir() and not (folder / "state.json").exists():
                        shutil.rmtree(folder)
                for partial in root.glob("receiving-*"):
                    partial.unlink(missing_ok=True)
                self.expire()

    def transaction(self):
        return FileLock(self.root.parent / "queue.lock", timeout=150)

    def jobs(self):
        return sorted(self.root.glob("*/state.json"), key=lambda p: p.parent.name)

    def read(self, job):
        return json.loads(job.read_text(encoding="utf-8"))

    def update(self, job, state, message=""):
        data = self.read(job)
        data.update(state=state, message=message)
        atomic_json(job, data)
        if state in {"failed", "review"}:
            self.preserve_failure(job)
        elif state in TERMINAL:
            self.clean_payload(job)

    def preserve_failure(self, job):
        state = self.read(job)
        folder = self.root.parent / "Needs attention" / job.parent.name
        folder.mkdir(parents=True, exist_ok=True)
        for name in ("input.pdf", "input.ps"):
            source = job.parent / name
            if source.exists():
                source.replace(folder / name)
        atomic_json(folder / "reason.json", state)
        self.clean_payload(job)

    def retry(self, identifier, settings):
        # Retry requires an explicit user action, especially after uncertain printing.
        with self.lock, self.transaction():
            job = next((j for j in self.jobs() if j.parent.name == identifier), None)
            if job is None or self.read(job)["state"] not in {"failed", "review"}:
                raise ValueError("Select a failed job to retry.")
            folder = self.root.parent / "Needs attention" / identifier
            source = folder / ("input.ps" if self.read(job).get("kind") == "ps" else "input.pdf")
            source.replace(job.parent / source.name)
            state = self.read(job)
            state.update(settings=asdict(settings), state="queued", message="Retry requested by user")
            atomic_json(job, state)
            shutil.rmtree(folder)

    def clear_finished(self):
        """Remove sent job records now; saved PDFs are outside the queue."""
        with self.lock, self.transaction():
            for job in self.jobs():
                if self.read(job)["state"] == "sent":
                    self.reconcile(job, self.read(job))
                    shutil.rmtree(job.parent)

    def dismiss(self, identifier):
        """Remove one failure and its private payload after UI confirmation."""
        with self.lock, self.transaction():
            job = next((j for j in self.jobs() if j.parent.name == identifier), None)
            if job is None or self.read(job)["state"] not in {"failed", "review"}:
                raise ValueError("Select a failed or review job to dismiss.")
            self.reconcile(job, self.read(job))
            failure = self.root.parent / "Needs attention" / identifier
            if failure.exists():
                shutil.rmtree(failure)
            shutil.rmtree(job.parent)

    def accept_file(self, source, settings, document=None, *, protected_spool=False):
        """Claim an arrival by rename, or durable copy/ack from the protected spool.

        Parsing happens later in the bounded processor, never in the broker.
        Repeated identical arrivals are distinct jobs; legacy byte submissions retain deduplication.
        """
        from .inbox import exclusive_read

        if protected_spool and not re.fullmatch(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.pdf", source.name
        ):
            raise ValueError("Invalid protected spool filename")
        attributes = source.lstat()
        if not stat.S_ISREG(attributes.st_mode) or (
            getattr(attributes, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
        ):
            raise ValueError("Watched PDFs must be regular files.")
        with (
            self.lock,
            FileLock(self.root.parent / "queue.lock"),
            exclusive_read(source, movable=True) as stream,
        ):
            if protected_spool:
                folder = self.root / f"spool-{source.stem}"
                existing = folder / "state.json"
                if existing.exists():
                    state = self.read(existing)
                    if state["state"] != "receiving" or (folder / "input.pdf").exists():
                        if state["state"] == "receiving":
                            self.update(existing, "queued", "Recovered completed pickup")
                        self.reconcile(existing, self.read(existing))
                        return existing
                    shutil.rmtree(folder)  # incomplete copy; source is still intact
                elif folder.exists():
                    shutil.rmtree(folder)  # crash between mkdir and metadata commit
            stream.seek(0, 2)
            size = stream.tell()
            if not 0 < size <= MAX_JOB:
                raise ValueError("PDF is empty or exceeds 100 MiB; check the watched folder.")
            stream.seek(0)
            header = stream.read(5)
            stream.seek(max(0, size - 2048))
            if header != b"%PDF-" or b"%%EOF" not in stream.read(2048):
                raise ValueError("PDF is incomplete; finish saving, then use Retry pickup in Job status.")
            if sum(self.read(j)["state"] in {"queued", "held"} for j in self.jobs()) >= 100:
                raise ValueError("The waiting queue is full. Open Job status.")
            total = sum(p.stat().st_size for p in self.root.glob("*/input.*"))
            if total + size > 512 * 1024**2 or shutil.disk_usage(self.root).free < 256 * 1024**2:
                raise ValueError("Insufficient queue space.")
            title = re.sub(r"[^a-zA-Z0-9 _-]", "_", document or source.stem)[:60].strip() or "job"
            if not protected_spool:
                folder = self.root / f"{time.time_ns()}-{uuid.uuid4().hex}-{title}"
            folder.mkdir(mode=0o700)
            # Commit recovery metadata before moving/copying any payload.
            state = {
                "state": "receiving",
                "created": time.time(),
                "digest": "",
                "kind": "pdf",
                "settings": asdict(settings),
                "message": "Claiming PDF",
                "document": title,
            }
            if protected_spool:
                state["pending_spool"] = str(source)
            atomic_json(folder / "state.json", state)
            try:
                if protected_spool:
                    # Different volumes/redirected profiles are supported. Commit a
                    # durable copy before acknowledging the protected source. The
                    # UUID is also the recovery key if deletion or the process fails.
                    stream.seek(0)
                    with (folder / "input.partial").open("xb") as target:
                        shutil.copyfileobj(stream, target)
                        target.flush()
                        os.fsync(target.fileno())
                    (folder / "input.partial").rename(folder / "input.pdf")
                else:
                    source.rename(folder / "input.pdf")
            except BaseException:
                shutil.rmtree(folder)
                raise
            state.update(state="queued", message="Waiting to print")
            atomic_json(folder / "state.json", state)
            self.reconcile(folder / "state.json", state)
            return folder / "state.json"

    def clean_payload(self, job):
        for name in ("input.ps", "input.pdf", "output.pdf", "page.bmp"):
            try:
                (job.parent / name).unlink(missing_ok=True)
            except OSError:
                return False
        for scratch in job.parent.glob("print-temp-*"):
            try:
                shutil.rmtree(scratch)
            except OSError:
                return False
        return True

    def reconcile(self, job, state):
        if state.get("pending_spool") and state["state"] != "receiving":
            Path(state["pending_spool"]).unlink(missing_ok=True)
            del state["pending_spool"]
            atomic_json(job, state)
        source = state.get("pending_receipt")
        if source:
            from .inbox import persist_receipt

            persist_receipt(self.root.parent, *source)
            del state["pending_receipt"]
            atomic_json(job, state)

    def accept_bytes(self, payload, settings: Settings, kind="pdf", source=None, return_job=False):
        if kind not in ("pdf", "ps") or not 0 < len(payload) <= MAX_JOB:
            raise ValueError("Job must be a PDF or PostScript file under 100 MiB.")
        digest = hashlib.sha256(payload).hexdigest()
        with self.lock, self.transaction():
            if (self.root.parent / "maintenance.json").exists():
                raise ValueError("An update is in progress. Try again after setup finishes.")
            for job in self.jobs():
                state = self.read(job)
                self.reconcile(job, state)
                if state["digest"] == digest:
                    if source:
                        state["pending_receipt"] = source
                        atomic_json(job, state)
                        self.reconcile(job, state)
                    return False
            if source:
                receipts = self.root.parent / "inbox-receipts.json"
                if receipts.exists() and json.loads(receipts.read_text()).get(source[0]) == source[1]:
                    return False
            if sum(self.read(j)["state"] in ("queued", "held") for j in self.jobs()) >= 100:
                raise ValueError("The waiting queue is full. Open Job status.")
            total = sum(p.stat().st_size for p in self.root.glob("*/input.*"))
            if (
                total + len(payload) > 512 * 1024**2
                or shutil.disk_usage(self.root).free < len(payload) + 256 * 1024**2
            ):
                raise ValueError("Insufficient queue space.")
            folder = self.root / f"{time.time_ns()}-{uuid.uuid4().hex}"
            folder.mkdir(mode=0o700)
            with (folder / f"input.{kind}").open("wb") as out:
                out.write(payload)
                out.flush()
                os.fsync(out.fileno())
            atomic_json(
                folder / "state.json",
                {
                    "state": "queued",
                    "created": time.time(),
                    "digest": digest,
                    "kind": kind,
                    "settings": asdict(settings),
                    "message": "Waiting to print",
                    "pending_receipt": source,
                },
            )
            if source:
                job = folder / "state.json"
                self.reconcile(job, self.read(job))
            return folder / "state.json" if return_job else True

    def accept(self, path, settings=None):
        return self.accept_bytes(path.read_bytes(), settings or Settings(), "ps")

    def expire(self):
        warning = None
        try:
            days = int(os.environ.get("VOUCHER_REORDER_FAILURE_RETENTION_DAYS", "7"))
            if not 1 <= days <= 365:
                raise ValueError
            failure_retention = days * 24 * 3600
        except ValueError:
            failure_retention = FAILURE_RETENTION
        for job in self.jobs():
            state = self.read(job)
            try:
                self.reconcile(job, state)
                if state["state"] in {"failed", "review"}:
                    if time.time() - state["created"] > failure_retention:
                        failure = self.root.parent / "Needs attention" / job.parent.name
                        if failure.exists():
                            shutil.rmtree(failure)
                        shutil.rmtree(job.parent)
                    else:
                        self.preserve_failure(job)
                elif state["state"] in TERMINAL and not self.clean_payload(job):
                    warning = "Private job cleanup deferred. Close files and check storage."
                if (
                    job.exists()
                    and state["state"] not in {"failed", "review"}
                    and time.time() - state["created"] > RETENTION
                ):
                    shutil.rmtree(job.parent)
            except OSError:
                warning = "Job storage needs attention. Cleanup will be retried."
        return warning

    def hold_waiting(self):
        for job in self.jobs():
            if self.read(job)["state"] == "queued":
                self.update(job, "held", "Held during update. Use Resume held jobs when ready.")
