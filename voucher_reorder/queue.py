"""Crash-aware queue. Never automatically retry an attempted physical print."""
import hashlib
import json
from pathlib import Path
import shutil
import threading
import time
import uuid
from .config import atomic_json

RETENTION = 24 * 3600


class Queue:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = threading.RLock()
        # A previous process may have died between submission and confirmation.
        for job in self.jobs():
            state = self.read(job)
            if state["state"] in ("converting", "printing"):
                self.update(job, "review", "Interrupted job: check physical output before reprinting.")
        for partial in root.glob("receiving-*"):
            partial.unlink(missing_ok=True)
        self.expire()

    def jobs(self):
        return sorted(self.root.glob("*/state.json"), key=lambda p: p.parent.name)

    def read(self, job):
        return json.loads(job.read_text(encoding="utf-8"))

    def update(self, job, state, message=""):
        with self.lock:
            data = self.read(job)
            data.update(state=state, message=message)
            atomic_json(job, data)
            if state in ("sent", "review", "failed", "discarded", "expired"):
                for name in ("input.ps", "input.pdf", "output.pdf"):
                    (job.parent / name).unlink(missing_ok=True)

    def accept(self, path: Path):
        with path.open("rb") as source:
            digest = hashlib.file_digest(source, "sha256").hexdigest()
        with self.lock:
            states = [self.read(job) for job in self.jobs()]
            if any(s["digest"] == digest for s in states):
                # Lost ACK can make Windows resend. A byte-identical job is not printed twice.
                return
            if sum(s["state"] == "queued" for s in states) >= 100:
                raise ValueError("Queue is full")
            folder = self.root / f"{time.time_ns()}-{uuid.uuid4().hex}"
            folder.mkdir(mode=0o700)
            shutil.move(str(path), folder / "input.ps")
            atomic_json(folder / "state.json", {"state": "queued", "created": time.time(),
                "digest": digest, "message": "Waiting to print"})

    def expire(self):
        with self.lock:
            for job in self.jobs():
                if time.time() - self.read(job)["created"] > RETENTION:
                    shutil.rmtree(job.parent)
            # Remove orphaned directories from interrupted admission.
            for folder in self.root.iterdir():
                if folder.is_dir() and not (folder / "state.json").exists():
                    shutil.rmtree(folder)
