"""Tests for apps.medical.pdf_merge."""

from __future__ import annotations

from io import BytesIO

from django.test import SimpleTestCase
from pypdf import PdfReader, PdfWriter

from apps.medical.pdf_merge import merge_pdfs, safe_merge_pdfs


def _minimal_pdf_bytes() -> bytes:
    w = PdfWriter()
    w.add_blank_page(width=200, height=200)
    buf = BytesIO()
    w.write(buf)
    return buf.getvalue()


class PdfMergeTests(SimpleTestCase):
    def test_merge_two_pdfs(self) -> None:
        a = _minimal_pdf_bytes()
        b = _minimal_pdf_bytes()
        out = merge_pdfs(a, [b])
        self.assertGreater(len(out), len(a))

    def test_merge_three_external_pdfs_preserves_page_order(self) -> None:
        """§12: Befund + 3 attachments — page count = sum of pages (1+1+1+1)."""
        base = _minimal_pdf_bytes()
        e1 = _minimal_pdf_bytes()
        e2 = _minimal_pdf_bytes()
        e3 = _minimal_pdf_bytes()
        out = merge_pdfs(base, [e1, e2, e3])
        reader = PdfReader(BytesIO(out))
        self.assertEqual(len(reader.pages), 4)

    def test_merge_mixed_page_sizes(self) -> None:
        """§12: different page dimensions still merge."""

        def page_pdf(w: float, h: float) -> bytes:
            wtr = PdfWriter()
            wtr.add_blank_page(width=w, height=h)
            buf = BytesIO()
            wtr.write(buf)
            return buf.getvalue()

        a = page_pdf(200, 200)
        b = page_pdf(612, 792)
        c = page_pdf(100, 500)
        out = merge_pdfs(a, [b, c])
        reader = PdfReader(BytesIO(out))
        self.assertEqual(len(reader.pages), 3)

    def test_safe_merge_fallback(self) -> None:
        bad = b"%PDF-1.4\nnot a real pdf"
        ok = _minimal_pdf_bytes()
        merged, ok_flag = safe_merge_pdfs(ok, [bad])
        self.assertFalse(ok_flag)
        self.assertEqual(merged, ok)
