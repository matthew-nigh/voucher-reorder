import importlib.util
import json
import sys
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


def test_job_status_cleanup_commands_keep_failed_input(tmp_path, monkeypatch):
    from voucher_reorder import app

    queue = Queue(tmp_path / "jobs")
    for marker, state in (
        (b"sent", "sent"),
        (b"failed", "failed"),
        (b"review", "review"),
        (b"waiting", "queued"),
    ):
        assert queue.accept_bytes(b"%PDF-" + marker, config())
        job = queue.jobs()[-1]
        if state != "queued":
            queue.update(job, state)
    failed = next(j for j in queue.jobs() if queue.read(j)["state"] == "failed")
    review = next(j for j in queue.jobs() if queue.read(j)["state"] == "review")
    failed_id = failed.parent.name
    review_id = review.parent.name
    monkeypatch.setattr(app, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(sys, "argv", ["app.py", "clear-finished"])
    app.main()
    assert sorted(queue.read(j)["state"] for j in queue.jobs()) == ["failed", "queued", "review"]
    monkeypatch.setattr(sys, "argv", ["app.py", "dismiss", "--file", failed_id])
    app.main()
    assert not (tmp_path / "Needs attention" / failed_id).exists()
    assert not failed.exists()
    monkeypatch.setattr(sys, "argv", ["app.py", "dismiss", "--file", review_id])
    app.main()
    assert not (tmp_path / "Needs attention" / review_id).exists()
    assert [queue.read(j)["state"] for j in queue.jobs()] == ["queued"]
    with pytest.raises(ValueError, match="failed or review"):
        app.main()


def test_alignment_queue_returns_exact_job_for_ui(tmp_path):
    queue = Queue(tmp_path / "jobs")
    job = queue.accept_bytes(b"%PDF-alignment", config(), return_job=True)
    assert job == queue.jobs()[0]


def config():
    return Settings(printer="FAKE OFFICE PRINTER", order=(2, 0, 1), offsets=((0.02, 0), (0, -0.03), (0, 0)))


def candidate(root, name, version):
    folder = root / "deployments" / name
    folder.mkdir(parents=True)
    (folder / "PACKAGE.json").write_text(json.dumps({"identity": IDENTITY, "version": version}))
    (folder / "old-library.dll").write_bytes(b"FAKE TEST FILE")
    return folder


def test_pdf_inbox_partial_writes_atomic_pickup_and_no_replay(tmp_path):
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
    inbox.scan(queue, config(), now=9)
    assert len(queue.jobs()) == 1
    assert not path.exists()
    assert (queue.jobs()[0].parent / "input.pdf").read_bytes() == payload
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
    assert (tmp_path / "worker.json").exists()  # status survives a stopped processor


@pytest.mark.parametrize("ui", [False, True])
@pytest.mark.parametrize("exit_code,mode", [(0, "virtual"), (10, "pdf"), (1, "pdf")])
def test_optional_elevation_success_decline_and_failure(tmp_path, monkeypatch, exit_code, mode, ui):
    source = Path(__file__).parents[1] / "packaging/mode_setup.py"
    spec = importlib.util.spec_from_file_location("test_mode_setup", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    save(tmp_path / "settings.json", config())
    monkeypatch.setattr(module, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(module, "stop_worker", lambda *args: None)
    monkeypatch.setattr(module, "powershell", lambda *args: ["fake-command"])
    monkeypatch.setattr(module, "register_user", lambda: None)
    messages = []
    monkeypatch.setattr(module, "message", messages.append)
    monkeypatch.setattr(module.subprocess, "CREATE_NO_WINDOW", 0, raising=False)
    calls = []

    def run(*args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=exit_code)

    monkeypatch.setattr(module.subprocess, "run", run)
    assert module.main("auto", ui=ui) == 0
    assert len(calls) == 1  # Exactly one elevation-helper invocation.
    assert len(messages) == (0 if ui else 1)
    status_file = tmp_path / "mode-status.txt"
    assert status_file.exists() == ui
    if ui:
        assert ("printer-setup-error.txt" in status_file.read_text()) == (exit_code != 0)
    saved = load(tmp_path / "settings.json")
    assert saved.mode == mode
    assert saved.printer == config().printer
    assert saved.offsets[0] == list(config().offsets[0])


@pytest.mark.parametrize("exit_code", [0, 1])
def test_installer_mode_result_is_only_reported_to_installer(tmp_path, monkeypatch, capsys, exit_code):
    source = Path(__file__).parents[1] / "packaging/mode_setup.py"
    spec = importlib.util.spec_from_file_location("test_mode_install", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    save(tmp_path / "settings.json", config())
    (tmp_path / "mode-status.txt").write_text("stale status")
    (tmp_path / "printer-setup-code.txt").write_text("stale code")
    monkeypatch.setattr(module, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(module, "stop_worker", lambda *args: None)
    monkeypatch.setattr(module, "powershell", lambda *args: ["fake-command"])
    monkeypatch.setattr(module.subprocess, "CREATE_NO_WINDOW", 0, raising=False)
    monkeypatch.setattr(
        module.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=exit_code)
    )
    assert module.main("setup") == exit_code
    assert "mode is ready" in capsys.readouterr().out
    assert not (tmp_path / "mode-status.txt").exists()
    code_file = tmp_path / "printer-setup-code.txt"
    assert code_file.exists() == (exit_code != 0)
    assert (tmp_path / "printer-setup-error.txt").exists() == (exit_code != 0)
    if exit_code:
        assert code_file.read_text() == str(exit_code)


def test_installer_setup_exception_records_failure_without_losing_pdf_mode(tmp_path, monkeypatch):
    source = Path(__file__).parents[1] / "packaging/mode_setup.py"
    spec = importlib.util.spec_from_file_location("test_mode_install_exception", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    save(tmp_path / "settings.json", config())
    monkeypatch.setattr(module, "data_dir", lambda: tmp_path)

    def timeout(*_args):
        raise TimeoutError

    monkeypatch.setattr(module, "stop_worker", timeout)
    assert module.main("setup") == 1
    assert load(tmp_path / "settings.json").mode == "pdf"
    assert (tmp_path / "printer-setup-code.txt").read_text() == "12"


def test_installer_pdf_choice_relaunches_setup_image_and_saves_variant(tmp_path, monkeypatch):
    source = Path(__file__).parents[1] / "packaging/mode_setup.py"
    spec = importlib.util.spec_from_file_location("test_pdf_install_mode", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    save(tmp_path / "settings.json", config())
    calls = []
    monkeypatch.setattr(module, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(module, "stop_worker", lambda *args: None)
    monkeypatch.setattr(module, "powershell", lambda *args: calls.append(args) or ["fake-command"])
    monkeypatch.setattr(module.subprocess, "CREATE_NO_WINDOW", 0, raising=False)
    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=0))
    monkeypatch.setattr(module.sys, "argv", ["mode_setup.py", "setup-pdf", "--installer"])
    assert module.main("setup-pdf") == 0
    assert calls[0][1:3] == ("-Action", "install-pdf")
    assert calls[0][3:] == ("-Installer",)
    assert load(tmp_path / "settings.json").virtual_variant == "print_to_pdf"


def test_elevation_targets_are_setup_image_or_protected_helper():
    root = Path(__file__).parents[1]
    request = (root / "packaging/request_printer.ps1").read_text()
    mode = (root / "packaging/mode_setup.py").read_text()
    installer = (root / "packaging/installer.nsi").read_text()
    assert "-Bootstrap" not in request + mode + installer
    assert "PrinterBootstrap.exe" not in request + mode + installer
    assert "VOUCHER_REORDER_SETUP_IMAGE" in request
    assert "-Setup.exe" in request
    assert "LocalApplicationData" in request and "ApplicationData" in request
    assert "PrinterSetup.exe" in request
    assert "-Installer" in mode


def test_pdf_virtual_setup_failure_is_visible_to_acceptance_runner(tmp_path, monkeypatch):
    source = Path(__file__).parents[1] / "packaging/mode_setup.py"
    spec = importlib.util.spec_from_file_location("test_pdf_mode_setup", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    save(tmp_path / "settings.json", config())
    monkeypatch.setattr(module, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(module, "stop_worker", lambda *args: None)
    monkeypatch.setattr(module, "powershell", lambda *args: ["fake-command"])
    monkeypatch.setattr(module, "register_user", lambda: None)
    monkeypatch.setattr(module.subprocess, "CREATE_NO_WINDOW", 0, raising=False)
    monkeypatch.setattr(
        module.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=16200005)
    )
    assert module.main("pdf-printer", ui=True) == 1
    assert load(tmp_path / "settings.json").mode == "pdf"
    assert (tmp_path / "printer-setup-code.txt").read_text() == "16200005"
    assert "stage 162" in (tmp_path / "printer-setup-error.txt").read_text()
    assert "Windows error 5" in (tmp_path / "mode-status.txt").read_text()


@pytest.mark.parametrize("follow_up", ["pdf", "auto", "pdf-printer"])
def test_settings_follow_up_keeps_error_with_nonzero_code(tmp_path, monkeypatch, follow_up):
    source = Path(__file__).parents[1] / "packaging/mode_setup.py"
    spec = importlib.util.spec_from_file_location("test_mode_follow_up", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    save(tmp_path / "settings.json", config())
    monkeypatch.setattr(module, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(module, "stop_worker", lambda *args: None)
    monkeypatch.setattr(module, "powershell", lambda *args: ["fake-command"])
    monkeypatch.setattr(module, "register_user", lambda: None)
    monkeypatch.setattr(module.subprocess, "CREATE_NO_WINDOW", 0, raising=False)
    results = iter((1620013, 0))
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=next(results)),
    )
    assert module.main("pdf-printer", ui=True) == 1
    code = tmp_path / "printer-setup-code.txt"
    error = tmp_path / "printer-setup-error.txt"
    assert code.read_text() == "1620013"
    assert "Windows error 13" in error.read_text()
    if follow_up == "auto":
        (tmp_path / "mode-initialized").unlink()
    module.main(follow_up, ui=True)
    assert code.read_text() == "1620013"
    assert "Windows error 13" in error.read_text()


@pytest.mark.parametrize("outcome", [0, 1, "timeout"])
def test_removal_reports_failure_and_preserves_retry_marker(tmp_path, monkeypatch, outcome):
    source = Path(__file__).parents[1] / "packaging/mode_setup.py"
    spec = importlib.util.spec_from_file_location("test_mode_remove", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    save(tmp_path / "settings.json", config())
    marker = tmp_path / "virtual-installed"
    marker.touch()
    monkeypatch.setattr(module, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(module, "stop_worker", lambda *args: None)
    monkeypatch.setattr(module, "powershell", lambda *args: ["fake-command"])
    monkeypatch.setattr(module.subprocess, "CREATE_NO_WINDOW", 0, raising=False)

    def run(*args, **kwargs):
        if outcome == "timeout":
            raise TimeoutError("spooler did not finish")
        return SimpleNamespace(returncode=outcome)

    monkeypatch.setattr(module.subprocess, "run", run)
    assert module.main("remove", ui=True) == (0 if outcome == 0 else 1)
    assert marker.exists() == (outcome != 0)
    assert load(tmp_path / "settings.json").mode == "pdf"
    if outcome == 1:
        assert "not removed" in (tmp_path / "mode-status.txt").read_text()


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
    with pytest.raises(ValueError, match="Encrypted"):
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


@pytest.mark.parametrize("printer", ["", "Microsoft Print to PDF", "Microsoft XPS Document Writer"])
def test_pdf_output_without_physical_printer(tmp_path, printer):
    from pypdf import PdfReader

    folder = tmp_path / "saved output"
    settings = Settings(printer=printer, output_mode="pdf", output_folder=str(folder), source_order=(2, 0, 1))
    queue = Queue(tmp_path / "jobs")
    for pages in (1, 10, 10):
        # Unique synthetic jobs, including consecutive 10-page batches.
        from voucher_reorder.alignment import create

        source = tmp_path / "FAKE.pdf"
        create(source, settings)
        from pypdf import PdfWriter

        writer = PdfWriter()
        for _ in range(pages):
            writer.add_page(PdfReader(source).pages[0])
        writer.add_metadata({"/Title": str(len(queue.jobs()))})
        writer.write(source)
        queue.accept_bytes(source.read_bytes(), settings)
        process_one(queue, settings, sender=lambda *args: pytest.fail("called Windows printer"))
        job = queue.jobs()[-1]
        state = queue.read(job)
        assert state["state"] == "sent", state
        assert "Saved reordered PDF:" in state["message"]
        output = Path(state["message"].removeprefix("Saved reordered PDF: "))
        assert output.parent == folder
        assert len(PdfReader(output).pages) == pages
        assert b"Tj" in PdfReader(output).pages[0]["/Resources"]["/XObject"]["/Sheet"].get_data()
        assert not (job.parent / "output.pdf").exists()
    assert len(list(folder.glob("*.pdf"))) == 3
    assert not list(folder.glob("*.tmp"))


def test_export_can_be_reprinted_but_unchanged_inbox_receipt_is_not_replayed(tmp_path):
    from voucher_reorder.engine import reorder

    inbox = Inbox(tmp_path)
    output = inbox.folder / "copied-back.pdf"
    reorder(sample(), output, Settings())
    queue = Queue(tmp_path / "jobs")
    settings = Settings(output_mode="pdf", output_folder=str(tmp_path / "output"))
    for watcher in (inbox, Inbox(tmp_path)):
        watcher.scan(queue, settings, now=0)
        watcher.scan(queue, settings, now=4)
        assert len(queue.jobs()) == 1
    assert not output.exists()
    assert read_pdf(queue.jobs()[0].parent / "input.pdf")
    process_one(queue, settings)
    assert queue.read(queue.jobs()[0])["state"] == "sent"


@pytest.mark.parametrize("child", ["", "nested"])
def test_export_folder_cannot_be_in_inbox(tmp_path, monkeypatch, child):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    with pytest.raises(ValueError, match="outside the Inbox"):
        Settings(output_mode="pdf", output_folder=str(tmp_path / "VoucherReorder" / "Inbox" / child))


def test_export_checks_queue_inbox_and_folder_failure(tmp_path):
    settings = Settings(output_mode="pdf", output_folder=str(tmp_path / "Inbox"))
    queue = Queue(tmp_path / "jobs")
    queue.accept_bytes(sample().getvalue(), settings)
    process_one(queue, settings)
    assert queue.read(queue.jobs()[0])["state"] == "review"
    assert not list((tmp_path / "Inbox").glob("*.pdf"))


@pytest.mark.parametrize("printer", ["Voucher Reorder", "voucher reorder", " Voucher Reorder "])
def test_self_output_always_rejected(tmp_path, printer):
    with pytest.raises(ValueError, match="loop"):
        Settings(printer=printer, output_mode="pdf", output_folder=str(tmp_path))


def test_pdf_export_rejects_images_and_blank_pages(tmp_path):
    import io

    from PIL import Image
    from pypdf import PdfWriter
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    from voucher_reorder.printing import validate_vector_pdf

    blank = tmp_path / "blank.pdf"
    writer = PdfWriter()
    writer.add_blank_page(612, 792)
    writer.write(blank)
    with pytest.raises(ValueError, match="blank"):
        validate_vector_pdf(blank)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(612, 792))
    c.drawImage(ImageReader(Image.new("RGB", (1, 1))), 50, 50, 100, 100)
    c.save()
    queue = Queue(tmp_path / "jobs")
    settings = Settings(output_mode="pdf", output_folder=str(tmp_path / "output"))
    queue.accept_bytes(buf.getvalue(), settings)
    process_one(queue, settings)
    assert queue.read(queue.jobs()[0])["state"] == "failed"
    assert not (tmp_path / "output").exists()


def test_pdf_preflight_handles_indirect_resources_and_soft_mask_images(tmp_path):
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject, NumberObject

    from voucher_reorder.printing import validate_vector_pdf

    writer = PdfWriter()
    page = writer.add_page(PdfReader(sample()).pages[0])
    resources = page["/Resources"]
    # Real producers can make the resources dictionaries indirect objects.
    resources[NameObject("/Font")] = writer._add_object(resources["/Font"])
    page[NameObject("/Resources")] = writer._add_object(resources)
    path = tmp_path / "vector.pdf"
    writer.write(path)
    validate_vector_pdf(path)
    bitmap = DecodedStreamObject()
    bitmap.set_data(b"\x00")
    bitmap.update({NameObject("/Subtype"): NameObject("/Image"), NameObject("/Width"): NumberObject(1)})
    group = DecodedStreamObject()
    group.set_data(b"/Im Do")
    group[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/XObject"): writer._add_object(
                DictionaryObject({NameObject("/Im"): writer._add_object(bitmap)})
            )
        }
    )
    resources[NameObject("/ExtGState")] = DictionaryObject(
        {
            NameObject("/GS"): DictionaryObject(
                {NameObject("/SMask"): DictionaryObject({NameObject("/G"): writer._add_object(group)})}
            )
        }
    )
    writer.write(path)
    with pytest.raises(ValueError, match="image content"):
        validate_vector_pdf(path)


def test_pdf_export_folder_alias_cannot_point_into_inbox(tmp_path, monkeypatch):
    import os

    if os.name == "nt":
        pytest.skip("Creating directory symlinks requires Windows developer mode or elevation")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    inbox = tmp_path / "VoucherReorder" / "Inbox"
    inbox.mkdir(parents=True)
    alias = tmp_path / "output-alias"
    alias.symlink_to(inbox, target_is_directory=True)
    with pytest.raises(ValueError, match="outside the Inbox"):
        Settings(output_mode="pdf", output_folder=str(alias))
