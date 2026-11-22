"""Application-owned PDF rejection reasons safe to expose across process boundaries."""

MESSAGES = {
    "encrypted": "Encrypted print jobs are not supported.",
    "pages": "PDF page count limit exceeded (maximum 250 pages).",
    "empty": "The print job has no pages.",
    "layers": "Flatten optional-content layers before sending a PDF print job.",
    "units": "Nonstandard PDF UserUnit is unsupported; print at normal scale.",
    "annotations": "Flatten annotations before sending a PDF print job.",
    "dimensions": "Page dimensions must be positive.",
    "expanded": "Expanded PDF data limit exceeded (256 MiB).",
    "output": "PDF output size limit exceeded (256 MiB).",
    "input": "PDF input size limit exceeded (256 MiB).",
    "deadline": "PDF processing time limit exceeded (120 seconds).",
    "memory": "PDF worker memory limit exceeded (768 MiB).",
    "image": "Scanned or image-only PDFs aren't supported; print from QuickBooks or another text-based document. PDFs containing image content are also unsupported.",
    "blank": "PDF contains a blank page with no vector content.",
    "recursive": "PDF contains recursive Form invocations.",
    "depth": "PDF resource nesting limit exceeded (40 levels).",
    "resources": "PDF resource count limit exceeded (100,000 objects).",
    "invalid_form": "PDF contains an invalid Form reference.",
}


class PdfError(ValueError):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(MESSAGES[reason])


def diagnostic_reason(detail):
    """Accept only fixed codes, never PDF/parser exception text."""
    for line in detail.splitlines():
        if line.startswith("VRPDF ") and line[6:] in MESSAGES:
            return MESSAGES[line[6:]]
    return None
