"""Notification scheduling, burst draining and persisted-status regressions."""

import json
import subprocess
import sys

import pytest

from voucher_reorder import spool, watcher, worker
from voucher_reorder.config import Settings, save
from voucher_reorder.notifications import relevant
from voucher_reorder.queue import Queue


class FakeChanges:
    def __init__(self, root):
        self.root = root
        self.attached = False
        self.waits = []
        self.events = []
        self.now = 0

    def watch_printer(self, enabled):
        changed = enabled and not self.attached
        self.attached = enabled
        return changed

    def wait(self, timeout=None):
        self.waits.append(timeout)
        if self.events:
            return self.events.pop(0)()
        if timeout is None:
            (self.root / "stop").touch()
            return {"files"}
        self.now += timeout
        (self.root / "stop").touch()
        return {"timeout"}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def settings(root, **kwargs):
    config = Settings(output_mode="pdf", output_folder=str(root / "saved"), **kwargs)
    save(root / "settings.json", config)
    return config


def test_watcher_import_does_not_load_pdf_or_processing_stack():
    subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import voucher_reorder.app; "
            "import voucher_reorder.watcher; import voucher_reorder.spool; "
            "assert not any(x in sys.modules for x in "
            "('pypdf', 'voucher_reorder.worker', 'voucher_reorder.engine', 'voucher_reorder.printing'))",
        ],
        check=True,
    )


@pytest.mark.parametrize(
    "name", ["Inbox/a.PDF", "jobs/123/state.json", "settings.json", "stop", "maintenance.json", "wake"]
)
def test_ingress_and_lifecycle_changes_wake(name):
    assert relevant(name)


@pytest.mark.parametrize(
    "name",
    [
        "worker.json",
        "watcher.json",
        "queue.lock",
        "settings-123.json",
        "Inbox/a.tmp",
        "jobs/123/output.pdf",
        "inbox-receipts.json",
    ],
)
def test_internal_writes_do_not_wake(name):
    assert not relevant(name)


def test_idle_virtual_watcher_blocks_without_repeated_probes_or_spawns(tmp_path, monkeypatch):
    settings(tmp_path, mode="virtual")
    monkeypatch.setattr(spool, "incoming_folder", lambda: tmp_path / "protected")
    changes = FakeChanges(tmp_path)
    probes = []
    monkeypatch.setattr(spool.Guard, "changed", lambda self: probes.append(True))
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: pytest.fail("idle process spawn"))
    changes.events = [lambda: set(), lambda: set()]
    watcher._serve(tmp_path, lambda root: changes)
    assert len(probes) == 1
    assert len(changes.waits) == 3
    assert all(23 * 3600 <= wait <= 24 * 3600 for wait in changes.waits)
    assert json.loads((tmp_path / "watcher.json").read_text())["state"] == "stopped"


def test_job_at_processor_exit_is_not_lost(tmp_path):
    config = settings(tmp_path)
    queue = Queue(tmp_path / "jobs")
    queue.accept_bytes(b"first", config)
    changes = FakeChanges(tmp_path)
    launched = []

    def launch(root):
        launched.append(True)
        for job in queue.jobs():
            queue.update(job, "sent")
        if len(launched) == 1:
            queue.accept_bytes(b"at exit", config)

    changes.events = [lambda: {"files"}]
    watcher._serve(tmp_path, lambda root: changes, launch)
    assert len(launched) == 2
    assert all(queue.read(j)["state"] == "sent" for j in queue.jobs())


def test_failed_pending_input_does_not_cause_respawn_loop(tmp_path):
    settings(tmp_path)
    (tmp_path / "Inbox").mkdir()
    (tmp_path / "Inbox" / "locked.pdf").write_bytes(b"unfinished")
    changes = FakeChanges(tmp_path)
    changes.events = [lambda: {"files"} for _ in range(5)]
    launched = []
    watcher._serve(tmp_path, lambda root: changes, lambda root: launched.append(True))
    assert launched == []


