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
from apps.intake.services import CONTACT_METHOD_CONSENT_CODE, NEW_SKIN_CHANGES_LOCATION


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
    """Layout rules from templates/pdf/intake_document.html (DE-only vs bilingual).

    Bilingual consent order: title DE + checkbox, body DE, title locale + checkbox,
    body locale.
    """

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

    def test_polish_locale_consent_title_de_body_de_title_locale_body_locale_order(
        self,
    ) -> None:
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
        self.assertLess(t_de, c_de)
        self.assertLess(c_de, t_pl)
        self.assertLess(t_pl, c_pl)

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
        self.assertNotIn("padding-left:22px", html)
        q_de = html.find("Q_DE_SUNBURN")
        q_pl = html.find("Q_PL_SUNBURN")
        self.assertLess(q_de, q_pl)
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

    def test_german_locale_prevention_contact_method_shows_checkboxes(self) -> None:
        snap = self._base_snapshot(form_locale="de-DE")
        snap["consents"] = [
            {
                "code": CONTACT_METHOD_CONSENT_CODE,
                "version": 1,
                "is_required": False,
                "accepted": True,
                "accepted_at": self._when.isoformat(),
                "title_de": "Kontaktweg",
                "title_locale": "Kontaktweg",
                "content_de": "Bitte wählen:",
                "content_locale": "Bitte wählen:",
                "selected_option_codes": ["EMAIL", "PHONE"],
                "contact_method_all_options": [
                    {
                        "option_code": "EMAIL",
                        "label_de": "E-Mail",
                        "label_locale": "E-Mail",
                        "selected": True,
                    },
                    {
                        "option_code": "SMS",
                        "label_de": "SMS",
                        "label_locale": "SMS",
                        "selected": False,
                    },
                    {
                        "option_code": "PHONE",
                        "label_de": "Telefon",
                        "label_locale": "Telefon",
                        "selected": True,
                    },
                ],
            }
        ]
        html = _render_intake_pdf_html(snap)
        self.assertRegex(
            html,
            r'<span class="cb">☑</span>\s*<span>E-Mail</span>',
        )
        self.assertRegex(
            html,
            r'<span class="cb">☐</span>\s*<span>SMS</span>',
        )
        self.assertRegex(
            html,
            r'<span class="cb">☑</span>\s*<span>Telefon</span>',
        )

    def test_polish_locale_contact_method_stacks_de_and_locale_rows(self) -> None:
        snap = self._base_snapshot(form_locale="pl-PL")
        snap["consents"] = [
            {
                "code": CONTACT_METHOD_CONSENT_CODE,
                "version": 1,
                "is_required": False,
                "accepted": True,
                "accepted_at": self._when.isoformat(),
                "title_de": "Kontakt",
                "title_locale": "Kontakt PL",
                "content_de": "Wybór:",
                "content_locale": "Wybór PL:",
                "selected_option_codes": ["SMS"],
                "contact_method_all_options": [
                    {
                        "option_code": "EMAIL",
                        "label_de": "E-Mail",
                        "label_locale": "E-mail",
                        "selected": False,
                    },
                    {
                        "option_code": "SMS",
                        "label_de": "SMS",
                        "label_locale": "SMS",
                        "selected": True,
                    },
                    {
                        "option_code": "PHONE",
                        "label_de": "Telefon",
                        "label_locale": "Telefon",
                        "selected": False,
                    },
                ],
            }
        ]
        html = _render_intake_pdf_html(snap)
        self.assertNotIn("padding-left:22px", html)
        self.assertRegex(
            html,
            r'<span class="cb">☐</span>\s*<span>E-Mail</span>',
        )
        self.assertRegex(
            html,
            r'<span class="cb">☐</span>\s*<span>E-mail</span>',
        )
        self.assertRegex(
            html,
            r'<span class="cb">☑</span>\s*<span>SMS</span>',
        )

    def test_body_map_section_renders_when_present_in_snapshot(self) -> None:
        snap = self._base_snapshot(form_locale="de-DE")
        snap["body_map"] = {
            "image_rel_path": "static/tablet/body.jpg",
            "points": [
                {
                    "left_pct": "22.0000",
                    "top_pct": "35.0000",
                    "side": "front",
                    "index": 1,
                },
            ],
        }
        html = _render_intake_pdf_html(snap)
        self.assertIn("Körperschema", html)
        self.assertIn("static/tablet/body.jpg", html)
        self.assertIn("body-map-marker", html)
        self.assertIn("left:22.0000%", html)
        self.assertIn("top:35.0000%", html)

    def test_body_map_section_placed_under_new_skin_question_not_at_end(self) -> None:
        snap = self._base_snapshot(form_locale="de-DE")
        snap["body_map"] = {
            "image_rel_path": "static/tablet/body.jpg",
            "points": [
                {
                    "left_pct": "22.0000",
                    "top_pct": "35.0000",
                    "side": "front",
                    "index": 1,
                },
            ],
        }
        snap["anamnesis"] = {
            "answers": [
                {
                    "question_code": NEW_SKIN_CHANGES_LOCATION,
                    "question_text_de": "COGITO_SKIN_Q_MARKER",
                    "question_text_locale": "COGITO_SKIN_Q_MARKER",
                    "all_options": [
                        {
                            "option_code": "YES",
                            "label_de": "Ja",
                            "label_locale": "Tak",
                            "selected": True,
                        },
                    ],
                },
                {
                    "question_code": "Q_OTHER_MELANOMA",
                    "question_text_de": "COGITO_OTHER_Q_MARKER",
                    "question_text_locale": "COGITO_OTHER_Q_MARKER",
                    "all_options": [],
                },
            ]
        }
        html = _render_intake_pdf_html(snap)
        skin_q = html.find("COGITO_SKIN_Q_MARKER")
        korper = html.find("Körperschema")
        other_q = html.find("COGITO_OTHER_Q_MARKER")
        self.assertGreater(skin_q, -1)
        self.assertGreater(korper, -1)
        self.assertGreater(other_q, -1)
        self.assertLess(skin_q, korper)
        self.assertLess(korper, other_q)
        self.assertEqual(html.count("body-map-wrap"), 1)

    def test_body_map_section_absent_when_not_in_snapshot(self) -> None:
        snap = self._base_snapshot(form_locale="de-DE")
        html = _render_intake_pdf_html(snap)
        self.assertNotIn("body-map-marker", html)
        self.assertNotIn("static/tablet/body.jpg", html)
