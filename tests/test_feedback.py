"""Windows feedback regressions: lossless compact output, reprints and idle work."""

import io
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pymupdf
import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DecodedStreamObject, DictionaryObject, NameObject, NumberObject

from voucher_reorder import bounded, spool, worker
from voucher_reorder.alignment import create
from voucher_reorder.config import Settings, save
from voucher_reorder.engine import reorder
from voucher_reorder.pdf_errors import MESSAGES, PdfError
from voucher_reorder.printing import validate_vector_pdf
from voucher_reorder.queue import Queue


def test_alignment_compact_and_repeated_reprints(tmp_path):
    source = tmp_path / "input.pdf"
    settings = Settings(order=(0, 1, 2))
    create(source, settings)
    with pymupdf.open(source) as original:
        pixels = original[0].get_pixmap().samples
    for index in range(6):
        output = tmp_path / f"output-{index}.pdf"
        bounded.execute("inspect", source)
        validate_vector_pdf(source)
        reorder(source, output, settings)
        assert output.stat().st_size < source.stat().st_size * 2
        assert output.stat().st_size < 10000
        with pymupdf.open(output) as result:
            assert result[0].get_pixmap().samples == pixels
            assert "SAMPLE ONLY" in result[0].get_text()
        page = PdfReader(output).pages[0]
        assert page["/Contents"]["/Filter"] == "/FlateDecode"
        assert page["/Resources"]["/XObject"]["/Sheet"]["/Filter"] == "/FlateDecode"
        source = output


def test_embedded_font_shared_across_pages_and_bytes_unchanged(tmp_path):
    # ReportLab's bundled TrueType fixture exercises the same opaque font-program
    # preservation needed by MICR fonts; no system font substitution is allowed.
    import reportlab
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    font_path = Path(reportlab.__file__).parent / "fonts/Vera.ttf"
    pdfmetrics.registerFont(TTFont("FakeEmbedded", str(font_path)))
    source = tmp_path / "font.pdf"
    c = canvas.Canvas(str(source))
    for i in range(10):
        c.setFont("FakeEmbedded", 12)
        c.drawString(30, 700, f"FAKE MICR FIDELITY 0123456789 {i}")
        c.showPage()
    c.save()
    output = tmp_path / "out.pdf"
    reorder(source, output, Settings(order=(0, 1, 2)))
    before, after = PdfReader(source), PdfReader(output)
    font = next(
        f.get_object()
        for f in before.pages[0]["/Resources"]["/Font"].values()
        if "/FontDescriptor" in f.get_object()
    )
    font_refs = set()
    for page in after.pages:
        fonts = page["/Resources"]["/XObject"]["/Sheet"]["/Resources"]["/Font"]
        copied = next(f.get_object() for f in fonts.values() if "/FontDescriptor" in f.get_object())
        font_refs.add(copied.indirect_reference.idnum)
        assert (
            copied["/FontDescriptor"]["/FontFile2"].get_data()
            == font["/FontDescriptor"]["/FontFile2"].get_data()
        )
        assert copied["/ToUnicode"].get_data() == font["/ToUnicode"].get_data()
        assert copied["/Widths"] == font["/Widths"]
        assert copied["/BaseFont"] == font["/BaseFont"]
    assert len(font_refs) == 1
    assert output.stat().st_size < source.stat().st_size * 1.5


def form_fixture(path, kind="inherited", depth=1):
    writer = PdfWriter()
    page = writer.add_blank_page(612, 792)
    form = DecodedStreamObject()
    form.set_data(b"0 0 20 20 re f")
    form.update(
        {
            NameObject("/Subtype"): NameObject("/Form"),
            NameObject("/BBox"): ArrayObject([NumberObject(n) for n in (0, 0, 612, 792)]),
        }
    )
    for _ in range(depth - 1):
        outer = DecodedStreamObject()
        outer.set_data(b"/Child Do")
        outer.update(
            {
                NameObject("/Subtype"): NameObject("/Form"),
                NameObject("/Resources"): DictionaryObject(
                    {
                        NameObject("/XObject"): DictionaryObject(
                            {NameObject("/Child"): writer._add_object(form)}
                        )
                    }
                ),
            }
        )
        form = outer
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/XObject"): DictionaryObject({NameObject("/Sheet"): writer._add_object(form)})}
    )
    if kind == "recursive":
        form.set_data(b"/Sheet Do")
    content = DecodedStreamObject()
    content.set_data(b"/Sheet Do /Sheet Do /Sheet Do")
    page[NameObject("/Contents")] = writer._add_object(content)
    writer.write(path)


