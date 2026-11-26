"""The Windows burst gate must detect lost and incomplete rendered jobs."""

import pymupdf
import pytest

from scripts.verify_clone_output import verify


def make_pdf(path, label, pages, *, blank_last=False):
    with pymupdf.open() as document:
        for number in range(1, pages + 1):
            page = document.new_page()
            if not blank_last or number != pages:
                page.insert_text((72, 72), f"VOID FAKE {label} PAGE {number}")
        document.save(path)


def test_burst_gate_accepts_distinct_complete_jobs(tmp_path):
    make_pdf(tmp_path / "first.pdf", "first", 1)
    make_pdf(tmp_path / "burst-a.pdf", "burst A", 10)
    make_pdf(tmp_path / "burst-b.pdf", "burst B", 10)
    verify(tmp_path)


@pytest.mark.parametrize("defect", ["duplicate", "blank_last"])
def test_burst_gate_rejects_lost_content(tmp_path, defect):
    make_pdf(tmp_path / "first.pdf", "first", 1)
    make_pdf(tmp_path / "burst-a.pdf", "burst A", 10)
    make_pdf(
        tmp_path / "burst-b.pdf",
        "burst A" if defect == "duplicate" else "burst B",
        10,
        blank_last=defect == "blank_last",
    )
    with pytest.raises(AssertionError):
        verify(tmp_path)
