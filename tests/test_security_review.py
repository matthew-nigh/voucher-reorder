"""Synthetic security regressions; see SECURITY_REVIEW.md for threat assumptions.

No real documents, installed printers, privileged operations or fixed ports are used.
"""

import io
import subprocess
import sys
import time

import pymupdf
import pytest
from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
    TextStringObject,
)
from test_engine import sample
from test_user_workflow import candidate

from voucher_reorder import inbox as inbox_module
from voucher_reorder.config import Settings, atomic_json
from voucher_reorder.deployment import install
from voucher_reorder.engine import reorder
from voucher_reorder.inbox import Inbox
from voucher_reorder.queue import RETENTION, Queue

SETTINGS = Settings(printer="FAKE SECURITY REVIEW PRINTER")


def test_malformed_xref_finishes_in_bounded_time(tmp_path):
    # Adapted from the public upstream regression in py-pdf/pypdf PR #4170.
    # A subprocess timeout terminates the child; never hang the test runner.
    body = (
        b"%PDF-1.0\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\n"
    )
    tail = b"\nstartxref\n%d\n%%%%EOF" % len(body)
    path = tmp_path / "FAKE-xref.pdf"
    path.write_bytes(body + b"xref\n0 3\n0000000000 65535 f \n" + tail)
    code = (
        "import sys; from pathlib import Path; from voucher_reorder.inbox import read_pdf; "
        "read_pdf(Path(sys.argv[1]))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code, str(path)], capture_output=True, timeout=3, check=False
    )
    assert result.returncode != 0, "Malformed input must be rejected"


def test_bad_inbox_pdf_does_not_block_valid_job(tmp_path):
    inbox = Inbox(tmp_path)
    queue = Queue(tmp_path / "jobs")
    (inbox.folder / "00-FAKE-bad.pdf").write_bytes(b"%PDF-1.7\nnot a PDF\n%%EOF\n")
    (inbox.folder / "01-FAKE-good.pdf").write_bytes(sample().getvalue())
    inbox.scan(queue, SETTINGS, now=0)
    assert inbox.scan(queue, SETTINGS, now=4)  # warning, while continuing the scan
    assert len(queue.jobs()) == 1


def test_inbox_retries_receipt_after_transient_disk_failure(tmp_path, monkeypatch):
    inbox = Inbox(tmp_path)
    queue = Queue(tmp_path / "jobs")
    source = inbox.folder / "FAKE.pdf"
    source.write_bytes(sample().getvalue())
    inbox.scan(queue, SETTINGS, now=0)

    def disk_full(*args):
        raise OSError("FAKE transient disk failure")

    with monkeypatch.context() as patch:
        patch.setattr(inbox_module, "atomic_json", disk_full)
        inbox.scan(queue, SETTINGS, now=4)
    assert len(queue.jobs()) == 1  # admission committed before receipt write
    inbox.scan(queue, SETTINGS, now=5)
    assert inbox.receipts.exists(), "In-memory receipt suppressed the retry after disk recovered"


def test_receipt_failure_does_not_reprint_original_after_retention(tmp_path, monkeypatch):
    inbox = Inbox(tmp_path)
    queue = Queue(tmp_path / "jobs")
    (inbox.folder / "FAKE.pdf").write_bytes(sample().getvalue())
    inbox.scan(queue, SETTINGS, now=0)

    def disk_full(*args):
        raise OSError("FAKE transient disk failure")

    with monkeypatch.context() as patch:
        patch.setattr(inbox_module, "atomic_json", disk_full)
        inbox.scan(queue, SETTINGS, now=4)
    job = queue.jobs()[0]
    queue.update(job, "sent", "FAKE successful handoff")
    state = queue.read(job)
    state["created"] = time.time() - RETENTION - 1
    atomic_json(job, state)
    queue.expire()
    restarted = Inbox(tmp_path)
    restarted.scan(queue, SETTINGS, now=10)
    restarted.scan(queue, SETTINGS, now=14)
    assert not queue.jobs(), "Unchanged already-sent Inbox original was queued again"


def hidden_layer_pdf():
    writer = PdfWriter()
    page = writer.add_blank_page(612, 792)
    layer = writer._add_object(
        DictionaryObject(
            {NameObject("/Type"): NameObject("/OCG"), NameObject("/Name"): TextStringObject("FAKE hidden")}
        )
    )
    writer._root_object[NameObject("/OCProperties")] = DictionaryObject(
        {
            NameObject("/OCGs"): ArrayObject([layer]),
            NameObject("/D"): DictionaryObject(
                {NameObject("/OFF"): ArrayObject([layer]), NameObject("/Order"): ArrayObject([layer])}
            ),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Properties"): DictionaryObject({NameObject("/Hidden"): layer})}
    )
    content = DecodedStreamObject()
    content.set_data(b"/OC /Hidden BDC 0 0 0 rg 0 0 612 792 re f EMC")
    page[NameObject("/Contents")] = writer._add_object(content)
    source = io.BytesIO()
    writer.write(source)
    return source.getvalue()


def test_identity_reorder_preserves_hidden_layer_appearance(tmp_path):
    source = hidden_layer_pdf()
    with pymupdf.open(stream=source, filetype="pdf") as original:
        expected = original[0].get_pixmap().pixel(100, 100)
    assert expected == (255, 255, 255)
    output = tmp_path / "FAKE-out.pdf"
    try:
        reorder(io.BytesIO(source), output, Settings(order=(0, 1, 2)))
    except ValueError:
        return  # Explicitly rejecting unsupported optional content is also safe.
    with pymupdf.open(output) as reordered:
        assert reordered[0].get_pixmap().pixel(100, 100) == expected


def test_install_does_not_delete_another_staged_candidate(tmp_path):
    root, data = tmp_path / "install", tmp_path / "data"
    first = candidate(root, "app-first", "1.0.0")
    # NSIS extracts the entire candidate before manage_install takes install.lock.
    other = candidate(root, "app-other", "1.1.0")
    install(root, first, data, lambda *args: None)
    assert (other / "PACKAGE.json").exists(), "Cleanup removed the other installer's staged payload"


@pytest.mark.parametrize("state", ["sent", "failed", "discarded", "review"])
def test_recovery_removes_payload_left_after_terminal_state_commit(tmp_path, state):
    queue = Queue(tmp_path / "jobs")
    queue.accept_bytes(sample().getvalue(), SETTINGS)
    job = queue.jobs()[0]
    value = queue.read(job)
    value["state"] = state
    # Simulate power loss after atomic state commit but before Queue.update unlinks.
    atomic_json(job, value)
    assert (job.parent / "input.pdf").exists()
    restored = Queue(queue.root, recover=True)
    assert restored.read(job)["state"] == state
    assert not (job.parent / "input.pdf").exists()


def test_over_budget_job_does_not_block_next_job(tmp_path):
    from voucher_reorder.bounded import MAX_PAGES
    from voucher_reorder.worker import process_one

    batch = PdfWriter()
    for _ in range(MAX_PAGES + 1):
        batch.add_blank_page(612, 792)
    stream = io.BytesIO()
    batch.write(stream)
    queue = Queue(tmp_path / "jobs")
    queue.accept_bytes(stream.getvalue(), SETTINGS)
    queue.accept_bytes(sample().getvalue(), SETTINGS)
    sent = []
    for _ in range(2):
        process_one(queue, SETTINGS, sender=lambda *args: sent.append(True))
    assert [queue.read(job)["state"] for job in queue.jobs()] == ["failed", "sent"]
    assert sent == [True]
