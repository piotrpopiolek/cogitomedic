"""Tests for intake PDF generation (WeasyPrint)."""

from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO
from unittest.mock import MagicMock

from django.test import SimpleTestCase
from pypdf import PdfReader

from apps.intake.pdf_builder import build_intake_pdf_bytes


class IntakePdfMetadataTests(SimpleTestCase):
    def test_document_properties_contain_snapshot_fields(self) -> None:
        fid = "33eeb2d8-986c-4a64-860b-b625340267b9"
        qid = "c0d6328a-8b5d-4a4e-a20e-3a3470c35bcd"
        when = datetime(2026, 4, 13, 13, 56, 53, tzinfo=UTC)
        version = MagicMock()
        version.snapshot_payload = {
            "intake_form_id": fid,
            "queue_entry_id": qid,
            "captured_at": when.isoformat(),
            "submitted_at": when.isoformat(),
            "base_locale": "de-DE",
            "form_locale": "de-DE",
            "patient": {
                "first_name": "Jan",
                "last_name": "Test",
                "date_of_birth": "1985-03-12",
                "phone": "+48123456789",
                "email": "j@test.invalid",
            },
            "consents": [
                {
                    "code": "GOAE_INFO",
                    "accepted": True,
                    "accepted_at": "2026-04-13T11:56:31.841270+00:00",
                }
            ],
            "anamnesis": {"answers": []},
            "signature": {
                "sha256": (
                    "5073fc6cefc478b6a1db49ac394b677345bac3585ada5f767255dccb433218f3"
                ),
            },
        }

        pdf_bytes = build_intake_pdf_bytes(version)
        meta = PdfReader(BytesIO(pdf_bytes)).metadata
        assert meta is not None
        self.assertEqual(meta.get("/Title"), "Einwilligungen")
        subject = meta.get("/Subject")
        assert isinstance(subject, str)
        self.assertIn(fid, subject)
        self.assertIn(qid, subject)
        self.assertIn("de-DE", subject)
        self.assertIn("GOAE_INFO=", subject)
        self.assertIn("2026-04-13T11:56:31", subject)
        self.assertIn(
            "5073fc6cefc478b6a1db49ac394b677345bac3585ada5f767255dccb433218f3", subject
        )
        self.assertEqual(
            meta.get("/cogitoconsentacceptance"),
            "GOAE_INFO=2026-04-13T11:56:31.841270+00:00",
        )
        self.assertEqual(
            meta.get("/cogitosignaturesha256"),
            "5073fc6cefc478b6a1db49ac394b677345bac3585ada5f767255dccb433218f3",
        )
        self.assertEqual(meta.get("/cogitointakeformid"), fid)
        self.assertEqual(meta.get("/cogitoqueueentryid"), qid)
        self.assertIn("/CreationDate", meta)
        self.assertIn("/ModDate", meta)
