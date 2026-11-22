import os
import threading
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_engine import sample

from voucher_reorder import filesystem
from voucher_reorder.config import Settings, atomic_json
from voucher_reorder.printing import save_pdf
from voucher_reorder.queue import Queue
from voucher_reorder.worker import process_one


@pytest.mark.parametrize("winerror", [5, 32, 33])
def test_metadata_publication_retries_without_resubmitting_job(tmp_path, monkeypatch, winerror):
    queue = Queue(tmp_path / "jobs")
    settings = Settings(printer="FAKE")
    queue.accept_bytes(sample().getvalue(), settings)
    real_replace = os.replace
    blocked = []
    delays = []
    sent = []

    def busy_metadata(source, destination):
        # Hold up only the terminal metadata after the sender already succeeded.
        if sent and len(blocked) < 3:
            blocked.append((source, destination))
            error = PermissionError("simulated Windows file sharing")
            error.winerror = winerror
            raise error
        return real_replace(source, destination)

    monkeypatch.setattr(filesystem, "os", SimpleNamespace(replace=busy_metadata))
    monkeypatch.setattr(filesystem, "time", SimpleNamespace(sleep=delays.append))
    process_one(queue, settings, sender=lambda *args: sent.append(True))
    assert sent == [True]
    assert len(set(blocked)) == 1  # Retry the same completed metadata, not the job.
    assert delays == [0.05, 0.1, 0.2]
    assert queue.read(queue.jobs()[0])["state"] == "sent"
    assert not (queue.jobs()[0].parent / "input.pdf").exists()


@pytest.mark.parametrize("winerror,attempts", [(32, 10), (112, 1), (None, 1)])
def test_permanent_publish_failure_is_bounded_and_preserves_old_file(
    tmp_path, monkeypatch, winerror, attempts
):
    path = tmp_path / "state.json"
    atomic_json(path, {"state": "printing"})
    previous = path.read_bytes()
    calls = []
    delays = []

    def fail(source, destination):
        calls.append((source, destination))
        error = OSError("permanent failure")
        error.winerror = winerror
        raise error

    monkeypatch.setattr(filesystem, "os", SimpleNamespace(replace=fail))
    monkeypatch.setattr(filesystem, "time", SimpleNamespace(sleep=delays.append))
    with pytest.raises(OSError):
        atomic_json(path, {"state": "sent"})
    assert len(calls) == attempts
    assert sum(delays) <= 3.25
    assert path.read_bytes() == previous
    assert not list(tmp_path.glob(".tmp-*"))


def test_pdf_publication_retries_same_destination(tmp_path, monkeypatch):
    source = tmp_path / "output.pdf"
    source.write_bytes(sample().getvalue())
    real_replace = os.replace
    targets = []

    def busy_once(source, destination):
        targets.append(destination)
        if len(targets) == 1:
            error = PermissionError("scanner holds temp file")
            error.winerror = 32
            raise error
        return real_replace(source, destination)

    monkeypatch.setattr(filesystem, "os", SimpleNamespace(replace=busy_once))
    monkeypatch.setattr(filesystem, "time", SimpleNamespace(sleep=lambda delay: None))
    settings = replace(Settings(), output_mode="pdf", output_folder=str(tmp_path / "saved"))
    destination = save_pdf(source, settings, tmp_path)
    assert targets == [destination, destination]
    assert list(destination.parent.iterdir()) == [destination]
    assert destination.read_bytes() == source.read_bytes()


@pytest.mark.skipif(os.name != "nt", reason="Real Windows DELETE-sharing semantics")
def test_real_windows_reader_releases_metadata_before_retry(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    atomic_json(path, {"state": "printing"})
    ready, release = threading.Event(), threading.Event()

    def reader():
        with path.open("rb") as stream:
            assert stream.read()
            ready.set()
            assert release.wait(10)

    thread = threading.Thread(target=reader)
    thread.start()
    assert ready.wait(10)
    retries = []

    def release_reader(delay):
        retries.append(delay)
        release.set()
        thread.join(10)
        assert not thread.is_alive()

    monkeypatch.setattr(filesystem, "time", SimpleNamespace(sleep=release_reader))
    try:
        atomic_json(path, {"state": "sent"})
        assert retries == [0.05]
        assert '"sent"' in path.read_text()
    finally:
        release.set()
        thread.join(10)
