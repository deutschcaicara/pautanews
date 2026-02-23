from __future__ import annotations

from app.workers import pdf_extractor


class _FakePdf:
    def __init__(self) -> None:
        self.closed = False
        self.pages = []

    def close(self) -> None:
        self.closed = True


def test_extract_pdf_content_uses_text_extractors_and_closes_pdfplumber(monkeypatch) -> None:
    fake_pdf = _FakePdf()
    monkeypatch.setattr(pdf_extractor, "_extract_with_pypdf", lambda _b: ["texto pypdf"])
    monkeypatch.setattr(pdf_extractor, "_extract_with_pdfplumber", lambda _b: (["texto plumber"], fake_pdf))
    monkeypatch.setattr(pdf_extractor, "_ocr_fallback_from_pdfplumber", lambda _pdf, max_pages=10: ["ocr"])

    out = pdf_extractor.extract_pdf_content(b"%PDF-1.4")
    assert "texto pypdf" in out
    assert "texto plumber" in out
    assert fake_pdf.closed is True


def test_extract_pdf_content_falls_back_to_ocr(monkeypatch) -> None:
    fake_pdf = _FakePdf()
    monkeypatch.setattr(pdf_extractor, "_extract_with_pypdf", lambda _b: [])
    monkeypatch.setattr(pdf_extractor, "_extract_with_pdfplumber", lambda _b: ([], fake_pdf))
    monkeypatch.setattr(pdf_extractor, "_ocr_fallback_from_pdfplumber", lambda _pdf, max_pages=10: ["texto ocr"])

    out = pdf_extractor.extract_pdf_content(b"%PDF-1.4")
    assert out == "texto ocr"