def test_processor_drains_burst_and_exits_after_idle(tmp_path, monkeypatch):
    config = settings(tmp_path, watch_inbox=False)
    queue = Queue(tmp_path / "jobs")
    for n in range(6):
        queue.accept_bytes(f"job {n}".encode(), config)
    sent = []

    def process(q, config):
        job = next(j for j in q.jobs() if q.read(j)["state"] == "queued")
        sent.append(job)
        q.update(job, "sent")

    monkeypatch.setattr(worker, "process_one", process)
    changes = FakeChanges(tmp_path)
    changes.events = [lambda: set()]  # own ignored writes must not cause a spin
    worker._serve(tmp_path)
    assert len(sent) == 6
    assert changes.waits == []
    assert json.loads((tmp_path / "worker.json").read_text())["state"] == "idle"


def test_secure_spool_guard_only_validates_metadata(tmp_path, monkeypatch):
    guard = spool.Guard(tmp_path)
    jobs = [{"id": n, "key": str(n), "document": f"doc{n}", "status": 0x10} for n in (1, 2)]
    monkeypatch.setattr(guard, "snapshot", lambda: jobs)
    assert guard.changed() is None
    assert not (tmp_path / "printer-pickup.json").exists()


def test_status_does_not_start_process_and_reads_persisted_jobs(tmp_path, monkeypatch, capsys):
    from voucher_reorder import app

    config = settings(tmp_path)
    queue = Queue(tmp_path / "jobs")
    queue.accept_bytes(b"job", config)
    queue.update(queue.jobs()[0], "sent", "Saved reordered PDF")
    (tmp_path / "worker.json").write_text('{"state":"idle"}')
    monkeypatch.setattr(app, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(sys, "argv", ["app.py", "status"])
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: pytest.fail("status launched process"))
    app.main()
    output = capsys.readouterr().out
    assert "idle (last saved state)" in output
    assert "sent: Saved reordered PDF" in output


def test_identical_arrivals_are_unique_and_failure_retry_preserves_pdf(tmp_path):
    from test_engine import sample

    config = settings(tmp_path)
    queue = Queue(tmp_path / "jobs")
    source = tmp_path / "job.pdf"
    payload = sample().getvalue()
    for _ in range(2):
        source.write_bytes(payload)
        queue.accept_file(source, config, "same title/unsafe")
        assert not source.exists()
    first, second = queue.jobs()
    assert first != second
    queue.update(first, "failed", "Test reason")
    attention = tmp_path / "Needs attention" / first.parent.name
    assert (attention / "input.pdf").read_bytes() == payload
    assert json.loads((attention / "reason.json").read_text())["message"] == "Test reason"
    Queue(queue.root, recover=True)
    assert (attention / "input.pdf").exists()
    queue.retry(first.parent.name, config)
    assert queue.read(first)["state"] == "queued"
    assert not attention.exists()
    assert (first.parent / "input.pdf").read_bytes() == payload
    queue.update(first, "sent")
    assert not (first.parent / "input.pdf").exists()
    assert (second.parent / "input.pdf").exists()


@pytest.mark.parametrize("name", ["Incoming", "jobs", "Needs attention"])
def test_output_cannot_target_private_job_folders(tmp_path, monkeypatch, name):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    with pytest.raises(ValueError, match="private job folders"):
        Settings(output_mode="pdf", output_folder=str(tmp_path / "VoucherReorder" / name))


def test_missing_virtual_printer_does_not_block_inbox(tmp_path, monkeypatch):
    from test_engine import sample

    settings(tmp_path, mode="virtual")
    folder = tmp_path / "Inbox"
    folder.mkdir()
    (folder / "job.pdf").write_bytes(sample().getvalue())
    changes = FakeChanges(tmp_path)

    def unavailable(self):
        raise OSError("spooler unavailable")

    monkeypatch.setattr(spool.Guard, "changed", unavailable)
    launched = []
    watcher._serve(tmp_path, lambda root: changes, lambda root: launched.append(True))
    assert launched == [True]
    assert not (folder / "job.pdf").exists()


def test_explicit_wake_allows_retry_after_processor_failure(tmp_path):
    config = settings(tmp_path)
    queue = Queue(tmp_path / "jobs")
    queue.accept_bytes(b"unfinished", config)
    changes = FakeChanges(tmp_path)
    changes.events = [lambda: ((tmp_path / "wake").touch(), {"files"})[1]]
    launches = []
    watcher._serve(tmp_path, lambda root: changes, lambda root: launches.append(True))
    assert launches == [True, True]
