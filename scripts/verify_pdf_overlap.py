"""Inspect diagnostic PDF outputs by page count and rendered first-page pixels."""

import hashlib
import json
import sys
from pathlib import Path

import pymupdf
from pypdf import PdfReader


def inspect(path: Path) -> dict[str, object]:
    result: dict[str, object] = {"name": path.name, "valid": False}
    try:
        pages = len(PdfReader(path, strict=True).pages)
        with pymupdf.open(path) as document:
            if pages != len(document) or pages == 0:
                return result
            digest = hashlib.sha256()
            for page in document:
                pixels = page.get_pixmap(matrix=pymupdf.Matrix(0.5, 0.5), alpha=False).samples
                if pixels.count(255) == len(pixels):
                    return result
                digest.update(pixels)
            result.update(valid=True, pages=pages, fingerprint=digest.hexdigest())
    except Exception as exc:
        result["error"] = str(exc)
    return result


if __name__ == "__main__":
    print(json.dumps([inspect(path) for path in sorted(Path(sys.argv[1]).glob("*.pdf"))]))
