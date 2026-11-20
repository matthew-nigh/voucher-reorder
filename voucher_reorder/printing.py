"""Reject scale/paper mismatches before any printer submission."""
from pypdf import PdfReader


def validate_pages(pdf, settings):
    for page in PdfReader(pdf).pages:
        if (abs(float(page.mediabox.width)-settings.paper_width*72) > .75 or
                abs(float(page.mediabox.height)-settings.paper_height*72) > .75):
            raise ValueError('PDF page size differs from selected printer paper. Nothing was printed. Select matching paper; never use fit-to-page.')
