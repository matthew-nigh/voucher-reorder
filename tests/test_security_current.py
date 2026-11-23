"""Synthetic regressions for the 2026-11-22 review; never print or elevate."""

import io
import os
import stat
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, NameObject, TextStringObject
from test_engine import sample

from voucher_reorder import inbox as inbox_module
from voucher_reorder.config import Settings
from voucher_reorder.engine import reorder
from voucher_reorder.inbox import Inbox
from voucher_reorder.printing import save_pdf
from voucher_reorder.queue import Queue


def symlink_or_skip(link, target):
    try:
        link.symlink_to(target)
    except OSError as error:
        if os.name == "nt" and error.winerror == 1314:
            pytest.skip("Windows account cannot create symlinks")
        raise


@pytest.mark.parametrize("existing", ["file", "symlink"])
def test_pdf_publication_never_overwrites_existing_name(tmp_path, monkeypatch, existing):
    folder = tmp_path / "saved"
    folder.mkdir()
    token = uuid.UUID(int=1)
    monkeypatch.setattr(uuid, "uuid4", lambda: token)
    destination = folder / f"VoucherReorder-{token.hex}.pdf"
    original = b"FAKE user file: must survive"
    victim = tmp_path / "user-file"
    victim.write_bytes(original)
    if existing == "symlink":
        symlink_or_skip(destination, victim)
    else:
        destination.write_bytes(original)
    source = tmp_path / "output.pdf"
    source.write_bytes(sample().getvalue())
    settings = Settings(output_mode="pdf", output_folder=str(folder))

    with pytest.raises(FileExistsError):
        save_pdf(source, settings, tmp_path)

    assert destination.read_bytes() == original
    assert destination.is_symlink() == (existing == "symlink")
    assert victim.read_bytes() == original
    assert list(folder.iterdir()) == [destination]


def test_inbox_symlink_is_not_claimed_and_next_file_is_admitted(tmp_path):
    inbox = Inbox(tmp_path)
    queue = Queue(tmp_path / "jobs")
    target = tmp_path / "private-original.pdf"
    data = sample().getvalue()
    target.write_bytes(data)
    link = inbox.folder / "00-linked.pdf"
    symlink_or_skip(link, target)
    (inbox.folder / "01-normal.pdf").write_bytes(data)

    assert inbox.scan(queue, Settings(printer="FAKE"))
    assert link.is_symlink()
    assert target.read_bytes() == data
    assert len(queue.jobs()) == 1
    assert (queue.jobs()[0].parent / "input.pdf").read_bytes() == data


@pytest.mark.parametrize("kind", ["directory", "fifo", "reparse"])
def test_pickup_rejects_nonregular_or_reparse_file_before_open(tmp_path, monkeypatch, kind):
    queue = Queue(tmp_path / "jobs")
    source = tmp_path / "arrival.pdf"
    source.write_bytes(sample().getvalue())
    attributes = SimpleNamespace(
        st_mode={"directory": stat.S_IFDIR, "fifo": stat.S_IFIFO, "reparse": stat.S_IFREG}[kind],
        st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT if kind == "reparse" else 0,
    )
    original = Path.lstat
    monkeypatch.setattr(Path, "lstat", lambda path: attributes if path == source else original(path))

    def refuse_open(*args, **kwargs):
        pytest.fail("Untrusted special file reached the blocking open")

    monkeypatch.setattr(inbox_module, "exclusive_read", refuse_open)
    with pytest.raises(ValueError, match="regular files"):
        queue.accept_file(source, Settings(printer="FAKE"))
    assert source.exists()
    assert not queue.jobs()


@pytest.mark.parametrize(
    "document", ["../../outside", r"..\..\outside", r"C:\bank:stream", "$(calc);'\nFAKE"]
)
def test_untrusted_document_title_cannot_control_job_path(tmp_path, document):
    queue = Queue(tmp_path / "jobs")
    source = tmp_path / "arrival.pdf"
    source.write_bytes(sample().getvalue())
    job = queue.accept_file(source, Settings(printer="FAKE"), document)
    assert job.parent.parent == queue.root
    assert job.resolve().is_relative_to(queue.root.resolve())
    assert (job.parent / "input.pdf").exists()
    assert all(c.isascii() and (c.isalnum() or c in " _-") for c in queue.read(job)["document"])
    with pytest.raises(ValueError, match="Select a failed job"):
        queue.retry("../../outside", Settings(printer="FAKE"))


@pytest.mark.parametrize("private", ["Inbox", "Incoming", "jobs", "Needs attention"])
def test_output_dotdot_path_cannot_escape_private_folder_check(tmp_path, monkeypatch, private):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    root = tmp_path / "VoucherReorder"
    destination = root / "saved" / ".." / private / "nested"
    with pytest.raises(ValueError, match="outside the Inbox"):
        Settings(output_mode="pdf", output_folder=str(destination))


def test_reordered_pdf_omits_catalog_and_page_actions(tmp_path):
    writer = PdfWriter()
    page = writer.add_page(PdfReader(sample()).pages[0])
    action = writer._add_object(
        DictionaryObject(
            {NameObject("/S"): NameObject("/JavaScript"), NameObject("/JS"): TextStringObject("FAKE")}
        )
    )
    writer._root_object[NameObject("/OpenAction")] = action
    page[NameObject("/AA")] = DictionaryObject({NameObject("/O"): action})
    writer.add_attachment("FAKE.txt", b"FAKE embedded financial data")
    writer.add_metadata({"/Title": "FAKE private title"})
    source = io.BytesIO()
    writer.write(source)
    source.seek(0)
    output = tmp_path / "reordered.pdf"
    reorder(source, output, Settings())
    result = PdfReader(output)
    assert "/OpenAction" not in result.root_object
    assert "/Names" not in result.root_object
    assert all("/AA" not in page for page in result.pages)
    assert result.metadata.title == "Voucher print job"
    assert b"FAKE private title" not in output.read_bytes()


@pytest.mark.parametrize("problem", ["broken-pages", "truncated-stream"])
def test_malformed_pdf_does_not_stop_following_job(tmp_path, problem):
    from voucher_reorder.worker import process_one

    writer = PdfWriter()
    if problem == "broken-pages":
        writer._root_object[NameObject("/Pages")] = TextStringObject("FAKE invalid page tree")
    else:
        writer.add_page(PdfReader(sample()).pages[0])
    stream = io.BytesIO()
    writer.write(stream)
    payload = stream.getvalue()
    if problem == "truncated-stream":
        payload = payload[: len(payload) // 2] + b"\n%%EOF\n"
    inbox = Inbox(tmp_path)
    queue = Queue(tmp_path / "jobs")
    (inbox.folder / "00-malformed.pdf").write_bytes(payload)
    (inbox.folder / "01-valid.pdf").write_bytes(sample().getvalue())
    settings = Settings(printer="FAKE")
    inbox.scan(queue, settings)
    sent = []
    for _ in range(2):
        process_one(queue, settings, sender=lambda *args: sent.append(True))
    assert [queue.read(job)["state"] for job in queue.jobs()] == ["failed", "sent"]
    assert sent == [True]
    assert "FAKE invalid page tree" not in queue.jobs()[0].read_text()
