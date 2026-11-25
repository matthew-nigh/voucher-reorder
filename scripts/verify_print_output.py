"""Validate the file-port result: every page has marks and no rasterized content."""

import sys
import time

import pymupdf
from pypdf import PdfReader
from pypdf.errors import PdfReadError


def check_resources(resources):
    resources = resources.get_object() if hasattr(resources, "get_object") else resources
    objects = resources.get("/XObject", {})
    objects = objects.get_object() if hasattr(objects, "get_object") else objects
    for ref in objects.values():
        obj = ref.get_object()
        assert obj["/Subtype"] != "/Image", "Vector fixture became an image"
        if obj["/Subtype"] == "/Form":
            check_resources(obj.get("/Resources", {}))


def verify(path, count, first=None):
    reader = PdfReader(path, strict=True)
    assert len(reader.pages) == count
    for page in reader.pages:
        assert page.get_contents().get_data(), "Empty printed page"
        assert abs(float(page.mediabox.width) - 612) < 1
        assert abs(float(page.mediabox.height) - 792) < 1
        check_resources(page["/Resources"])

    with pymupdf.open(path) as printed:
        for index, page in enumerate(printed):
            drawings = page.get_drawings()
            assert len(drawings) > 30, "Blank or incomplete voucher content"
            if first is not None:
                actual = 0
                for bit in range(7):
                    point = pymupdf.Point(483 + bit * 9, 28)
                    if any(
                        d["fill"] == (0, 0, 0)
                        and any(item[0] == "re" and point in item[1] for item in d["items"])
                        for d in drawings
                    ):
                        actual |= 1 << bit
                assert actual == first + index, f"Page order/content mismatch: {actual} != {first + index}"


if __name__ == "__main__":
    deadline = time.monotonic() + (60 if "--wait" in sys.argv else 0)
    while True:
        try:
            first = int(sys.argv[sys.argv.index("--first") + 1]) if "--first" in sys.argv else None
            verify(sys.argv[1], int(sys.argv[2]), first)
            break
        except (OSError, PdfReadError, AssertionError):
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.5)
