"""Protected spool handoff: independent offline arrivals and crash recovery."""

import shutil
import time
import uuid
from pathlib import Path

import pytest
from test_notifications import FakeChanges, settings

from voucher_reorder import spool, watcher
from voucher_reorder.config import Settings, atomic_json
from voucher_reorder.queue import RETENTION, Queue

POSTSCRIPT = (
    b"%!PS-Adobe-3.0\n<< /PageSize [612 792] >> setpagedevice\n"
    b"/Helvetica findfont 14 scalefont setfont\n72 720 moveto (FAKE VOID) show\nshowpage\n"
)


def test_virtual_variant_defaults_to_imagesetter_and_rejects_unknown_driver():
    assert Settings().virtual_variant == "imagesetter"
    assert Settings(virtual_variant="print_to_pdf").virtual_variant == "print_to_pdf"
    with pytest.raises(ValueError, match="variant"):
        Settings(virtual_variant="unknown")


def arrival(folder, data=None):
    folder.mkdir(exist_ok=True)
    source = folder / f"{uuid.uuid4()}.ps"
    source.write_bytes(data or POSTSCRIPT)
    return source


def test_offline_burst_admits_all_unique_files_without_overwrite(tmp_path, monkeypatch):
    settings(tmp_path, mode="virtual")
    incoming = tmp_path / "protected"
    sources = [arrival(incoming) for _ in range(4)]
    (incoming / "unfinished.partial").write_bytes(b"unfinished")
    monkeypatch.setattr(spool, "incoming_folder", lambda: incoming)
    monkeypatch.setattr(spool.Guard, "changed", lambda self: None)
    watcher._serve(tmp_path, FakeChanges, lambda root: None)
    queue = Queue(tmp_path / "jobs")
    assert len(queue.jobs()) == 4
    assert all(queue.read(job)["state"] == "queued" for job in queue.jobs())
    assert all(not source.exists() for source in sources)
    assert len({job.parent.name for job in queue.jobs()}) == 4
    assert (incoming / "unfinished.partial").read_bytes() == b"unfinished"


def test_handoff_copies_across_volumes_without_renaming_protected_source(tmp_path, monkeypatch):
    source = arrival(tmp_path / "protected")
    original = source.read_bytes()
    rename = Path.rename

    def refuse_source_rename(path, target):
        assert path != source, "Cross-volume privileged source cannot be renamed"
        return rename(path, target)

    monkeypatch.setattr(Path, "rename", refuse_source_rename)
    queue = Queue(tmp_path / "jobs")
    job = queue.accept_file(source, Settings(), protected_spool=True)
    assert (job.parent / "input.ps").read_bytes() == original
    assert queue.read(job)["kind"] == "ps"
    assert not source.exists()
    assert "pending_spool" not in queue.read(job)


def test_failed_ack_and_retention_never_create_duplicate_job(tmp_path, monkeypatch):
    source = arrival(tmp_path / "protected")
    queue = Queue(tmp_path / "jobs")
    unlink = Path.unlink

    def fail_ack(path, *args, **kwargs):
        if path == source:
            raise PermissionError("Synthetic locked spool file")
        return unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_ack)
    with pytest.raises(PermissionError):
        queue.accept_file(source, Settings(), protected_spool=True)
    (job,) = queue.jobs()
    state = queue.read(job)
    state["created"] = time.time() - RETENTION - 1
    atomic_json(job, state)
    queue.update(job, "sent")
    assert queue.expire()  # Keep the recovery key until acknowledgement succeeds.
    assert source.exists() and job.exists()
    monkeypatch.setattr(Path, "unlink", unlink)
    restarted = Queue(queue.root)
    assert restarted.accept_file(source, Settings(), protected_spool=True) == job
    assert len(restarted.jobs()) == 1
    assert restarted.read(job)["state"] == "sent"
    assert not source.exists()


@pytest.mark.parametrize("copied", [False, True])
def test_crash_during_copy_or_before_queue_commit_recovers_once(tmp_path, copied):
    source = arrival(tmp_path / "protected")
    payload = source.read_bytes()
    queue = Queue(tmp_path / "jobs")
    folder = queue.root / f"spool-{source.stem}"
    folder.mkdir()
    atomic_json(
        folder / "state.json",
        {
            "state": "receiving",
            "created": time.time(),
            "pending_spool": str(source),
            "settings": {},
            "document": "fake",
            "kind": "ps",
            "digest": "",
        },
    )
    (folder / ("input.ps" if copied else "input.partial")).write_bytes(payload if copied else b"partial")
    job = queue.accept_file(source, Settings(), protected_spool=True)
    assert len(queue.jobs()) == 1
    assert queue.read(job)["state"] == "queued"
    assert (folder / "input.ps").read_bytes() == payload
    assert not source.exists()


@pytest.mark.parametrize("name", ["job.ps", "..ps", "arbitrary.ps", "arbitrary.pdf"])
def test_shared_or_arbitrary_spool_names_are_refused(tmp_path, name):
    source = tmp_path / name
    source.write_bytes(POSTSCRIPT)
    with pytest.raises(ValueError, match="spool filename"):
        Queue(tmp_path / "jobs").accept_file(source, Settings(), protected_spool=True)
    assert source.exists()


def test_protected_spool_requires_postscript_header(tmp_path):
    source = arrival(tmp_path / "protected", b"%PDF-1.4\n%%EOF\n")
    with pytest.raises(ValueError, match="PostScript"):
        Queue(tmp_path / "jobs").accept_file(source, Settings(), protected_spool=True)
    assert source.exists()


def test_protected_postscript_reaches_pdf_output(tmp_path):
    if not shutil.which("gs"):
        pytest.skip("Ghostscript not installed")
    from pypdf import PdfReader

    from voucher_reorder.worker import process_one

    output = tmp_path / "output"
    config = Settings(mode="virtual", output_mode="pdf", output_folder=str(output))
    source = arrival(tmp_path / "protected")
    queue = Queue(tmp_path / "jobs")
    job = queue.accept_file(source, config, protected_spool=True)
    process_one(queue, config)
    assert queue.read(job)["state"] == "sent"
    assert not source.exists()
    assert not (job.parent / "input.ps").exists()
    (pdf,) = output.glob("*.pdf")
    assert len(PdfReader(pdf).pages) == 1


def test_old_fixed_port_marker_requires_migration(tmp_path):
    from voucher_reorder.config import load, save
    from voucher_reorder.provisioning import check_version

    save(tmp_path / "settings.json", Settings(mode="virtual"))
    (tmp_path / "fixed-port-installed").touch()
    assert not check_version(tmp_path, "0.2.6")
    assert load(tmp_path / "settings.json").mode == "pdf"


def test_crash_before_admission_metadata_does_not_block_same_uuid(tmp_path):
    source = arrival(tmp_path / "protected")
    queue = Queue(tmp_path / "jobs")
    folder = queue.root / f"spool-{source.stem}"
    folder.mkdir()
    job = queue.accept_file(source, Settings(), protected_spool=True)
    assert job.parent == folder
    assert queue.read(job)["state"] == "queued"
    assert not source.exists()
