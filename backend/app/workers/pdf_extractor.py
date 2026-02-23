"""PDF and OCR extraction worker — Blueprint §6.7 / §16.3.

Best-effort extraction pipeline:
1) `pypdf` text
2) `pdfplumber` text/tables
3) OCR fallback if dependencies are available
"""
from __future__ import annotations

import io
import logging

logger = logging.getLogger(__name__)


def _extract_with_pypdf(pdf_bytes: bytes) -> list[str]:
    chunks: list[str] = []
    try:
        from pypdf import PdfReader
    except Exception as exc:
        logger.debug("pypdf unavailable: %s", exc)
        return chunks

    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        for page in reader.pages[:100]:
            with_text = page.extract_text() or ""
            with_text = with_text.strip()
            if with_text:
                chunks.append(with_text)
    except Exception as exc:
        logger.warning("pypdf extraction failed: %s", exc)
    return chunks


def _extract_with_pdfplumber(pdf_bytes: bytes) -> tuple[list[str], object | None]:
    chunks: list[str] = []
    pdf_obj = None
    try:
        import pdfplumber
    except Exception as exc:
        logger.debug("pdfplumber unavailable: %s", exc)
        return chunks, None

    try:
        pdf_obj = pdfplumber.open(io.BytesIO(pdf_bytes))
        for page in pdf_obj.pages[:100]:
            page_text = page.extract_text() or ""
            page_text = page_text.strip()
            if page_text:
                chunks.append(page_text)

            tables = page.extract_tables() or []
            for table in tables:
                if not table:
                    continue
                table_lines = []
                for row in table:
                    if not row:
                        continue
                    cells = [str(cell).strip() for cell in row if cell not in (None, "")]
                    if cells:
                        table_lines.append(" | ".join(cells))
                if table_lines:
                    chunks.append("\n[TABLE]\n" + "\n".join(table_lines) + "\n[/TABLE]\n")
    except Exception as exc:
        logger.warning("pdfplumber extraction failed: %s", exc)
        if pdf_obj is not None:
            try:
                pdf_obj.close()
            except Exception:
                pass
        return chunks, None
    return chunks, pdf_obj


def _ocr_fallback_from_pdfplumber(pdf_obj: object | None, *, max_pages: int = 10) -> list[str]:
    chunks: list[str] = []
    if pdf_obj is None:
        return chunks

    try:
        import pytesseract
    except Exception as exc:
        logger.debug("pytesseract unavailable: %s", exc)
        try:
            pdf_obj.close()
        except Exception:
            pass
        return chunks

    try:
        pages = getattr(pdf_obj, "pages", [])[:max_pages]
        for page in pages:
            try:
                page_image = page.to_image(resolution=200).original
                ocr_text = pytesseract.image_to_string(page_image, lang="por")
                ocr_text = (ocr_text or "").strip()
                if ocr_text:
                    chunks.append(ocr_text)
            except Exception as exc:
                logger.warning("OCR fallback failed for one PDF page: %s", exc)
    finally:
        try:
            pdf_obj.close()
        except Exception:
            pass
    return chunks


def extract_pdf_content(pdf_bytes: bytes) -> str:
    """Extract text from PDF with image-only OCR fallback."""
    text_chunks: list[str] = []
    text_chunks.extend(_extract_with_pypdf(pdf_bytes))

    plumber_chunks, pdf_obj = _extract_with_pdfplumber(pdf_bytes)
    if plumber_chunks:
        text_chunks.extend(plumber_chunks)

    full_text = "\n".join(c for c in text_chunks if c and c.strip()).strip()
    if full_text:
        if pdf_obj is not None:
            try:
                pdf_obj.close()
            except Exception:
                pass
        # Avoid duplicate chunks when both extractors succeed heavily.
        # Keep bounded size for downstream queue payloads.
        return full_text[:200000]

    logger.info("No text extracted from PDF, attempting OCR fallback.")
    ocr_chunks = _ocr_fallback_from_pdfplumber(pdf_obj, max_pages=10)
    if ocr_chunks:
        return "\n".join(ocr_chunks).strip()[:200000]
    return ""
