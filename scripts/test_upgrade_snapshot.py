"""Probe actual v0.2.0 snapshots after the installed watcher acknowledges startup."""

import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

from voucher_reorder.config import data_dir, load, save
from voucher_reorder.lifecycle import stop_worker
from voucher_reorder.locking import FileLock
from voucher_reorder.queue import Queue
from voucher_reorder.worker import process_one


def probe(expected_root):
    root = data_dir()
    assert root.resolve() == expected_root.resolve(), (
        f"Wrong standard-user profile: {root} != {expected_root}"
    )
    # Installer exit only acknowledges its asynchronous register launch. A stop
    # before serve() acquires worker.lock is undone by that late watcher's startup.
    # watcher.json is published after acquiring the lock and opening notifications.
    deadline = time.monotonic() + 30
    while True:
        status = root / "watcher.json"
        if status.exists() and json.loads(status.read_text())["state"] == "waiting":
            break
        if time.monotonic() >= deadline:
            raise AssertionError("Upgraded watcher did not acknowledge startup within 30 seconds")
        time.sleep(0.1)  # Acceptance harness only; the product broker remains event-driven.
    stop_worker(root, timeout=30)
    assert json.loads(status.read_text())["state"] == "stopped", "Watcher did not acknowledge stop"
    # Keep the synthetic sender the sole processor, including against late launches.
    with FileLock(root / "worker.lock", timeout=30), FileLock(root / "processor.lock", timeout=30):
        settings = load(root / "settings.json")
        assert tuple(settings.source_order) == (0, 1, 2), "v0.2.0 source order did not migrate"
        assert tuple(settings.order) == (2, 0, 1), "v0.2.0 destination order changed"
        assert "quickbooks_version" not in asdict(settings) and "printer_model" not in asdict(settings)
        save(root / "settings.json", settings)
        queue = Queue(root / "jobs")
        assert len(queue.jobs()) == 1, "Expected exactly one preserved v0.2.0 job"
        job = queue.jobs()[0]
        before = queue.read(job)
        assert before["state"] == "held", before
        assert "source_order" not in before["settings"], "Fixture must contain an actual v0.2.0 snapshot"
        assert (job.parent / "input.pdf").is_file(), "Held legacy payload was lost before migration"
        queue.update(job, "queued")
        calls = []
        process_one(queue, settings, sender=lambda p, s, a: calls.append(tuple(s.source_order)))
        after = queue.read(job)
        assert calls == [(0, 1, 2)], f"v0.2.0 queued settings did not migrate: calls={calls}, state={after}"
        assert after["state"] == "sent", after
        assert after["settings"] == before["settings"], "Migration mutated the immutable legacy snapshot"
    print("PASS: synchronous v0.2.0 settings and queued snapshot migration")


if __name__ == "__main__":
    try:
        probe(Path(sys.argv[1]))
    except Exception:
        root = data_dir()
        print(f"Migration diagnostics: data_dir={root}, runtime={sys.executable}", flush=True)
        for path in [
            root / name
            for name in ("watcher.json", "worker.json", "settings.json", "maintenance.json", "stop")
        ]:
            print(f"{path}: {path.read_text() if path.exists() else '<absent>'}", flush=True)
        for path in sorted((root / "jobs").glob("*/state.json")):
            print(f"{path}: {path.read_text()}; files={[p.name for p in path.parent.iterdir()]}", flush=True)
        raise
