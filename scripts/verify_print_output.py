"""Validate the file-port result: every page has marks and no rasterized content."""

import sys

from pypdf import PdfReader


def check_resources(resources):
    resources = resources.get_object() if hasattr(resources, "get_object") else resources
    objects = resources.get("/XObject", {})
    objects = objects.get_object() if hasattr(objects, "get_object") else objects
    for ref in objects.values():
        obj = ref.get_object()
        assert obj["/Subtype"] != "/Image", "Vector fixture became an image"
        if obj["/Subtype"] == "/Form":
            check_resources(obj.get("/Resources", {}))


def verify(path, count):
    reader = PdfReader(path, strict=True)
    assert len(reader.pages) == count
    for page in reader.pages:
        assert page.get_contents().get_data(), "Empty printed page"
        assert abs(float(page.mediabox.width) - 612) < 1
        assert abs(float(page.mediabox.height) - 792) < 1
        check_resources(page["/Resources"])


if __name__ == "__main__":
    verify(sys.argv[1], int(sys.argv[2]))