def test_inherited_resources_are_not_recursive_execution(tmp_path):
    source = tmp_path / "input.pdf"
    form_fixture(source)
    validate_vector_pdf(source)
    bounded.execute("prepare", tmp_path, Settings(output_mode="pdf", output_folder=str(tmp_path / "saved")))
    validate_vector_pdf(tmp_path / "output.pdf")


@pytest.mark.parametrize("kind,depth,reason", [("recursive", 1, "recursive"), ("inherited", 42, "depth")])
def test_real_recursion_and_depth_still_rejected_with_specific_reason(tmp_path, kind, depth, reason):
    source = tmp_path / "input.pdf"
    form_fixture(source, kind, depth)
    with pytest.raises(ValueError) as error:
        bounded.execute(
            "prepare", tmp_path, Settings(output_mode="pdf", output_folder=str(tmp_path / "saved"))
        )
    assert str(error.value) == MESSAGES[reason]


@pytest.mark.parametrize("mode", ["pdf", "printer"])
def test_scanned_pdf_specific_reason_reaches_job_status(tmp_path, mode):
    from PIL import Image
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    content = io.BytesIO()
    c = canvas.Canvas(content, pagesize=(612, 792))
    c.drawImage(ImageReader(Image.new("RGB", (2, 2))), 0, 0, 612, 792)
    c.save()
    settings = Settings(output_mode=mode, printer="FAKE", output_folder=str(tmp_path / "saved"))
    queue = Queue(tmp_path / "jobs")
    queue.accept_bytes(content.getvalue(), settings)
    worker.process_one(queue, settings)
    state = queue.read(queue.jobs()[0])
    assert state["state"] == "failed"
    assert state["message"] == MESSAGES["image"]
    assert not (tmp_path / "saved").exists()


def test_page_limit_reason_reaches_job_status(tmp_path):
    writer = PdfWriter()
    for _ in range(bounded.MAX_PAGES + 1):
        writer.add_blank_page(612, 792)
    content = io.BytesIO()
    writer.write(content)
    settings = Settings(output_mode="pdf", output_folder=str(tmp_path / "saved"))
    queue = Queue(tmp_path / "jobs")
    queue.accept_bytes(content.getvalue(), settings)
    worker.process_one(queue, settings)
    assert queue.read(queue.jobs()[0])["message"] == MESSAGES["pages"]


def test_output_and_expanded_limits_remain_enforced(tmp_path, monkeypatch):
    source = tmp_path / "input.pdf"
    create(source, Settings())
    monkeypatch.setattr(bounded, "MAX_OUTPUT", 100)
    with pytest.raises(PdfError, match="Expanded PDF data limit"):
        validate_vector_pdf(source)
    with bounded.LimitedOutput(open(tmp_path / "large.pdf", "wb", buffering=0)) as output:
        with pytest.raises(PdfError, match="output size limit"):
            output.write(b"x" * 101)


def test_untrusted_pdf_error_text_cannot_reach_status():
    from voucher_reorder.diagnostics import sanitize
    from voucher_reorder.pdf_errors import diagnostic_reason

    assert sanitize("VRPDF image\n") == "VRPDF image\n"
    assert sanitize("VRPDF secret payee 1234\n") == ""
    assert diagnostic_reason("VRPDF secret payee 1234") is None


def test_idle_virtual_worker_never_spawns(tmp_path, monkeypatch):
    save(
        tmp_path / "settings.json",
        Settings(mode="virtual", output_mode="pdf", output_folder=str(tmp_path / "saved")),
    )
    polls = []
    monkeypatch.setattr(spool, "poll", lambda excluded: polls.append(excluded))
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: pytest.fail("idle process spawn"))

    def tick(_):
        if len(polls) == 4:
            (tmp_path / "stop").touch()

    monkeypatch.setattr(worker.time, "sleep", tick)
    worker._serve(tmp_path)
    assert polls == [[], [], [], []]


