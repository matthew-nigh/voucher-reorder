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
