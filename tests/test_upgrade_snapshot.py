"""Force the late installer-watcher startup that used to race the migration probe."""

import json
import os
import subprocess
import sys
import time
from dataclasses import asdict
from types import SimpleNamespace

from test_engine import sample

from scripts import test_upgrade_snapshot as probe
from voucher_reorder.config import Settings, atomic_json
from voucher_reorder.queue import Queue


def test_snapshot_probe_waits_for_late_watcher_and_excludes_competing_processor(tmp_path, monkeypatch):
    root = tmp_path / "VoucherReorder"
    queue = Queue(root / "jobs")
    settings = Settings(printer="FAKE", order=(2, 0, 1))
    legacy = asdict(settings)
    del legacy["source_order"]
    legacy.update(quickbooks_version="2024", printer_model="Old printer")
    atomic_json(root / "settings.json", legacy)
    queue.accept_bytes(sample().getvalue(), settings)
    job = queue.jobs()[0]
    state = queue.read(job)
    state.update(state="held", settings=legacy)
    atomic_json(job, state)
    # Pipe-backed notifications let the real watcher acquire/release its locks
    # without relying on a Windows desktop or arbitrary scheduling sleeps.
    bootstrap = """
import sys
from voucher_reorder import watcher
class Changes:
    child = None
    def __init__(self, root): pass
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def watch_printer(self, enabled): return False
    def wait(self):
        sys.stdin.buffer.read(1)
        return {"files"}
serve = watcher._serve
watcher._serve = lambda root: serve(root, changes_factory=Changes)
sys.stdin.buffer.read(1)
watcher.serve()
"""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    child = subprocess.Popen([sys.executable, "-c", bootstrap], stdin=subprocess.PIPE, env=os.environ.copy())
    released = False

    def release_late_start(seconds):
        nonlocal released
        if not released:
            # probe must wait for ready BEFORE it calls stop_worker.
            assert not (root / "stop").exists()
            child.stdin.write(b"s")
            child.stdin.flush()
            released = True
        time.sleep(seconds)

    def wake_and_stop(root, timeout):
        assert released
        (root / "stop").touch()
        child.stdin.write(b"x")
        child.stdin.flush()
        probe_stop(root, timeout=timeout)

    probe_stop = probe.stop_worker
    monkeypatch.setattr(probe, "time", SimpleNamespace(monotonic=time.monotonic, sleep=release_late_start))
    monkeypatch.setattr(probe, "stop_worker", wake_and_stop)
    real_process = probe.process_one

    def exclusive_process(*args, **kwargs):
        from voucher_reorder.worker import serve

        # A real competing processor must exit without stealing this queued job.
        serve()
        assert queue.read(job)["state"] == "queued"
        return real_process(*args, **kwargs)

    monkeypatch.setattr(probe, "process_one", exclusive_process)
    try:
        probe.probe(root)
        assert child.wait(timeout=10) == 0
        assert queue.read(job)["state"] == "sent"
        assert queue.read(job)["settings"] == json.loads(json.dumps(legacy))
        assert json.loads((root / "watcher.json").read_text())["state"] == "stopped"
    finally:
        child.stdin.close()
        if child.poll() is None:
            child.kill()
        child.wait()
