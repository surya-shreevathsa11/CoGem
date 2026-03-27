from __future__ import annotations

from pathlib import Path

import pytest
from pypdf import PdfReader

from clogem.pdf_tools import generate_pdf_from_text


def test_generate_pdf_from_text_creates_file(tmp_path: Path):
    out = tmp_path / "hello.pdf"
    generate_pdf_from_text("Hello PDF\nSecond line", str(out))
    assert out.exists()
    data = out.read_bytes()
    assert data[:4] == b"%PDF"
    reader = PdfReader(str(out))
    extracted = ""
    for page in reader.pages:
        extracted += (page.extract_text() or "")
    assert "Hello" in extracted


def test_generate_pdf_rejects_empty_text(tmp_path: Path):
    out = tmp_path / "empty.pdf"
    with pytest.raises(ValueError):
        generate_pdf_from_text("   \n  ", str(out))

