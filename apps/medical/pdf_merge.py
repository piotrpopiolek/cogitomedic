"""Merge Befund PDF with external PDFs (pypdf) with Befund-only fallback."""

from __future__ import annotations

import logging
from io import BytesIO

from pypdf import PdfWriter

logger = logging.getLogger(__name__)


def merge_pdfs(befund_pdf_bytes: bytes, external_pdf_bytes_list: list[bytes]) -> bytes:
    """Merge Befund + external PDFs. Raises if merge is impossible.

    Uses ``PdfWriter.append`` instead of ``add_page`` in a loop so each source
    PDF keeps its full page tree and embedded resources intact — ``add_page``
    copies pages individually which can drop fonts/images from WeasyPrint PDFs
    or complex lab scanner output, causing a silent merge failure.
    """
    writer = PdfWriter()
    writer.append(BytesIO(befund_pdf_bytes))
    for ext_bytes in external_pdf_bytes_list:
        writer.append(BytesIO(ext_bytes))
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
