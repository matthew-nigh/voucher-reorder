"""Portable regressions for Windows print supervision and diagnostics."""

import io
import subprocess
import sys
import time

import pytest

from voucher_reorder import bounded
from voucher_reorder.diagnostics import ErrorCapture, sanitize
from voucher_reorder.windows import PrintError, print_run


def test_diagnostics_drop_document_output_and_redact_paths():
    assert sanitize("Private payee and account number\n") == ""
    result = sanitize('VRPRINT failed "Private payee" C:\\Users\\private\\checks.pdf\n')
    assert "Private payee" not in result and "checks.pdf" not in result
    assert "private" not in sanitize("VRPRINT IOException HRESULT=1 line=2: private account 123")
    stream = io.BytesIO(b"private document content\n" * 10000 + b"VRPRINT OutOfMemoryException\n")
    capture = ErrorCapture(stream)
    assert capture.finish() == "VRPRINT OutOfMemoryException\n"


def test_print_engine_failure_preserves_specific_code():
    with pytest.raises(PrintError) as failure:
        print_run([sys.executable, "-c", "raise SystemExit(7)"], code=7)
    assert failure.value.print_code == 7


def test_print_engine_deadline_kills_process():
    started = time.monotonic()
    with pytest.raises(PrintError) as failure:
        print_run([sys.executable, "-c", "import time; time.sleep(30)"], code=7, timeout=0.1)
    assert failure.value.print_code == 8
    assert time.monotonic() - started < 3


def test_batch_budget_scales_with_validated_page_count(tmp_path, monkeypatch):
    # Worker publishes its validated page count; the supervisor must not use the
    # old single-phase deadline for a large batch. No PDF parsing in the parent.
    real_popen = subprocess.Popen
    monkeypatch.setattr(bounded, "TIMEOUT", 0.1)

    def launch(args, **kwargs):
        code = (
            "from pathlib import Path; import time; "
            f"Path({str(tmp_path / 'print-budget.json')!r}).write_text('{{\"pages\":52}}'); "
            "time.sleep(.35)"
        )
        return real_popen([sys.executable, "-c", code], **kwargs)

    monkeypatch.setattr(bounded.subprocess, "Popen", launch)
    bounded.execute("print", tmp_path / "fake.pdf")


def test_print_failure_writes_sanitized_local_diagnostic(tmp_path, monkeypatch):
    real_popen = subprocess.Popen
    monkeypatch.setattr(bounded, "data_dir", lambda: tmp_path / "data")

    def launch(args, **kwargs):
        return real_popen(
            [
                sys.executable,
                "-c",
                'import sys; print("secret account",file=sys.stderr); '
                'print("VRPRINT OutOfMemoryException",file=sys.stderr); sys.exit(7)',
            ],
            **kwargs,
        )

    monkeypatch.setattr(bounded.subprocess, "Popen", launch)
    with pytest.raises(ValueError, match="code 7"):
        bounded.execute("print", tmp_path / "fake.pdf")
    log = (tmp_path / "data/print-error.log").read_text()
    assert "OutOfMemoryException" in log and "secret account" not in log


def test_provisioning_mismatch_uses_pdf_without_blocking_upgrade(tmp_path):
    from voucher_reorder.config import Settings, load, save
    from voucher_reorder.provisioning import check_version

    data, protected = tmp_path / "data", tmp_path / "protected"
    protected.mkdir()
    (protected / "version.txt").write_text("0.2.0")
    save(data / "settings.json", Settings(mode="virtual", printer="FAKE"))
    assert not check_version(data, "0.2.1", protected)
    assert load(data / "settings.json").mode == "pdf"
    assert load(data / "settings.json").printer == "FAKE"
    assert "one prompt" in (data / "mode-status.txt").read_text()
    save(data / "settings.json", Settings(mode="virtual"))
    assert check_version(data, "0.2.0", protected)
    assert load(data / "settings.json").mode == "virtual"


def test_print_error_code_reaches_job_status(tmp_path, monkeypatch):
    from test_engine import sample

    from voucher_reorder import worker
    from voucher_reorder.config import Settings
    from voucher_reorder.queue import Queue

    settings = Settings(printer="FAKE")
    queue = Queue(tmp_path / "jobs")
    queue.accept_bytes(sample().getvalue(), settings)

    def fail_print(operation, *args):
        if operation == "print":
            raise ValueError(bounded.ERRORS[7])

    monkeypatch.setattr(worker, "execute", fail_print)
    worker.process_one(queue, settings)
    state = queue.read(queue.jobs()[0])
    assert state["state"] == "review"
    assert "code 7" in str(state)