def test_windows_children_disable_startup_feedback(monkeypatch):
    from voucher_reorder.process import background_options

    monkeypatch.setattr(subprocess, "STARTUPINFO", lambda: SimpleNamespace(dwFlags=1), raising=False)
    monkeypatch.setattr(subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    options = background_options()
    assert options["creationflags"] == 0x08000000
    assert options["startupinfo"].dwFlags == 0x81


def test_spool_selection_preserves_owner_status_and_quarantine_checks():
    from voucher_reorder.spool_poll import select_candidate

    printer = dict(
        comment="VoucherReorder owner=S-1-FAKE",
        attributes=0x100,
        port="NUL:",
        driver="MS Publisher Imagesetter",
    )
    jobs = [
        dict(id=i, ticks=i, key=f"{i}-{i}", status=status)
        for i, status in enumerate((0x80, 0x88, 0x90, 0x2000, 0x8, 0))
    ]
    assert select_candidate(printer, jobs, "S-1-FAKE", ["0-0"])["id"] == 3
    assert select_candidate(printer, jobs, "S-1-FAKE", ["0-0", "3-3"]) is None
    for field, value in (
        ("comment", "other owner"),
        ("attributes", 0x108),
        ("attributes", 0),
        ("port", "FILE:"),
        ("driver", "other driver"),
    ):
        with pytest.raises(ValueError, match="owner-restricted"):
            select_candidate({**printer, field: value}, jobs, "S-1-FAKE", [])


@pytest.mark.parametrize("location", ["form", "pattern", "glyph", "mask"])
@pytest.mark.parametrize(
    "content,reason", [(b"BI /W 1 /H 1 /BPC 8 /CS /G ID \x00 EI", "image"), (b"/Loop Do", "recursive")]
)
def test_hidden_resource_programs_cannot_bypass_preflight(tmp_path, location, content, reason):
    writer = PdfWriter()
    page = writer.add_blank_page(612, 792)
    program = DecodedStreamObject()
    program.set_data(content)
    program[NameObject("/Subtype")] = NameObject("/Form")
    ref = writer._add_object(program)
    resources = DictionaryObject({NameObject("/XObject"): DictionaryObject({NameObject("/Loop"): ref})})
    program[NameObject("/Resources")] = resources
    if location == "pattern":
        program[NameObject("/PatternType")] = NumberObject(1)
        resources = DictionaryObject({NameObject("/Pattern"): DictionaryObject({NameObject("/P"): ref})})
    elif location == "glyph":
        resources = DictionaryObject(
            {
                NameObject("/Font"): DictionaryObject(
                    {
                        NameObject("/F"): DictionaryObject(
                            {
                                NameObject("/Subtype"): NameObject("/Type3"),
                                NameObject("/Resources"): resources,
                                NameObject("/CharProcs"): DictionaryObject({NameObject("/A"): ref}),
                            }
                        )
                    }
                )
            }
        )
    elif location == "mask":
        resources = DictionaryObject(
            {
                NameObject("/ExtGState"): DictionaryObject(
                    {
                        NameObject("/GS"): DictionaryObject(
                            {NameObject("/SMask"): DictionaryObject({NameObject("/G"): ref})}
                        )
                    }
                )
            }
        )
    page[NameObject("/Resources")] = resources
    painted = DecodedStreamObject()
    painted.set_data(b"0 0 10 10 re f")
    page[NameObject("/Contents")] = writer._add_object(painted)
    source = tmp_path / "hidden.pdf"
    writer.write(source)
    with pytest.raises(PdfError) as error:
        validate_vector_pdf(source)
    assert error.value.reason == reason


def test_decompression_bomb_names_existing_pypdf_limit(tmp_path):
    import zlib

    from pypdf.generic import EncodedStreamObject

    # Generate a small compressed bomb incrementally; the parent test never
    # allocates its 76 MB expansion. The bounded child must enforce pypdf's cap.
    compressor = zlib.compressobj()
    chunks = [compressor.compress(b" " * 1000000) for _ in range(76)]
    stream = EncodedStreamObject()
    stream._data = b"".join(chunks) + compressor.flush()
    stream[NameObject("/Filter")] = NameObject("/FlateDecode")
    writer = PdfWriter()
    page = writer.add_blank_page(612, 792)
    page[NameObject("/Contents")] = writer._add_object(stream)
    writer.write(tmp_path / "input.pdf")
    with pytest.raises(ValueError) as error:
        bounded.execute("prepare", tmp_path)
    assert str(error.value) == MESSAGES["decompression"]


@pytest.mark.parametrize(
    "detail,reason",
    [
        ("Maximum XRef stream entry limit reached: 123", "xref"),
        ("Reached maximum number of tokens per stream.", "tokens"),
        ("Maximum filter count 10 exceeded: 11", "filters"),
        ("Declared stream length of 123 exceeds maximum allowed length.", "stream_length"),
        ("Detected cycle in /Parent hierarchy for key 'private payee'.", "parser_cycle"),
        ("Unknown exception containing private account 1234", "parser_limit"),
    ],
)
def test_parser_limits_use_fixed_messages_only(detail, reason):
    from pypdf.errors import LimitReachedError

    from voucher_reorder.pdf_errors import parser_limit_reason

    assert parser_limit_reason(LimitReachedError(detail)) == reason
    assert "private" not in MESSAGES[reason]
