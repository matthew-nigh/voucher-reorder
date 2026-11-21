"""Native preflight must refuse blank and image pages before creating a printer job."""

import sys
from pathlib import Path

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject, NumberObject

from voucher_reorder.bounded import execute
from voucher_reorder.config import Settings


def check(folder, printer):
    for kind in ("blank", "image"):
        writer = PdfWriter()
        page = writer.add_blank_page(612, 792)
        if kind == "image":
            bitmap = DecodedStreamObject()
            bitmap.set_data(b"\x00\x00\x00")
            bitmap.update(
                {
                    NameObject("/Type"): NameObject("/XObject"),
                    NameObject("/Subtype"): NameObject("/Image"),
                    NameObject("/Width"): NumberObject(1),
                    NameObject("/Height"): NumberObject(1),
                    NameObject("/ColorSpace"): NameObject("/DeviceRGB"),
                    NameObject("/BitsPerComponent"): NumberObject(8),
                }
            )
            page[NameObject("/Resources")] = DictionaryObject(
                {NameObject("/XObject"): DictionaryObject({NameObject("/Im"): writer._add_object(bitmap)})}
            )
            content = DecodedStreamObject()
            content.set_data(b"q 100 0 0 100 50 50 cm /Im Do Q")
            page[NameObject("/Contents")] = writer._add_object(content)
        path = folder / f"{kind}.pdf"
        writer.write(path)
        marker = folder / "windows-job-id"
        marker.unlink(missing_ok=True)
        try:
            execute("print", path, Settings(printer=printer))
        except ValueError as error:
            assert "code 7" in str(error), str(error)
        else:
            raise AssertionError(f"{kind} page was accepted")
        assert not marker.exists(), f"{kind} page reached StartDoc"
    print("PASS: image and blank PDFs refused before printer submission")


if __name__ == "__main__":
    check(Path(sys.argv[1]), sys.argv[2])
