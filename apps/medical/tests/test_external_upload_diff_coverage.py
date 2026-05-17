"""Diff-cover targets for external-upload API and related service edge paths."""

from __future__ import annotations

import json
import tempfile
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from pypdf import PdfWriter

from apps.core.api_utils import assign_group_to_test_user
from apps.core.exceptions import DomainError
from apps.medical.external_pdf_service import ExternalPdfCorruptError
from apps.medical.models import (
    DocVersionStatus,
    ExternalPdfAttachment,
    ExternalPdfStatus,
    MedicalDocStatus,
    MedicalDocument,
    MedicalDocumentSourceType,
    MedicalDocumentVersion,
)
from apps.medical.tests.test_api import ExternalUploadApiTests, _minimal_pdf_bytes
from apps.medical.tests.test_services_coverage import ServicesCoverageBase
from apps.medical.services import (
    _hidrive_path_is_external_upload_prefix,
    _sanitize_external_upload_filename,
    create_external_upload_medical_document,
    get_single_medical_document_for_queue_entry,
    publish_external_upload_version,
    start_external_upload_revision,
    upload_external_pdf_to_incoming,
)
from apps.reception.models import QueueEntry
from apps.users.models import StaffUser


class ExternalUploadApiDiffCoverageTests(ExternalUploadApiTests):
    """HTTP branches in ``apps.medical.api_views`` not hit by the main flow tests."""

    def test_upload_get_returns_405(self) -> None:
        self.client.force_login(self.reception_user)
        r = self.client.get("/api/v1/medical-documents/external-upload/upload")
        self.assertEqual(r.status_code, 405)

    def test_upload_missing_fields_returns_400(self) -> None:
        self.client.force_login(self.reception_user)
        r = self.client.post(
            "/api/v1/medical-documents/external-upload/upload",
            data={"queue_entry_id": str(self.queue_entry.id)},
        )
        self.assertEqual(r.status_code, 400)

    def test_upload_invalid_queue_entry_uuid_returns_400(self) -> None:
        self.client.force_login(self.reception_user)
        r = self.client.post(
            "/api/v1/medical-documents/external-upload/upload",
            data={
                "queue_entry_id": "not-a-uuid",
                "file": self._external_upload_file(),
            },
        )
        self.assertEqual(r.status_code, 400)

    def test_upload_unknown_queue_entry_returns_404(self) -> None:
        self.client.force_login(self.reception_user)
        r = self.client.post(
            "/api/v1/medical-documents/external-upload/upload",
            data={
                "queue_entry_id": str(uuid4()),
                "file": self._external_upload_file(),
            },
        )
        self.assertEqual(r.status_code, 404)

    @patch(
        "apps.medical.api_views.create_external_upload_pdf_and_bind_draft",
        side_effect=DomainError(
            "hidrive",
            api_message_key="other.api.server_error",
        ),
    )
    def test_upload_server_error_maps_to_502(self, _mock: object) -> None:
        self.client.force_login(self.reception_user)
        r = self.client.post(
            "/api/v1/medical-documents/external-upload/upload",
            data={
                "queue_entry_id": str(self.queue_entry.id),
                "file": self._external_upload_file(),
            },
        )
        self.assertEqual(r.status_code, 502)

    def test_select_get_returns_405(self) -> None:
        self.client.force_login(self.reception_user)
        r = self.client.get(
            f"/api/v1/medical-documents/{uuid4()}/external-upload/select-attachment"
        )
        self.assertEqual(r.status_code, 405)

    def test_select_invalid_json_returns_400(self) -> None:
        self.client.force_login(self.reception_user)
        r = self.client.post(
            f"/api/v1/medical-documents/{uuid4()}/external-upload/select-attachment",
            data=b"\xff\xfe",
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)

    def test_select_validation_error_returns_400(self) -> None:
        self.client.force_login(self.reception_user)
        r = self.client.post(
            f"/api/v1/medical-documents/{uuid4()}/external-upload/select-attachment",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn("details", r.json())

    def test_select_unknown_document_returns_404(self) -> None:
        self.client.force_login(self.reception_user)
        r = self.client.post(
            f"/api/v1/medical-documents/{uuid4()}/external-upload/select-attachment",
            data=json.dumps({"attachment_id": str(uuid4())}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 404)

    @patch("apps.medical.services.get_hidrive_adapter")
    def test_select_invalid_attachment_status_returns_422(
        self, adapter_factory: MagicMock
    ) -> None:
        adapter_factory.return_value.upload.return_value = None
        self.client.force_login(self.reception_user)
        up = self.client.post(
            "/api/v1/medical-documents/external-upload/upload",
            data={
                "queue_entry_id": str(self.queue_entry.id),
                "file": self._external_upload_file(),
            },
        )
        doc_id = up.json()["document_id"]
        att_id = up.json()["attachment_id"]
        ExternalPdfAttachment.objects.filter(id=att_id).update(
            status=ExternalPdfStatus.PENDING_UPLOAD
        )
        r = self.client.post(
            f"/api/v1/medical-documents/{doc_id}/external-upload/select-attachment",
            data=json.dumps({"attachment_id": att_id}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 422)

    @patch("apps.medical.services.get_hidrive_adapter")
    def test_publish_out_of_scope_returns_403(self, adapter_factory: MagicMock) -> None:
        adapter_factory.return_value.upload.return_value = None
        other = self._queue_entry_on_other_clinic()
        self._ensure_intake_submitted(other)
        self.client.force_login(self.admin_user)
        up = self.client.post(
            "/api/v1/medical-documents/external-upload/upload",
            data={
                "queue_entry_id": str(other.id),
                "file": self._external_upload_file(),
            },
        )
        doc_id = up.json()["document_id"]
        att_id = up.json()["attachment_id"]
        self.client.post(
            f"/api/v1/medical-documents/{doc_id}/external-upload/select-attachment",
            data=json.dumps({"attachment_id": att_id}),
            content_type="application/json",
        )
        self.client.force_login(self.reception_user)
        r = self.client.post(
            f"/api/v1/medical-documents/{doc_id}/external-upload/publish",
            data=json.dumps(
                {
                    "publish_request_id": str(uuid4()),
                    "publish_locale": "de-DE",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 403)

    @patch("apps.medical.services.get_hidrive_adapter")
    def test_select_out_of_scope_returns_403(self, adapter_factory: MagicMock) -> None:
        adapter_factory.return_value.upload.return_value = None
        other = self._queue_entry_on_other_clinic()
        self._ensure_intake_submitted(other)
        self.client.force_login(self.admin_user)
        up = self.client.post(
            "/api/v1/medical-documents/external-upload/upload",
            data={
                "queue_entry_id": str(other.id),
                "file": self._external_upload_file(),
            },
        )
        doc_id = up.json()["document_id"]
        att_id = up.json()["attachment_id"]
        self.client.force_login(self.reception_user)
        r = self.client.post(
            f"/api/v1/medical-documents/{doc_id}/external-upload/select-attachment",
            data=json.dumps({"attachment_id": att_id}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 403)

    def _ensure_intake_submitted(self, entry: QueueEntry) -> None:
        from apps.intake.models import IntakeStatus, PatientIntakeForm
        from apps.reception.models import PatientFormSession
        from datetime import timedelta

        session = PatientFormSession.objects.create(
            queue_entry=entry,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=self.admin_user,
        )
        PatientIntakeForm.objects.create(
            queue_entry=entry,
            session=session,
            form_status=IntakeStatus.SUBMITTED,
            submitted_at=timezone.now(),
            signature_sha256="e" * 64,
        )

    def test_preview_post_returns_405(self) -> None:
        self.client.force_login(self.reception_user)
        r = self.client.post(
            f"/api/v1/medical-documents/{uuid4()}/external-upload/preview-pdf"
        )
        self.assertEqual(r.status_code, 405)

    def test_preview_unknown_document_returns_404(self) -> None:
        self.client.force_login(self.reception_user)
        r = self.client.get(
            f"/api/v1/medical-documents/{uuid4()}/external-upload/preview-pdf"
        )
        self.assertEqual(r.status_code, 404)

    def test_preview_non_external_source_returns_422(self) -> None:
        doc = MedicalDocument.objects.create(
            queue_entry=self.queue_entry,
            intake_form=self.intake_form,
            source_type=MedicalDocumentSourceType.DIGITAL_INTAKE,
            status=MedicalDocStatus.DRAFT,
            current_version_no=0,
            created_by_user=self.doctor_user,
        )
        self.client.force_login(self.reception_user)
        r = self.client.get(
            f"/api/v1/medical-documents/{doc.id}/external-upload/preview-pdf"
        )
        self.assertEqual(r.status_code, 422)

    def test_preview_invalid_source_query_returns_400(self) -> None:
        with patch("apps.medical.services.get_hidrive_adapter") as adapter_factory:
            adapter_factory.return_value.upload.return_value = None
            self.client.force_login(self.reception_user)
            up = self.client.post(
                "/api/v1/medical-documents/external-upload/upload",
                data={
                    "queue_entry_id": str(self.queue_entry.id),
                    "file": self._external_upload_file(),
                },
            )
        doc_id = up.json()["document_id"]
        r = self.client.get(
            f"/api/v1/medical-documents/{doc_id}/external-upload/preview-pdf",
            {"source": "bogus"},
        )
        self.assertEqual(r.status_code, 400)

    @patch("apps.medical.api_views.download_external_pdf")
    @patch("apps.medical.services.get_hidrive_adapter")
    def test_preview_without_selected_attachment_returns_422(
        self, adapter_factory: MagicMock, mock_download: MagicMock
    ) -> None:
        mock_download.return_value = _minimal_pdf_bytes()
        adapter_factory.return_value.upload.return_value = None
        self.client.force_login(self.reception_user)
        up = self.client.post(
            "/api/v1/medical-documents/external-upload/upload",
            data={
                "queue_entry_id": str(self.queue_entry.id),
                "file": self._external_upload_file(),
            },
        )
        doc_id = up.json()["document_id"]
        r = self.client.get(
            f"/api/v1/medical-documents/{doc_id}/external-upload/preview-pdf"
        )
        self.assertEqual(r.status_code, 422)

    @patch("apps.medical.api_views.download_external_pdf")
    @patch("apps.medical.services.get_hidrive_adapter")
    def test_preview_corrupt_pdf_returns_422(
        self, adapter_factory: MagicMock, mock_download: MagicMock
    ) -> None:
        adapter_factory.return_value.upload.return_value = None
        mock_download.side_effect = ExternalPdfCorruptError("bad")
        self.client.force_login(self.reception_user)
        up = self.client.post(
            "/api/v1/medical-documents/external-upload/upload",
            data={
                "queue_entry_id": str(self.queue_entry.id),
                "file": self._external_upload_file(),
            },
        )
        doc_id = up.json()["document_id"]
        att_id = up.json()["attachment_id"]
        self.client.post(
            f"/api/v1/medical-documents/{doc_id}/external-upload/select-attachment",
            data=json.dumps({"attachment_id": att_id}),
            content_type="application/json",
        )
        r = self.client.get(
            f"/api/v1/medical-documents/{doc_id}/external-upload/preview-pdf"
        )
        self.assertEqual(r.status_code, 422)

    @override_settings(DEBUG=False)
    @patch("apps.medical.api_views.download_external_pdf")
    @patch("apps.medical.services.get_hidrive_adapter")
    def test_preview_infra_error_returns_502(
        self, adapter_factory: MagicMock, mock_download: MagicMock
    ) -> None:
        adapter_factory.return_value.upload.return_value = None
        mock_download.side_effect = RuntimeError("hidrive down")
        self.client.force_login(self.reception_user)
        up = self.client.post(
            "/api/v1/medical-documents/external-upload/upload",
            data={
                "queue_entry_id": str(self.queue_entry.id),
                "file": self._external_upload_file(),
            },
        )
        doc_id = up.json()["document_id"]
        att_id = up.json()["attachment_id"]
        self.client.post(
            f"/api/v1/medical-documents/{doc_id}/external-upload/select-attachment",
            data=json.dumps({"attachment_id": att_id}),
            content_type="application/json",
        )
        r = self.client.get(
            f"/api/v1/medical-documents/{doc_id}/external-upload/preview-pdf"
        )
        self.assertEqual(r.status_code, 502)

    @patch("apps.medical.api_views.download_external_pdf")
    @patch("apps.medical.services.get_hidrive_adapter")
    def test_preview_published_from_local_pdf_path(
        self, adapter_factory: MagicMock, mock_download: MagicMock
    ) -> None:
        mock_download.return_value = _minimal_pdf_bytes()
        adapter_factory.return_value.upload.return_value = None
        self.client.force_login(self.reception_user)
        up = self.client.post(
            "/api/v1/medical-documents/external-upload/upload",
            data={
                "queue_entry_id": str(self.queue_entry.id),
                "file": self._external_upload_file(),
            },
        )
        doc_id = up.json()["document_id"]
        att_id = up.json()["attachment_id"]
        self.client.post(
            f"/api/v1/medical-documents/{doc_id}/external-upload/select-attachment",
            data=json.dumps({"attachment_id": att_id}),
            content_type="application/json",
        )
        self.client.post(
            f"/api/v1/medical-documents/{doc_id}/external-upload/publish",
            data=json.dumps(
                {
                    "publish_request_id": str(uuid4()),
                    "publish_locale": "de-DE",
                }
            ),
            content_type="application/json",
        )
        with tempfile.TemporaryDirectory() as media_root:
            rel = "external/published-preview.pdf"
            full = Path(media_root) / rel
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_bytes(_minimal_pdf_bytes())
            MedicalDocumentVersion.objects.filter(
                medical_document_id=doc_id,
                version_status=DocVersionStatus.PUBLISHED,
            ).update(pdf_local_path=rel)
            with override_settings(MEDIA_ROOT=media_root):
                r = self.client.get(
                    f"/api/v1/medical-documents/{doc_id}/external-upload/preview-pdf",
                    {"source": "published"},
                )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["X-External-Upload-Preview-Source"], "published")

    @patch("apps.medical.api_views.download_external_pdf")
    @patch("apps.medical.services.get_hidrive_adapter")
    def test_preview_auto_uses_draft_when_pending_revision(
        self, adapter_factory: MagicMock, mock_download: MagicMock
    ) -> None:
        mock_download.return_value = _minimal_pdf_bytes()
        adapter_factory.return_value.upload.return_value = None
        self.client.force_login(self.reception_user)
        up = self.client.post(
            "/api/v1/medical-documents/external-upload/upload",
            data={
                "queue_entry_id": str(self.queue_entry.id),
                "file": self._external_upload_file(),
            },
        )
        doc_id = up.json()["document_id"]
        att_id = up.json()["attachment_id"]
        self.client.post(
            f"/api/v1/medical-documents/{doc_id}/external-upload/select-attachment",
            data=json.dumps({"attachment_id": att_id}),
            content_type="application/json",
        )
        self.client.post(
            f"/api/v1/medical-documents/{doc_id}/external-upload/publish",
            data=json.dumps(
                {
                    "publish_request_id": str(uuid4()),
                    "publish_locale": "de-DE",
                }
            ),
            content_type="application/json",
        )
        self.client.post(
            f"/api/v1/medical-documents/{doc_id}/external-upload/revision/start",
            data=json.dumps({}),
            content_type="application/json",
        )
        r = self.client.get(
            f"/api/v1/medical-documents/{doc_id}/external-upload/preview-pdf"
        )
        self.assertEqual(r.status_code, 422)

    def test_publish_get_returns_405(self) -> None:
        self.client.force_login(self.reception_user)
        r = self.client.get(
            f"/api/v1/medical-documents/{uuid4()}/external-upload/publish"
        )
        self.assertEqual(r.status_code, 405)

    def test_publish_invalid_json_returns_400(self) -> None:
        self.client.force_login(self.reception_user)
        r = self.client.post(
            f"/api/v1/medical-documents/{uuid4()}/external-upload/publish",
            data=b"\xff",
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)

    def test_publish_validation_error_returns_400(self) -> None:
        self.client.force_login(self.reception_user)
        r = self.client.post(
            f"/api/v1/medical-documents/{uuid4()}/external-upload/publish",
            data=json.dumps({"publish_request_id": str(uuid4())}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)

    def test_revision_get_returns_405(self) -> None:
        self.client.force_login(self.reception_user)
        r = self.client.get(
            f"/api/v1/medical-documents/{uuid4()}/external-upload/revision/start"
        )
        self.assertEqual(r.status_code, 405)

    def test_revision_invalid_json_returns_400(self) -> None:
        self.client.force_login(self.reception_user)
        r = self.client.post(
            f"/api/v1/medical-documents/{uuid4()}/external-upload/revision/start",
            data=b"\xff",
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)

    @override_settings(DEBUG=False)
    @patch("apps.medical.api_views.download_external_pdf")
    @patch("apps.medical.services.get_hidrive_adapter")
    def test_doctor_preview_external_missing_attachment_returns_404(
        self, adapter_factory: MagicMock, mock_download: MagicMock
    ) -> None:
        mock_download.return_value = _minimal_pdf_bytes()
        adapter_factory.return_value.upload.return_value = None
        self.client.force_login(self.reception_user)
        up = self.client.post(
            "/api/v1/medical-documents/external-upload/upload",
            data={
                "queue_entry_id": str(self.queue_entry.id),
                "file": self._external_upload_file(),
            },
        )
        doc_id = up.json()["document_id"]
        att_id = up.json()["attachment_id"]
        self.client.post(
            f"/api/v1/medical-documents/{doc_id}/external-upload/select-attachment",
            data=json.dumps({"attachment_id": att_id}),
            content_type="application/json",
        )
        self.client.force_login(self.doctor_user)
        with patch.object(
            ExternalPdfAttachment.objects,
            "get",
            side_effect=ExternalPdfAttachment.DoesNotExist,
        ):
            r = self.client.get(f"/api/v1/medical-documents/{doc_id}/preview-pdf")
        self.assertEqual(r.status_code, 404)

    @override_settings(DEBUG=False)
    @patch("apps.medical.api_views.download_external_pdf")
    @patch("apps.medical.services.get_hidrive_adapter")
    def test_doctor_preview_external_corrupt_returns_422(
        self, adapter_factory: MagicMock, mock_download: MagicMock
    ) -> None:
        adapter_factory.return_value.upload.return_value = None
        mock_download.side_effect = ExternalPdfCorruptError("bad")
        self.client.force_login(self.reception_user)
        up = self.client.post(
            "/api/v1/medical-documents/external-upload/upload",
            data={
                "queue_entry_id": str(self.queue_entry.id),
                "file": self._external_upload_file(),
            },
        )
        doc_id = up.json()["document_id"]
        att_id = up.json()["attachment_id"]
        self.client.post(
            f"/api/v1/medical-documents/{doc_id}/external-upload/select-attachment",
            data=json.dumps({"attachment_id": att_id}),
            content_type="application/json",
        )
        self.client.force_login(self.doctor_user)
        r = self.client.get(f"/api/v1/medical-documents/{doc_id}/preview-pdf")
        self.assertEqual(r.status_code, 422)

    @override_settings(DEBUG=False)
    @patch(
        "apps.medical.api_views.download_external_pdf", side_effect=RuntimeError("x")
    )
    @patch("apps.medical.services.get_hidrive_adapter")
    def test_doctor_preview_external_infra_error_returns_502(
        self, adapter_factory: MagicMock, _mock_dl: MagicMock
    ) -> None:
        adapter_factory.return_value.upload.return_value = None
        self.client.force_login(self.reception_user)
        up = self.client.post(
            "/api/v1/medical-documents/external-upload/upload",
            data={
                "queue_entry_id": str(self.queue_entry.id),
                "file": self._external_upload_file(),
            },
        )
        doc_id = up.json()["document_id"]
        att_id = up.json()["attachment_id"]
        self.client.post(
            f"/api/v1/medical-documents/{doc_id}/external-upload/select-attachment",
            data=json.dumps({"attachment_id": att_id}),
            content_type="application/json",
        )
        self.client.force_login(self.doctor_user)
        r = self.client.get(f"/api/v1/medical-documents/{doc_id}/preview-pdf")
        self.assertEqual(r.status_code, 502)


class ExternalUploadServiceDiffCoverageTests(ServicesCoverageBase):
    """Unit tests for uncovered ``apps.medical.services`` diff lines."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.reception = StaffUser.objects.create_user(
            username="cov-reception-eu-diff",
            email="cov-reception-eu-diff@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(cls.reception, "Reception")

    def test_sanitize_empty_filename_gets_generated_pdf_name(self) -> None:
        name = _sanitize_external_upload_filename("   ")
        self.assertTrue(name.endswith(".pdf"))
        self.assertIn("external_", name)

    def test_hidrive_path_prefix_rejects_empty_and_traversal(self) -> None:
        self.assertFalse(_hidrive_path_is_external_upload_prefix(""))
        self.assertFalse(_hidrive_path_is_external_upload_prefix("/../etc/passwd"))

    def test_get_single_medical_document_raises_when_multiple_rows(self) -> None:
        doc = create_external_upload_medical_document(
            queue_entry_id=self.queue_entry.id,
            created_by_user_id=self.reception.id,
        )
        MedicalDocument.objects.create(
            queue_entry_id=self.queue_entry.id,
            intake_form_id=doc.intake_form_id,
            source_type=MedicalDocumentSourceType.EXTERNAL_UPLOAD,
            created_by_user_id=self.reception.id,
            updated_by_user_id=self.reception.id,
        )
        with self.assertRaises(DomainError) as ctx:
            get_single_medical_document_for_queue_entry(
                queue_entry_id=self.queue_entry.id
            )
        self.assertIn(
            "external_upload_multiple_medical_documents_for_queue_entry",
            ctx.exception.api_message_key,
        )

    @patch("apps.medical.services.get_hidrive_adapter")
    def test_upload_persists_non_temp_file_to_temp_path(
        self, adapter_factory: MagicMock
    ) -> None:
        doc = create_external_upload_medical_document(
            queue_entry_id=self.queue_entry.id,
            created_by_user_id=self.reception.id,
        )
        adapter_factory.return_value.upload.return_value = None
        upload = SimpleUploadedFile(
            "lab.pdf", _minimal_pdf_bytes(), content_type="application/pdf"
        )
        att = upload_external_pdf_to_incoming(
            medical_document_id=doc.id,
            uploaded_file=upload,
            actor_user_id=self.reception.id,
        )
        self.assertEqual(att.status, ExternalPdfStatus.MATCHED)

    def test_publish_staff_user_not_found_raises(self) -> None:
        doc = create_external_upload_medical_document(
            queue_entry_id=self.queue_entry.id,
            created_by_user_id=self.reception.id,
        )
        with self.assertRaises(DomainError) as ctx:
            publish_external_upload_version(
                medical_document_id=doc.id,
                publish_request_id=uuid4(),
                published_by_user_id=uuid4(),
                publish_locale="de-DE",
            )
        self.assertIn("staff_user_not_found", ctx.exception.api_message_key)

    @patch("apps.medical.services.get_hidrive_adapter")
    def test_start_revision_requires_published_document(
        self, adapter_factory: MagicMock
    ) -> None:
        adapter_factory.return_value.upload.return_value = None
        doc = create_external_upload_medical_document(
            queue_entry_id=self.queue_entry.id,
            created_by_user_id=self.reception.id,
        )
        with self.assertRaises(DomainError) as ctx:
            start_external_upload_revision(
                medical_document_id=doc.id,
                actor_user_id=self.reception.id,
            )
        self.assertIn(
            "external_upload_revision_requires_published",
            ctx.exception.api_message_key,
        )

    def test_upload_unknown_actor_raises_staff_not_found(self) -> None:
        doc = create_external_upload_medical_document(
            queue_entry_id=self.queue_entry.id,
            created_by_user_id=self.reception.id,
        )
        with self.assertRaises(DomainError) as ctx:
            upload_external_pdf_to_incoming(
                medical_document_id=doc.id,
                uploaded_file=SimpleUploadedFile(
                    "x.pdf", _minimal_pdf_bytes(), content_type="application/pdf"
                ),
                actor_user_id=uuid4(),
            )
        self.assertIn("staff_user_not_found", ctx.exception.api_message_key)

    def test_create_external_upload_bootstraps_draft_when_document_has_no_versions(
        self,
    ) -> None:
        doc = MedicalDocument.objects.create(
            queue_entry=self.queue_entry,
            intake_form=self.intake,
            source_type=MedicalDocumentSourceType.EXTERNAL_UPLOAD,
            status=MedicalDocStatus.DRAFT,
            current_version_no=0,
            created_by_user=self.reception,
            updated_by_user=self.reception,
        )
        out = create_external_upload_medical_document(
            queue_entry_id=self.queue_entry.id,
            created_by_user_id=self.reception.id,
        )
        self.assertEqual(out.id, doc.id)
        self.assertTrue(
            MedicalDocumentVersion.objects.filter(medical_document_id=doc.id).exists()
        )

    @patch("apps.medical.services.get_hidrive_adapter")
    def test_publish_republish_creates_republished_audit(
        self, adapter_factory: MagicMock
    ) -> None:
        from apps.operations.models import AuditEvent

        adapter_factory.return_value.upload.return_value = None
        doc = create_external_upload_medical_document(
            queue_entry_id=self.queue_entry.id,
            created_by_user_id=self.reception.id,
        )
        upload = SimpleUploadedFile(
            "lab.pdf", _minimal_pdf_bytes(), content_type="application/pdf"
        )
        att = upload_external_pdf_to_incoming(
            medical_document_id=doc.id,
            uploaded_file=upload,
            actor_user_id=self.reception.id,
        )
        draft = MedicalDocumentVersion.objects.get(
            medical_document_id=doc.id, version_status=DocVersionStatus.DRAFT
        )
        draft.external_selected_attachment = att
        draft.save(update_fields=["external_selected_attachment"])
        rid = uuid4()
        publish_external_upload_version(
            medical_document_id=doc.id,
            publish_request_id=rid,
            published_by_user_id=self.reception.id,
            publish_locale="de-DE",
        )
        start_external_upload_revision(
            medical_document_id=doc.id,
            actor_user_id=self.reception.id,
        )
        draft2 = (
            MedicalDocumentVersion.objects.filter(
                medical_document_id=doc.id,
                version_status=DocVersionStatus.DRAFT,
            )
            .order_by("-version_no")
            .first()
        )
        assert draft2 is not None
        draft2.external_selected_attachment = att
        draft2.save(update_fields=["external_selected_attachment"])
        publish_external_upload_version(
            medical_document_id=doc.id,
            publish_request_id=uuid4(),
            published_by_user_id=self.reception.id,
            publish_locale="de-DE",
        )
        self.assertTrue(
            AuditEvent.objects.filter(
                event_type="DOCUMENT_REPUBLISHED",
                medical_document_id=doc.id,
            ).exists()
        )

    def test_upload_zero_page_pdf_raises(self) -> None:
        doc = create_external_upload_medical_document(
            queue_entry_id=self.queue_entry.id,
            created_by_user_id=self.reception.id,
        )
        writer = PdfWriter()
        buf = BytesIO()
        writer.write(buf)
        with self.assertRaises(DomainError) as ctx:
            upload_external_pdf_to_incoming(
                medical_document_id=doc.id,
                uploaded_file=SimpleUploadedFile(
                    "empty.pdf", buf.getvalue(), content_type="application/pdf"
                ),
                actor_user_id=self.reception.id,
            )
        self.assertIn(
            "external_upload_invalid_or_empty_pdf",
            ctx.exception.api_message_key,
        )
