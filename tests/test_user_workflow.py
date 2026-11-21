import importlib.util
import json
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_engine import sample

from voucher_reorder.config import Settings, load, save
from voucher_reorder.deployment import IDENTITY, active, install
from voucher_reorder.inbox import Inbox, read_pdf
from voucher_reorder.lifecycle import stop_worker
from voucher_reorder.locking import FileLock
from voucher_reorder.queue import Queue
from voucher_reorder.worker import process_one


def config():
    return Settings(printer="FAKE OFFICE PRINTER", order=(2, 0, 1), offsets=((0.02, 0), (0, -0.03), (0, 0)))


def candidate(root, name, version):
    folder = root / "deployments" / name
    folder.mkdir(parents=True)
    (folder / "PACKAGE.json").write_text(json.dumps({"identity": IDENTITY, "version": version}))
    (folder / "old-library.dll").write_bytes(b"FAKE TEST FILE")
    return folder


def test_pdf_inbox_stability_receipts_and_no_original_deletion(tmp_path):
    inbox = Inbox(tmp_path)
    path = inbox.folder / "FAKE.pdf"
    payload = sample().getvalue()
    path.write_bytes(payload[:100])
    queue = Queue(tmp_path / "jobs")
    inbox.scan(queue, config(), now=0)
    assert inbox.scan(queue, config(), now=4)
    assert not queue.jobs()
    path.write_bytes(payload)
    inbox.scan(queue, config(), now=5)
    inbox.scan(queue, config(), now=7)
    assert not queue.jobs()
    inbox.scan(queue, config(), now=9)
    assert len(queue.jobs()) == 1
    assert path.read_bytes() == payload
    # Receipt survives a restart and even expiration of private job records.
    import shutil

    shutil.rmtree(queue.jobs()[0].parent)
    Inbox(tmp_path).scan(queue, config(), now=99)
    assert not queue.jobs()


def test_manual_pdf_job_is_immutable_and_printed_once(tmp_path):
    queue = Queue(tmp_path / "jobs")
    assert queue.accept_bytes(sample().getvalue(), config())
    job = queue.jobs()[0]
    saved = queue.read(job)
    assert saved["settings"]["offsets"][0] == [0.02, 0]
    calls = []
    process_one(queue, Settings(printer="DIFFERENT"), sender=lambda p, s, a: calls.append(s))
    assert calls[0].printer == "FAKE OFFICE PRINTER"
    process_one(queue, config(), sender=lambda *args: calls.append(args))
    assert len(calls) == 1
    assert queue.read(job)["state"] == "sent"
    assert not (job.parent / "input.pdf").exists()


@pytest.mark.parametrize("mode", ["pdf", "virtual"])
def test_upgrade_preserves_settings_holds_jobs_cleans_previous(tmp_path, mode):
    root, data = tmp_path / "app", tmp_path / "data"
    data.mkdir()
    settings = Settings(**{**asdict(config()), "mode": mode})
    save(data / "settings.json", settings)
    original = (data / "settings.json").read_bytes()
    first = candidate(root, "app-first", "0.2.0")
    calls = []
    install(root, first, data, lambda p, v: calls.append((p, v)))
    queue = Queue(data / "jobs")
    queue.accept_bytes(sample().getvalue(), settings)
    job = queue.jobs()[0]
    second = candidate(root, "app-next", "0.3.0")
    install(root, second, data, lambda p, v: calls.append((p, v)))
    assert active(root)["version"] == "0.3.0"
    assert (data / "settings.json").read_bytes() == original
    assert load(data / "settings.json").mode == mode
    assert queue.read(job)["state"] == "held"
    assert (job.parent / "input.pdf").exists()
    assert not first.exists()
    assert second.exists()
    assert not (data / "maintenance.json").exists()
    # Same-version repair is supported, a downgrade is refused without touching data.
    repair = candidate(root, "app-repair", "0.3.0")
    install(root, repair, data, lambda *args: None)
    assert not second.exists()
    lower = candidate(root, "app-lower", "0.2.9")
    with pytest.raises(ValueError, match="Downgrades"):
        install(root, lower, data, lambda *args: pytest.fail("integrated a downgrade"))
    assert active(root)["directory"] == "app-repair"
    assert (data / "settings.json").read_bytes() == original


def test_failed_activation_rolls_back_and_keeps_old_files(tmp_path):
    root, data = tmp_path / "app", tmp_path / "data"
    old = candidate(root, "app-old", "1.0.0")
    install(root, old, data, lambda *args: None)
    new = candidate(root, "app-new", "1.1.0")
    calls = []

    def integrate(path, version):
        calls.append(version)
        if version == "1.1.0":
            raise OSError("simulated integration failure")

    with pytest.raises(OSError):
        install(root, new, data, integrate)
    assert calls == ["1.1.0", "1.0.0"]
    assert active(root)["directory"] == old.name
    assert old.exists()
    assert not (data / "maintenance.json").exists()


