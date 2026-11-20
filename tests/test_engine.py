import io
import itertools
import math

import pymupdf
import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import FloatObject, NameObject, RectangleObject
from reportlab.pdfgen import canvas

from voucher_reorder.alignment import create
from voucher_reorder.config import Settings, load, save
from voucher_reorder.engine import reorder

COLORS = ((1, 0, 0), (0, 1, 0), (0, 0, 1))


def sample(size=(612, 792), pages=1, boundaries=None):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=size, pageCompression=0)
    w, h = size
    edges = Settings(boundaries=boundaries).edges(h)
    for p in range(pages):
        for band in range(3):
            y = h - edges[band + 1]
            c.setFillColorRGB(*COLORS[band])
            c.rect(0, y, w, edges[band + 1] - edges[band], stroke=0, fill=1)
            c.setFillColorRGB(0, 0, 0)
            c.setFont("Helvetica", 14)
            c.drawString(72, h - edges[band] - 60, f"FAKE SAMPLE PAGE {p} BAND {band} VOID")
            c.rect(30, h - edges[band] - 100, 10, 10, stroke=0, fill=1)
        c.showPage()
    c.save()
    buf.seek(0)
    return buf


def pixel(page, x, y):
    pix = page.get_pixmap(matrix=pymupdf.Matrix(1, 1))
    return pix.pixel(int(x), int(y))[:3]


@pytest.mark.parametrize("order", list(itertools.permutations(range(3))))
@pytest.mark.parametrize("size", [(612, 792), (503, 719), (842, 595)])
def test_all_orders_and_odd_sizes(tmp_path, order, size):
    output = tmp_path / "out.pdf"
    reorder(sample(size, pages=3), output, Settings(order=order))
    document = pymupdf.open(output)
    assert len(document) == 3
    for p, page in enumerate(document):
        assert page.rect.width == size[0]
        assert page.rect.height == size[1]
        for slot, source in enumerate(order):
            expected = tuple(int(v * 255) for v in COLORS[source])
            assert pixel(page, 10, (slot + 0.5) * size[1] / 3) == expected
            # Raster testing is ONLY a test oracle. Output stays vector and searchable.
            words = page.get_text("blocks")
            visible = [b for b in words if f"PAGE {p} BAND {source}" in b[4]]
            assert len(visible) == 1
            assert slot * size[1] / 3 < visible[0][1] < (slot + 1) * size[1] / 3
        pdf_page = PdfReader(output).pages[p]
        form = pdf_page["/Resources"]["/XObject"]["/Sheet"]
        assert form["/Subtype"] == "/Form"
        assert "/Font" in form["/Resources"]
        assert "/XObject" not in form["/Resources"]  # no raster image created
        assert b"Tj" in form.get_data()


@pytest.mark.parametrize("source_index", range(3))
@pytest.mark.parametrize("dx,dy", [(0.25, 0.125), (-0.125, -0.25)])
def test_offsets_follow_source_and_clip(tmp_path, source_index, dx, dy):
    offsets = [(0, 0)] * 3
    offsets[source_index] = (dx, dy)
    out = tmp_path / "out.pdf"
    order = (2, 0, 1)
    reorder(sample(), out, Settings(order=order, offsets=offsets))
    page = pymupdf.open(out)[0]
    slot = order.index(source_index)
    assert pixel(page, 35 + dx * 72, slot * 264 + 95 + dy * 72) == (0, 0, 0)
    blocks = [b for b in page.get_text("blocks") if f"BAND {source_index}" in b[4]]
    assert blocks[0][0] == pytest.approx(72 + dx * 72, abs=0.01)
    # A positive horizontal nudge leaves white space; adjacent band remains unchanged.
    if dx > 0:
        assert pixel(page, 5, slot * 264 + 150) == (255, 255, 255)
    for other in range(3):
        if other != slot:
            assert pixel(page, 10, other * 264 + 150) == tuple(int(v * 255) for v in COLORS[order[other]])


