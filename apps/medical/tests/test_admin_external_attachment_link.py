"""Regression: ``MedicalDocumentVersionAdmin.external_selected_attachment_link``."""

from __future__ import annotations

import uuid
from typing import Any

from django.contrib.admin.sites import AdminSite
from django.test import SimpleTestCase

from apps.medical.admin import MedicalDocumentVersionAdmin
from apps.medical.models import MedicalDocumentVersion


class ExternalSelectedAttachmentLinkTests(SimpleTestCase):
    def setUp(self) -> None:
        self.site = AdminSite()
        self.admin = MedicalDocumentVersionAdmin(MedicalDocumentVersion, self.site)

    def test_returns_em_dash_when_no_attachment(self) -> None:
        ver = MedicalDocumentVersion()
        ver.external_selected_attachment = None
        self.assertEqual(self.admin.external_selected_attachment_link(ver), "—")

    def test_truncates_long_hidrive_path(self) -> None:
        long_path = "/" + ("x" * 200) + ".pdf"
        att_id = uuid.uuid4()

        class _Att:
            pass

        a = _Att()
        a.id = att_id
        a.hidrive_remote_path = long_path

        ver = MedicalDocumentVersion()
        ver.external_selected_attachment = a  # type: ignore[assignment]
        out = self.admin.external_selected_attachment_link(ver)
        self.assertIn("…", out)
        self.assertIn(str(att_id), out)
        self.assertLess(len(out), len(long_path) + 80)

    def test_empty_path_shows_em_dash_segment(self) -> None:
        class _Att2:
            id = uuid.uuid4()
            hidrive_remote_path = "   "

        ver2: Any = MedicalDocumentVersion()
        ver2.external_selected_attachment = _Att2()
        self.assertIn("—", self.admin.external_selected_attachment_link(ver2))