def test_update_waits_for_worker_does_not_force_kill(tmp_path):
    root, data = tmp_path / "app", tmp_path / "data"
    old = candidate(root, "app-old", "1.0.0")
    install(root, old, data, lambda *args: None)
    new = candidate(root, "app-new", "1.1.0")
    with FileLock(data / "worker.lock"):
        with pytest.raises(TimeoutError):
            install(root, new, data, lambda *args: pytest.fail("activated while printing"), timeout=0)
        assert active(root)["version"] == "1.0.0"
    assert old.exists()
    assert not (data / "maintenance.json").exists()


def test_stale_heartbeat_does_not_block_shutdown(tmp_path):
    (tmp_path / "worker.json").write_text('{"heartbeat": 0}')
    with FileLock(tmp_path / "worker.lock"):
        with pytest.raises(TimeoutError):
            stop_worker(tmp_path, timeout=0)
    stop_worker(tmp_path, timeout=0)
    assert not (tmp_path / "worker.json").exists()


@pytest.mark.parametrize("exit_code,mode", [(0, "virtual"), (10, "pdf"), (1, "pdf")])
def test_optional_elevation_success_decline_and_failure(tmp_path, monkeypatch, exit_code, mode):
    source = Path(__file__).parents[1] / "packaging/mode_setup.py"
    spec = importlib.util.spec_from_file_location("test_mode_setup", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    save(tmp_path / "settings.json", config())
    monkeypatch.setattr(module, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(module, "stop_worker", lambda *args: None)
    monkeypatch.setattr(module, "powershell", lambda *args: ["fake-command"])
    monkeypatch.setattr(module, "register_user", lambda: None)
    monkeypatch.setattr(module, "message", lambda text: None)
    monkeypatch.setattr(module.subprocess, "CREATE_NO_WINDOW", 0, raising=False)
    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kw: SimpleNamespace(returncode=exit_code))
    assert module.main("auto") == 0
    saved = load(tmp_path / "settings.json")
    assert saved.mode == mode
    assert saved.printer == config().printer
    assert saved.offsets[0] == list(config().offsets[0])


def test_paper_mismatch_holds_without_submission(tmp_path):
    queue = Queue(tmp_path / "jobs")
    queue.accept_bytes(sample(size=(595, 842)).getvalue(), config())
    process_one(queue, config(), sender=lambda *args: pytest.fail("printed a mismatched sheet"))
    state = queue.read(queue.jobs()[0])
    assert state["state"] == "failed"
    assert "page size" in state["message"]


def test_supported_nonletter_paper(tmp_path):
    settings = Settings(printer="FAKE", paper_kind=5, paper_width=8.5, paper_height=14)
    queue = Queue(tmp_path / "jobs")
    queue.accept_bytes(sample(size=(612, 1008)).getvalue(), settings)
    calls = []
    process_one(queue, settings, sender=lambda p, s, a: calls.append(s.paper_kind))
    assert calls == [5]


def test_incomplete_encrypted_pdf_not_admitted(tmp_path):
    from pypdf import PdfWriter

    source = tmp_path / "FAKE.pdf"
    source.write_bytes(b"%PDF-1.7\npartial")
    with pytest.raises(ValueError):
        read_pdf(source)
    writer = PdfWriter()
    writer.add_blank_page(612, 792)
    writer.encrypt("FAKE TEST ONLY")
    writer.write(source)
    with pytest.raises(ValueError, match="unencrypted"):
        read_pdf(source)


def test_v020_settings_and_held_job_migrate(tmp_path):
    legacy = asdict(config())
    del legacy["source_order"]
    legacy.update(quickbooks_version="2024", printer_model="Old printer")
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(legacy))
    settings = load(path)
    assert settings.source_order == (0, 1, 2)
    assert settings.order == list(config().order)
    save(path, settings)
    assert "quickbooks_version" not in json.loads(path.read_text())
    assert "printer_model" not in json.loads(path.read_text())
    queue = Queue(tmp_path / "jobs")
    queue.accept_bytes(sample().getvalue(), settings)
    job = queue.jobs()[0]
    state = queue.read(job)
    state["settings"] = legacy
    job.write_text(json.dumps(state))
    calls = []
    process_one(queue, settings, sender=lambda p, s, a: calls.append(s))
    assert queue.read(job)["state"] == "sent"
    assert calls[0].source_order == (0, 1, 2)
