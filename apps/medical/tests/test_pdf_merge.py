"""Tests for apps.medical.pdf_merge."""

from __future__ import annotations

from io import BytesIO

from django.test import SimpleTestCase
from pypdf import PdfWriter

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

    def test_safe_merge_fallback(self) -> None:
        bad = b"%PDF-1.4\nnot a real pdf"
        ok = _minimal_pdf_bytes()
        merged, ok_flag = safe_merge_pdfs(ok, [bad])
        self.assertFalse(ok_flag)
        self.assertEqual(merged, ok)
