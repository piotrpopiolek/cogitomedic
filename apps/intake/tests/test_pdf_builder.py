"""Tests for intake PDF generation (WeasyPrint)."""

from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO
from unittest.mock import MagicMock
from uuid import uuid4

from django.template.loader import render_to_string
from django.test import SimpleTestCase
from pypdf import PdfReader

from apps.intake.pdf_builder import _normalize_snapshot, build_intake_pdf_bytes


def _render_intake_pdf_html(snapshot: dict) -> str:
    return render_to_string("pdf/intake_document.html", _normalize_snapshot(snapshot))


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


class IntakePdfBilingualLayoutTests(SimpleTestCase):
    """Layout rules from templates/pdf/intake_document.html (DE-only vs bilingual)."""

    _when = datetime(2026, 4, 13, 13, 56, 53, tzinfo=UTC)

    def _base_snapshot(self, *, form_locale: str) -> dict:
        return {
            "captured_at": self._when.isoformat(),
            "submitted_at": self._when.isoformat(),
            "base_locale": "de-DE",
            "form_locale": form_locale,
            "intake_form_id": str(uuid4()),
            "queue_entry_id": str(uuid4()),
            "patient": {
                "first_name": "Jan",
                "last_name": "Test",
                "date_of_birth": "1985-03-12",
                "phone": "+48123456789",
                "email": "j@test.invalid",
            },
            "consents": [],
            "anamnesis": {"answers": []},
            "signature": {},
        }

    def test_german_locale_uses_short_section_titles_and_single_option_rows(
        self,
    ) -> None:
        snap = self._base_snapshot(form_locale="de-DE")
        snap["consents"] = [
            {
                "code": "DEMO",
                "version": 1,
                "is_required": True,
                "accepted": True,
                "accepted_at": self._when.isoformat(),
                "title_de": "Titel deutsch",
                "title_locale": "Titel PL nieuzywany",
                "content_de": "COGITO_BODY_DE_ONLY",
                "content_locale": "COGITO_BODY_PL_SKIP",
            }
        ]
        snap["anamnesis"] = {
            "answers": [
                {
                    "question_code": "SUN",
                    "question_text_de": "Frage DE",
                    "question_text_locale": "Frage PL",
                    "all_options": [
                        {
                            "option_code": "n",
                            "label_de": "Nein",
                            "label_locale": "Nie",
                            "selected": True,
                        },
                    ],
                }
            ]
        }
        html = _render_intake_pdf_html(snap)
        self.assertNotIn("Einwilligungen / Consents", html)
        self.assertIn("<h2>Einwilligungen</h2>", html)
        self.assertNotIn("Anamnese / Anamnesis", html)
        self.assertIn("<h2>Anamnese</h2>", html)
        self.assertNotIn("padding-left:22px", html)
        self.assertIn("<h2>Unterschrift</h2>", html)
        self.assertNotIn("<strong>Podpis</strong>", html)
        self.assertIn("Keine Signatur.", html)
        self.assertIn("COGITO_BODY_DE_ONLY", html)
        self.assertNotIn("COGITO_BODY_PL_SKIP", html)
        self.assertIn("Frage DE", html)
        self.assertNotIn("Frage PL", html)

    def test_polish_locale_consent_body_de_then_locale_then_titles(self) -> None:
        snap = self._base_snapshot(form_locale="pl-PL")
        snap["consents"] = [
            {
                "code": "ORDER",
                "version": 1,
                "is_required": True,
                "accepted": True,
                "accepted_at": self._when.isoformat(),
                "title_de": "TITLE_DE_MARKER",
                "title_locale": "TITLE_PL_MARKER",
                "content_de": "CONTENT_DE_MARKER",
                "content_locale": "CONTENT_PL_MARKER",
            }
        ]
        html = _render_intake_pdf_html(snap)
        self.assertIn("Einwilligungen / Consents", html)
        c_de = html.find("CONTENT_DE_MARKER")
        c_pl = html.find("CONTENT_PL_MARKER")
        t_de = html.find("TITLE_DE_MARKER")
        t_pl = html.find("TITLE_PL_MARKER")
        self.assertGreater(c_de, -1, msg="German body missing")
        self.assertGreater(c_pl, -1, msg="Locale body missing")
        self.assertGreater(t_de, -1, msg="German title missing")
        self.assertGreater(t_pl, -1, msg="Locale title missing")
        self.assertLess(c_de, c_pl)
        self.assertLess(c_pl, t_de)
        self.assertLess(t_de, t_pl)

    def test_polish_locale_anamnesis_question_and_options_stacked_per_language(
        self,
    ) -> None:
        snap = self._base_snapshot(form_locale="pl-PL")
        snap["anamnesis"] = {
            "answers": [
                {
                    "question_code": "SUN",
                    "question_text_de": "Q_DE_SUNBURN",
                    "question_text_locale": "Q_PL_SUNBURN",
                    "all_options": [
                        {
                            "option_code": "n",
                            "label_de": "Nein",
                            "label_locale": "Nie",
                            "selected": True,
                        },
                        {
                            "option_code": "y",
                            "label_de": "Ja",
                            "label_locale": "Tak",
                            "selected": False,
                        },
                    ],
                }
            ]
        }
        html = _render_intake_pdf_html(snap)
        self.assertIn("Anamnese / Anamnesis", html)
        q_de = html.find("Q_DE_SUNBURN")
        q_pl = html.find("Q_PL_SUNBURN")
        self.assertLess(q_de, q_pl)
        self.assertGreaterEqual(html.count("padding-left:22px"), 2)
        nein = html.find("Nein")
        nie = html.find("Nie")
        self.assertGreater(nein, -1)
        self.assertGreater(nie, -1)
        self.assertLess(nein, nie)

    def test_polish_locale_free_text_shows_bilingual_labels(self) -> None:
        snap = self._base_snapshot(form_locale="pl-PL")
        snap["anamnesis"] = {
            "answers": [
                {
                    "question_code": "NOTE",
                    "question_text_de": "Notiz",
                    "question_text_locale": "Notatka",
                    "all_options": [],
                    "free_text": "Antwort frei",
                }
            ]
        }
        html = _render_intake_pdf_html(snap)
        self.assertIn("<strong>Eintrag</strong>", html)
        self.assertIn("<strong>Wpis / Entry</strong> (pl-PL)", html)
        self.assertIn("Antwort frei", html)

    def test_english_locale_signature_block_uses_signature_label(self) -> None:
        snap = self._base_snapshot(form_locale="en-GB")
        html = _render_intake_pdf_html(snap)
        self.assertIn("<h2>Unterschrift / Signature</h2>", html)
        self.assertIn("<strong>Signature</strong>", html)

    def test_non_pl_en_locale_signature_uses_locale_code_fallback(self) -> None:
        snap = self._base_snapshot(form_locale="fr-FR")
        html = _render_intake_pdf_html(snap)
        self.assertIn("<h2>Unterschrift / Unterschrift</h2>", html)
        self.assertIn("<strong>fr-FR</strong>", html)
