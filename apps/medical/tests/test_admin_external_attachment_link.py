"""Regression: ``MedicalDocumentVersionAdmin.external_selected_attachment_link``."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

from django.contrib.admin.sites import AdminSite
from django.test import SimpleTestCase

from apps.medical.admin import MedicalDocumentVersionAdmin
from apps.medical.models import MedicalDocumentVersion


class _StubExternalAttachment:
    """Minimal stand-in for ``ExternalPdfAttachment`` in admin display tests."""

    __slots__ = ("id", "hidrive_remote_path")

    def __init__(self, attachment_id: uuid.UUID, hidrive_remote_path: str) -> None:
        self.id = attachment_id
        self.hidrive_remote_path = hidrive_remote_path


class ExternalSelectedAttachmentLinkTests(SimpleTestCase):
    def setUp(self) -> None:
        self.site = AdminSite()
        self.admin = MedicalDocumentVersionAdmin(MedicalDocumentVersion, self.site)

    def test_returns_em_dash_when_no_attachment(self) -> None:
        obj = SimpleNamespace(external_selected_attachment=None)
        self.assertEqual(self.admin.external_selected_attachment_link(obj), "—")

    def test_truncates_long_hidrive_path(self) -> None:
        long_path = "/" + ("x" * 200) + ".pdf"
        att_id = uuid.uuid4()
        a = _StubExternalAttachment(att_id, long_path)
        obj = SimpleNamespace(external_selected_attachment=a)
        out = self.admin.external_selected_attachment_link(obj)
        self.assertIn("…", out)
        self.assertIn(str(att_id), out)
        self.assertLess(len(out), len(long_path) + 80)

    def test_empty_path_shows_em_dash_segment(self) -> None:
        obj = SimpleNamespace(
            external_selected_attachment=_StubExternalAttachment(
                uuid.uuid4(),
                "   ",
            )
        )
        self.assertIn("—", self.admin.external_selected_attachment_link(obj))
