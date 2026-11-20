"""Generate a vector alignment sheet containing ONLY clearly fake data."""

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from .config import Settings

LABELS = ("CHECK - VOID - SAMPLE ONLY", "VOUCHER STUB 1 - SAMPLE ONLY", "VOUCHER STUB 2 - SAMPLE ONLY")


def create(path, settings: Settings):
    writer = PdfWriter()
    page = writer.add_blank_page(612, 792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
    )
    ops = ["0 G 0 g 0.5 w"]

    def text(x, y, size, value):
        ops.append(f"BT /F1 {size} Tf {x:.6f} {y:.6f} Td ({value}) Tj ET")

    edges = settings.edges(792)
    for i in range(3):
        top, bottom = 792 - edges[i], 792 - edges[i + 1]
        ops.append(f"18 {bottom + 18:.6f} 576 {top - bottom - 36:.6f} re S")
        text(30, top - 42, 16, LABELS[i])
        text(30, top - 62, 10, "TOP EDGE above | LEFT edge here | RIGHT edge at frame")
        text(30, bottom + 26, 10, "BOTTOM EDGE below - Frame is 0.25 inch inside section")
        text(30, top - 82, 10, "Ruler: quarter-inch ticks; numbered marks are whole inches")
        for tick in range(25):
            x = 72 + tick * 18
            y = top - 110
            ops.append(f"{x} {y:.6f} m {x} {y - (12 if tick % 4 == 0 else 6):.6f} l S")
            if tick % 4 == 0:
                text(x - 3, y - 25, 9, str(tick // 4))
        text(72, top - 165, 11, "FAKE EXAMPLE: Example Office / Example Payee / VOID")
    stream = DecodedStreamObject()
    stream.set_data("\n".join(ops).encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    writer.write(path)
