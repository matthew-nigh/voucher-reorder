"""Reject scale/paper mismatches before any printer submission."""

from pypdf import PdfReader


def validate_pages(pdf, settings):
    from .bounded import MAX_PAGES

    pages = PdfReader(pdf, strict=True).pages
    from .pdf_errors import PdfError

    if len(pages) > MAX_PAGES:
        raise PdfError("pages")
    if not pages:
        raise PdfError("empty")
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
    """Check resource safety separately from actual Form execution.

    Resource dictionaries are graphs, not call stacks: inherited/shared resources
    can legally refer back to a Form. Only executed Do operators imply recursion.
    Still inspect unused resources, masks, patterns and Type3 glyphs for images.
    """
    from pypdf.generic import ContentStream

    from .bounded import MAX_OUTPUT, MAX_PAGES
    from .pdf_errors import PdfError

    reader = PdfReader(path, strict=True)
    if reader.is_encrypted:
        raise PdfError("encrypted")
    if len(reader.pages) > MAX_PAGES:
        raise PdfError("pages")
    if not reader.pages:
        raise PdfError("empty")
    paint = {b"Tj", b"TJ", b"'", b'"', b"S", b"s", b"f", b"F", b"f*", b"B", b"B*", b"b", b"b*", b"sh"}
    streams, resources_seen, painted_cache, resource_streams = {}, {}, {}, {}
    expanded = 0

    def resolve(obj):
        return obj.get_object() if hasattr(obj, "get_object") else obj

    def operations(stream):
        nonlocal expanded
        if stream is None:
            return []
        key = id(stream)
        if key not in streams:
            content = ContentStream(stream, reader)
            expanded += len(content.get_data())
            if expanded > MAX_OUTPUT:
                raise PdfError("expanded")
            if len(streams) >= 100000:
                raise PdfError("resources")
            # Retain the source object too: Python may otherwise reuse its id.
            streams[key] = (stream, content.operations)
            if any(operator == b"INLINE IMAGE" for _, operator in content.operations):
                raise PdfError("image")
        return streams[key][1]

    def resource_stream(stream, resources, depth):
        resources = resolve(resources)
        resource_streams[(id(stream), id(resources))] = (stream, resources)
        if len(resource_streams) > 100000:
            raise PdfError("resources")
        operations(stream)
        resources_safe(resources, depth)

    def resources_safe(resources, depth=0):
        resources = resolve(resources)
        key = id(resources)
        if key in resources_seen:
            return
        if depth > 40:
            raise PdfError("depth")
        resources_seen[key] = resources
        if len(resources_seen) > 100000:
            raise PdfError("resources")
        for obj in resolve(resources.get("/XObject", {})).values():
            obj = resolve(obj)
            if obj.get("/Subtype") == "/Image":
                raise PdfError("image")
            if obj.get("/Subtype") == "/Form":
                resource_stream(obj, obj.get("/Resources", resources), depth + 1)
        for pattern in resolve(resources.get("/Pattern", {})).values():
            pattern = resolve(pattern)
            if pattern.get("/PatternType") == 1:
                resource_stream(pattern, pattern.get("/Resources", resources), depth + 1)
        for state in resolve(resources.get("/ExtGState", {})).values():
            mask = resolve(resolve(state).get("/SMask"))
            if isinstance(mask, dict) and "/G" in mask:
                group = resolve(mask["/G"])
                resource_stream(group, group.get("/Resources", resources), depth + 1)
        for font in resolve(resources.get("/Font", {})).values():
            font = resolve(font)
            for glyph in resolve(font.get("/CharProcs", {})).values():
                resource_stream(resolve(glyph), font.get("/Resources", resources), depth + 1)

    def inspect(stream, resources, ancestors):
        resources = resolve(resources)
        key = (id(stream), id(resources))
        if key in ancestors:
            raise PdfError("recursive")
        if len(ancestors) > 40:
            raise PdfError("depth")
        if key in painted_cache:
            painted, height = painted_cache[key]
            if len(ancestors) + height > 40:
                raise PdfError("depth")
            return painted, height
        ancestors = ancestors | {key}
        painted, height = False, 0
        for operands, operator in operations(stream):
            painted |= operator in paint
            if operator == b"Do":
                obj = resolve(resolve(resources.get("/XObject", {})).get(operands[0]))
                if not isinstance(obj, dict) or obj.get("/Subtype") != "/Form":
                    raise PdfError("invalid_form")
                child_paint, child_height = inspect(obj, obj.get("/Resources", resources), ancestors)
                painted |= child_paint
                height = max(height, child_height + 1)
        painted_cache[key] = (painted, height)
        return painted, height

    for page in reader.pages:
        resources = page.get("/Resources", {})
        resources_safe(resources)
        # Patterns, masks and glyph programs can execute Forms too. Validate
        # their invocations even when the page does not paint that resource.
        for stream, context in resource_streams.values():
            inspect(stream, context, set())
        if not inspect(page.get_contents(), resources, set())[0]:
            raise PdfError("blank")