def test_unequal_bands_keep_height(tmp_path):
    output = tmp_path / "out.pdf"
    reorder(sample(boundaries=(3.5, 7)), output, Settings(order=(2, 0, 1), boundaries=(3.5, 7)))
    page = pymupdf.open(output)[0]
    assert pixel(page, 10, 280) == (0, 0, 255)  # 4-inch bottom band moved to top
    assert pixel(page, 10, 300) == (255, 0, 0)
    assert pixel(page, 10, 550) == (0, 255, 0)


def test_rotation_and_nonzero_origin(tmp_path):
    writer = PdfWriter()
    page = writer.add_page(PdfReader(sample()).pages[0])
    page.rotate(90)
    rotated = io.BytesIO()
    writer.write(rotated)
    rotated.seek(0)
    out = tmp_path / "rotated.pdf"
    reorder(rotated, out, Settings(order=(0, 1, 2)))
    document = pymupdf.open(out)
    assert document[0].rect == pymupdf.Rect(0, 0, 792, 612)
    assert "FAKE SAMPLE" in document[0].get_text()
    # Translate crop origin into the sheet; content must be translated identically.
    writer = PdfWriter()
    page = writer.add_page(PdfReader(sample()).pages[0])
    page.cropbox = RectangleObject([20, 30, 600, 780])
    cropped = io.BytesIO()
    writer.write(cropped)
    cropped.seek(0)
    reorder(cropped, out, Settings(order=(0, 1, 2)))
    page = pymupdf.open(out)[0]
    assert page.rect == pymupdf.Rect(0, 0, 580, 750)
    block = next(b for b in page.get_text("blocks") if "BAND 0" in b[4])
    assert block[0] == pytest.approx(52)


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(order=(0, 0, 1)),
        dict(order=(0, 1, True)),
        dict(boundaries=(4, 3)),
        dict(boundaries=(0, 7)),
        dict(boundaries=(math.nan, 7)),
        dict(offsets=((2, 0), (0, 0), (0, 0))),
        dict(offsets=((0, math.inf), (0, 0), (0, 0))),
        dict(printer="Voucher Reorder"),
        dict(printer="bad\nname"),
    ],
)
def test_invalid_settings(kwargs):
    with pytest.raises(ValueError):
        Settings(**kwargs)


def test_invalid_page_and_encryption(tmp_path):
    with pytest.raises(ValueError, match="inside"):
        reorder(sample(size=(100, 100)), tmp_path / "out.pdf", Settings(boundaries=(1, 2)))
    writer = PdfWriter()
    writer.add_blank_page(612, 792)
    writer.encrypt("fake-password")
    buf = io.BytesIO()
    writer.write(buf)
    buf.seek(0)
    with pytest.raises(ValueError, match="Encrypted"):
        reorder(buf, tmp_path / "out.pdf", Settings())
    writer = PdfWriter()
    page = writer.add_blank_page(612, 792)
    page[NameObject("/UserUnit")] = FloatObject(2)
    buf = io.BytesIO()
    writer.write(buf)
    buf.seek(0)
    with pytest.raises(ValueError, match="UserUnit"):
        reorder(buf, tmp_path / "out.pdf", Settings())


def test_settings_roundtrip_and_alignment(tmp_path):
    settings = Settings(printer="FAKE OFFICE PRINTER", boundaries=(3.5, 7), order=(2, 1, 0))
    save(tmp_path / "settings.json", settings)
    assert load(tmp_path / "settings.json").order == list(settings.order)
    source = tmp_path / "alignment.pdf"
    create(source, settings)
    reorder(source, tmp_path / "out.pdf", settings)
    text = "".join(p.get_text() for p in pymupdf.open(tmp_path / "out.pdf"))
    for label in ("CHECK - VOID", "VOUCHER STUB 1", "VOUCHER STUB 2", "quarter-inch ticks"):
        assert label in text
