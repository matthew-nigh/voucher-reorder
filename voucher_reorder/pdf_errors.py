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
    "decompression": "PDF stream decompression limit exceeded (75,000,000 bytes per stream).",
    "stream_length": "PDF stream length limit exceeded.",
    "decode_work": "PDF accumulated stream decoding work limit exceeded.",
    "filters": "PDF stream filter count limit exceeded.",
    "xref": "PDF cross-reference entry count limit exceeded.",
    "object_stream": "PDF object-stream entry count limit exceeded.",
    "tokens": "PDF parser token count limit exceeded.",
    "token_length": "PDF parser token length limit exceeded.",
    "dictionary": "PDF dictionary entry count limit exceeded.",
    "array": "PDF array element count limit exceeded.",
    "parser_depth": "PDF parser nesting limit exceeded.",
    "parser_cycle": "PDF contains a cyclic object reference.",
    "recovery": "PDF parser recovery limit exceeded.",
    "row": "PDF stream predictor row length limit exceeded.",
    "columns": "PDF stream predictor column count limit exceeded.",
    "colors": "PDF stream predictor color count limit exceeded.",
    "parser_limit": "PDF parser safety limit exceeded.",
    "print_memory": "Windows print worker memory limit exceeded (384 MiB).",
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


# Match only known pypdf 7.1.1 diagnostic prefixes; never forward its free-form
# exception text (which can include object values, paths or document content).
def parser_limit_reason(error):
    text = str(error)
    for prefixes, reason in (
        (("Limit reached while decompressing.",), "decompression"),
        (("Recovery limit reached", "Maximum Root object recovery"), "recovery"),
        (("Declared stream length", "Requested length", "Read stream length"), "stream_length"),
        (("Stream decoding exceeded",), "decode_work"),
        (("Maximum filter count",), "filters"),
        (("Declared size", "Total XRef entries", "Maximum XRef stream entry"), "xref"),
        (("Value /N",), "object_stream"),
        (("Reached maximum number of tokens",), "tokens"),
        (("Token exceeds maximum length",), "token_length"),
        (("Reached maximum number of dictionary entries",), "dictionary"),
        (("Reached maximum array element count",), "array"),
        (("Detected loop", "Detected cycle", "Detected cyclic"), "parser_cycle"),
        (("Row length of",), "row"),
        (("Number of columns",), "columns"),
        (("Color value",), "colors"),
    ):
        if text.startswith(prefixes):
            return reason
    if text.startswith("Array-based stream has"):
        return "stream_length" if "output bytes" in text else "array"
    return "parser_limit"
