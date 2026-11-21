"""Reject scale/paper mismatches before any printer submission."""

from pypdf import PdfReader


def validate_pages(pdf, settings):
    from .bounded import MAX_PAGES

    pages = PdfReader(pdf, strict=True).pages
    if not 0 < len(pages) <= MAX_PAGES:
        raise ValueError("Invalid page count.")
    for page in pages:
        if (
            abs(float(page.mediabox.width) - settings.paper_width * 72) > 0.75
            or abs(float(page.mediabox.height) - settings.paper_height * 72) > 0.75
        ):
            raise ValueError(
                "PDF page size differs from selected printer paper. Nothing was printed. Select matching paper; never use fit-to-page."
            )
    return len(pages)


def save_pdf(source, settings, root):
    """Publish a complete PDF outside the Inbox; never replace an existing user file."""
    import os
    import shutil
    import tempfile
    import uuid

    folder = settings.pdf_folder(root)
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination = folder / f"VoucherReorder-{uuid.uuid4().hex}.pdf"
    fd, temporary = tempfile.mkstemp(prefix=".voucher-", suffix=".tmp", dir=folder)
    try:
        with os.fdopen(fd, "wb") as output, source.open("rb") as input_file:
            shutil.copyfileobj(input_file, output, length=65536)
            output.flush()
            os.fsync(output.fileno())
        # UUID filenames avoid collisions; the private temp is on the same volume.
        os.replace(temporary, destination)
    finally:
        from pathlib import Path

        Path(temporary).unlink(missing_ok=True)
    return destination


def validate_vector_pdf(path):
    """Conservative file-output preflight, inside the bounded preparation child.

    Keep PDF text/paths as-is. Refuse image resources (also nested/unused), inline
    images and pages with no vector paint, without invoking a raster renderer.
    Physical printing retains its stricter PDFium/EMF preflight.
    """
    from pypdf.generic import ContentStream

    reader = PdfReader(path, strict=True)
    paint = {b"Tj", b"TJ", b"'", b'"', b"S", b"s", b"f", b"F", b"f*", b"B", b"B*", b"b", b"b*", b"sh"}

    def resolve(obj):
        return obj.get_object() if hasattr(obj, "get_object") else obj

    def inspect(stream, resources, ancestors):
        if len(ancestors) > 40 or id(stream) in ancestors:
            raise ValueError("Recursive PDF resources are unsupported.")
        ancestors = ancestors | {id(stream)}
        resources = resolve(resources)
        painted = False
        invoked = set()
        if stream is not None:
            content = ContentStream(stream, reader)
            for operands, operator in content.operations:
                if operator == b"INLINE IMAGE":
                    raise ValueError("Use a vector PDF; image content is unsupported.")
                painted |= operator in paint
                if operator == b"Do":
                    invoked.add(operands[0])
        for name, obj in resolve(resources.get("/XObject", {})).items():
            obj = resolve(obj)
            if obj.get("/Subtype") == "/Image":
                raise ValueError("Use a vector PDF; image content is unsupported.")
            if obj.get("/Subtype") == "/Form":
                child_paint = inspect(obj, obj.get("/Resources", resources), ancestors)
                # Only invoked Forms count toward the page's vector content.
                if name in invoked:
                    painted |= child_paint
        for pattern in resolve(resources.get("/Pattern", {})).values():
            pattern = pattern.get_object()
            if pattern.get("/PatternType") == 1:
                inspect(pattern, pattern.get("/Resources", {}), ancestors)
        for state in resolve(resources.get("/ExtGState", {})).values():
            mask = resolve(resolve(state).get("/SMask"))
            if isinstance(mask, dict) and "/G" in mask:
                group = resolve(mask["/G"])
                inspect(group, group.get("/Resources", resources), ancestors)
        for font in resolve(resources.get("/Font", {})).values():
            font = font.get_object()
            for glyph in resolve(font.get("/CharProcs", {})).values():
                inspect(glyph.get_object(), font.get("/Resources", {}), ancestors)
        return painted

    for page in reader.pages:
        if not inspect(page.get_contents(), page.get("/Resources", {}), set()):
            raise ValueError("Use a vector PDF; blank pages are unsupported.")
