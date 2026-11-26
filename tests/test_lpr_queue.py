import io
import shutil
import socket
import threading
import time

import pytest
from legacy_lpr import MAX_JOB, Server, receive
from test_engine import sample

from voucher_reorder.config import Settings, atomic_json
from voucher_reorder.queue import Queue
from voucher_reorder.worker import process_one


def packet(data=b"%!PS-Adobe-3.0\nFAKE SAMPLE ONLY\n", data_first=False):
    control = b"Hlocalhost\nPFAKE_USER\nfdfA001localhost\n"
    parts = [
        b"\x02" + str(len(control)).encode() + b" ../../ignored\n" + control + b"\0",
        b"\x03" + str(len(data)).encode() + b" ../../ignored\n" + data + b"\0",
    ]
    return b"\x02voucher\n" + b"".join(reversed(parts) if data_first else parts)


@pytest.mark.parametrize("data_first", [False, True])
def test_receive_durable_and_deduplicated(tmp_path, data_first):
    queue = Queue(tmp_path)
    acks = []
    receive(io.BytesIO(packet(data_first=data_first)), acks.append, tmp_path, queue.accept)
    assert acks == [b"\0"] * 5
    assert len(queue.jobs()) == 1
    assert queue.read(queue.jobs()[0])["state"] == "queued"
    receive(io.BytesIO(packet(data_first=data_first)), acks.append, tmp_path, queue.accept)
    assert len(queue.jobs()) == 1
    assert not list(tmp_path.glob("receiving-*"))


@pytest.mark.parametrize(
    "wire",
    [
        b"\x02wrong\n",
        b"\x02voucher\n\x03" + str(MAX_JOB + 1).encode() + b" x\n",
        b"\x02voucher\n\x03-1 x\n",
        b"\x02voucher\n\x03100 x\nshort",
        packet()[:-1] + b"X",
        b"x" * 1025,
        b"\x02voucher\n\x03999 x\n",
    ],
)
def test_bad_job_not_queued(tmp_path, wire):
    queue = Queue(tmp_path)
    with pytest.raises(ValueError):
        receive(io.BytesIO(wire), lambda b: None, tmp_path, queue.accept)
    assert not queue.jobs()
    assert not list(tmp_path.glob("receiving-*"))


def test_real_socket_handshake(tmp_path):
    queue = Queue(tmp_path)
    server = Server(("127.0.0.1", 0), tmp_path, queue.accept)
    thread = threading.Thread(target=server.handle_request)
    thread.start()
    with socket.create_connection(server.server_address, timeout=2) as sock:
        sock.sendall(b"\x02voucher\n")
        assert sock.recv(1) == b"\0"
        for kind, data in [(b"\x02", b"PFAKE_USER\n"), (b"\x03", b"%!PS\nFAKE SAMPLE")]:
            sock.sendall(kind + str(len(data)).encode() + b" ignored\n")
            assert sock.recv(1) == b"\0"
            sock.sendall(data + b"\0")
            assert sock.recv(1) == b"\0"
    thread.join(timeout=3)
    server.server_close()
    assert len(queue.jobs()) == 1


def enqueue(tmp_path):
    queue = Queue(tmp_path / "jobs")
    path = tmp_path / "sample.ps"
    path.write_bytes(b"%!PS FAKE SAMPLE ONLY")
    queue.accept(path)
    return queue, queue.jobs()[0]


def fake_convert(source, output):
    output.write_bytes(sample().getvalue())


def test_success_and_no_printer(tmp_path):
    queue, job = enqueue(tmp_path)
    calls = []
    process_one(queue, Settings(), fake_convert, lambda *args: calls.append(args))
    assert queue.read(job)["state"] == "queued"
    process_one(queue, Settings(printer="FAKE"), fake_convert, lambda *args: calls.append(args))
    assert len(calls) == 1
    assert queue.read(job)["state"] == "sent"
    assert not (job.parent / "input.ps").exists()
    assert not (job.parent / "output.pdf").exists()
    process_one(queue, Settings(printer="FAKE"), fake_convert, lambda *args: calls.append(args))
    assert len(calls) == 1


def test_failure_not_retried(tmp_path):
    queue, job = enqueue(tmp_path)
    calls = []

    def fail(*args):
        calls.append(1)
        raise TimeoutError("untrusted job contents must never enter status")

    assert process_one(queue, Settings(printer="FAKE"), fake_convert, fail)
    assert queue.read(job)["state"] == "review"
    process_one(queue, Settings(printer="FAKE"), fake_convert, fail)
    assert len(calls) == 1
    assert "untrusted" not in job.read_text()
    assert list(job.parent.iterdir()) == [job]


@pytest.mark.parametrize("state", ["converting", "printing"])
def test_crash_recovery(tmp_path, state):
    queue, job = enqueue(tmp_path)
    queue.update(job, state)
    restored = Queue(queue.root, recover=True)
    assert restored.read(job)["state"] == "review"
    assert not (job.parent / "input.ps").exists()


def test_retention(tmp_path):
    queue, job = enqueue(tmp_path)
    state = queue.read(job)
    state["created"] = time.time() - 86401
    atomic_json(job, state)
    queue.expire()
    assert not job.parent.exists()


@pytest.mark.parametrize("state", ["failed", "review"])
def test_failed_job_retention_removes_payload_and_status(tmp_path, state, monkeypatch):
    queue, job = enqueue(tmp_path)
    queue.update(job, state)
    failure = tmp_path / "Needs attention" / job.parent.name
    assert (failure / "input.ps").exists()
    monkeypatch.setenv("VOUCHER_REORDER_FAILURE_RETENTION_DAYS", "2")
    saved = queue.read(job)
    saved["created"] = time.time() - 2 * 86400 - 1
    atomic_json(job, saved)
    queue.expire()
    assert not job.parent.exists()
    assert not failure.exists()


def test_ghostscript_vector_pipeline(tmp_path):
    if not shutil.which("gs"):
        pytest.skip("Ghostscript not installed")
    from pypdf import PdfReader

    from voucher_reorder.windows import convert

    source = tmp_path / "fake.ps"
    source.write_text(
        "%!PS-Adobe-3.0\n<< /PageSize [612 792] >> setpagedevice\n/Helvetica findfont 14 scalefont setfont\n72 720 moveto (FAKE SAMPLE VOID) show\nshowpage\n"
    )
    out = tmp_path / "converted.pdf"
    convert(source, out)
    page = PdfReader(out).pages[0]
    assert "FAKE SAMPLE VOID" in page.extract_text()
    assert "/Font" in page["/Resources"]


def test_final_ack_follows_durable_admission(tmp_path):
    acks = []

    def failed_admission(path):
        assert path.exists()
        assert len(acks) == 4  # final ACK has not been sent
        raise OSError("simulated disk failure")

    with pytest.raises(OSError):
        receive(io.BytesIO(packet()), acks.append, tmp_path, failed_admission)
    assert len(acks) == 4
    assert not list(tmp_path.iterdir())


def test_nonletter_is_rejected_before_physical_forward(tmp_path):
    queue, job = enqueue(tmp_path)
    calls = []

    def odd_convert(source, output):
        output.write_bytes(sample(size=(503, 719)).getvalue())

    process_one(queue, Settings(printer="FAKE"), odd_convert, lambda *args: calls.append(args))
    assert not calls
    assert queue.read(job)["state"] == "failed"
