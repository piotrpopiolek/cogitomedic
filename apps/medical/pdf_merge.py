"""Merge Befund PDF with external PDFs (pypdf) with Befund-only fallback."""

from __future__ import annotations

import logging
from io import BytesIO

from pypdf import PdfReader, PdfWriter

logger = logging.getLogger(__name__)


def merge_pdfs(befund_pdf_bytes: bytes, external_pdf_bytes_list: list[bytes]) -> bytes:
    """Merge Befund + external PDFs. Raises if merge is impossible."""
    writer = PdfWriter()
    reader = PdfReader(BytesIO(befund_pdf_bytes))
    for page in reader.pages:
        writer.add_page(page)
    for ext_bytes in external_pdf_bytes_list:
        ext_reader = PdfReader(BytesIO(ext_bytes))
        for page in ext_reader.pages:
            writer.add_page(page)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def safe_merge_pdfs(
    befund_pdf_bytes: bytes, external_pdf_bytes_list: list[bytes]
) -> tuple[bytes, bool]:
    """Merge with fallback: returns ``(pdf_bytes, merge_succeeded)``."""
    try:
        merged = merge_pdfs(befund_pdf_bytes, external_pdf_bytes_list)
        return merged, True
    except Exception:
        logger.exception("PDF merge failed, falling back to Befund-only PDF")
        return befund_pdf_bytes, False
