"""Verify the real Imagesetter burst by its rendered PDF pages.

Windows GDI/PostScript may emit glyph outlines, so PDF text extraction is not a
reliable way to identify the printed document. Rendered pixels test what was
actually saved, including content that has no extractable text.
"""

import hashlib
import sys
from pathlib import Path

import pymupdf
from pypdf import PdfReader


def verify(folder: Path) -> None:
    paths = sorted(folder.glob("*.pdf"))
    assert len(paths) == 3, f"Expected three distinct PDF files, found {len(paths)}"
    rendered = []
    for path in paths:
        reader = PdfReader(path, strict=True)
        with pymupdf.open(path) as document:
            assert len(reader.pages) == len(document), f"Page count disagrees: {path.name}"
            fingerprints = []
            for page in document:
                pixels = page.get_pixmap(matrix=pymupdf.Matrix(0.5, 0.5), alpha=False).samples
                assert pixels.count(255) != len(pixels), f"Blank page in {path.name}"
                fingerprints.append(hashlib.sha256(pixels).digest())
            rendered.append((len(document), fingerprints))

    assert sorted(count for count, _ in rendered) == [1, 10, 10], "Wrong burst page counts"
    assert len({pages[0] for _, pages in rendered}) == 3, "Burst first pages are not distinct"
    long_jobs = [pages for count, pages in rendered if count == 10]
    assert len({pages[-1] for pages in long_jobs}) == 2, "Burst final pages are not distinct"
    assert all(len(set(pages)) == 10 for pages in long_jobs), "Burst contains a repeated page"


if __name__ == "__main__":
    verify(Path(sys.argv[1]))
