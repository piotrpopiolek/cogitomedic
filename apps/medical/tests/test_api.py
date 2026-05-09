from __future__ import annotations

import json
from datetime import date, timedelta
from io import BytesIO
from unittest.mock import patch
from uuid import uuid4

from django.core.exceptions import ObjectDoesNotExist
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.utils import timezone
from pypdf import PdfWriter

from apps.intake.models import IntakeStatus, PatientIntakeForm
from apps.core.api_utils import assign_group_to_test_user
from apps.core.exceptions import DomainError
from apps.medical.models import (
    ExternalPdfAttachment,
    ExternalPdfStatus,
    MedicalDocStatus,
    MedicalDocument,
    MedicalDocumentSourceType,
    MedicalDocumentVersion,
)
from apps.medical.services import authorize_paper_intake
from apps.operations.models import AuditEvent
from apps.outbox.models import OutboxEvent, OutboxEventType, OutboxStatus
from apps.reception.models import (
    ClinicSite,
    ConsultingRoom,
    DailyQueue,
    Patient,
    PatientFormSession,
    QueueEntry,
    QueueEntryStatus,
    QueueStatus,
)
from apps.users.models import StaffUser

_PAPER_AUTH_REASON = (
    "Paper intake path authorized for this queue entry in test (long enough)."
)


def _minimal_pdf_bytes() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


class MedicalApiTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.doctor_user = StaffUser.objects.create_user(
            username="api-doctor",
            email="api.doctor@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.doctor_user, "Doctor")

        self.reception_user = StaffUser.objects.create_user(
            username="api-reception-medical",
            email="api.reception.medical@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.reception_user, "Reception")

        self.admin_user = StaffUser.objects.create_user(
            username="api-admin-medical",
            email="api.admin.medical@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.admin_user, "Admin")
        clinic = ClinicSite.objects.create(code="API2", name="API Clinic 2")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="B1", name="B1")
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            created_by_user=self.reception_user,
            assigned_doctor=self.doctor_user,
        )
        patient = Patient.objects.create(
            first_name="Medical",
            last_name="Api",
            date_of_birth=date(1988, 8, 8),
            phone="+48111222333",
            email="medical.api@example.com",
            doctolib_patient_id="DOC-API-MED-1",
        )
        self.queue_entry = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
            position_no=1,
            created_by_user=self.reception_user,
        )
        session = PatientFormSession.objects.create(
            queue_entry=self.queue_entry,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(minutes=30),
            consumed_at=timezone.now(),
            created_by_user=self.reception_user,
        )
        self.queue_entry.active_session = session
        self.queue_entry.save(update_fields=["active_session", "updated_at"])
        self.intake_form = PatientIntakeForm.objects.create(
            queue_entry=self.queue_entry,
            session=session,
            form_status=IntakeStatus.SUBMITTED,
            signature_file_path="/tmp/signature.png",
            signature_sha256="c" * 64,
            submitted_at=timezone.now(),
            anamnesis_payload={"schema_version": 1, "answers": []},
        )
        self.client.force_login(self.doctor_user)

    def _external_upload_file(
        self, *, name: str = "lab.pdf", content: bytes | None = None
    ):
        data = content if content is not None else _minimal_pdf_bytes()
        return SimpleUploadedFile(name, data, content_type="application/pdf")

    def test_medical_document_create_draft_publish_flow(self) -> None:
        create_response = self.client.post(
            "/api/v1/medical-documents",
            data=json.dumps(
                {
                    "queue_entry_id": str(self.queue_entry.id),
                    "intake_form_id": str(self.intake_form.id),
                    "created_by_user_id": str(self.doctor_user.id),
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(create_response.status_code, 201)
        medical_document_id = create_response.json()["medical_document_id"]

        invalid_draft_response = self.client.put(
            f"/api/v1/medical-documents/{medical_document_id}/draft",
            data=json.dumps(
                {
                    "updated_by_user_id": str(self.doctor_user.id),
                    "medical_payload_schema_version": 1,
                    "medical_payload": {"schema_version": 2},
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(invalid_draft_response.status_code, 400)

        draft_response = self.client.put(
            f"/api/v1/medical-documents/{medical_document_id}/draft",
            data=json.dumps(
                {
                    "updated_by_user_id": str(self.doctor_user.id),
                    "medical_payload_schema_version": 1,
                    "medical_payload": {
                        "schema_version": 1,
                        "authoring_locale": "de-DE",
                        "lesions": [],
                        "examination_scope": ["INTIMATE_AREA_NOT_EXAMINED"],
                        "fitzpatrick_type": "TYPE_III",
                        "overall_image_assessment": "NO_CONTROL_NEEDED",
                        "recommendations": ["NO_SHORT_TERM_FOLLOWUP_REQUIRED"],
                        "final_assessment": "NO_HIGH_GRADE_SUSPICION",
                    },
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(draft_response.status_code, 200)
        self.assertEqual(draft_response.json()["version_status"], "DRAFT")

        publish_response = self.client.post(
            f"/api/v1/medical-documents/{medical_document_id}/publish",
            data=json.dumps(
                {
                    "publish_request_id": str(uuid4()),
                    "published_by_user_id": str(self.doctor_user.id),
                    "publish_locale": "de-DE",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(publish_response.status_code, 200)
        self.assertEqual(publish_response.json()["version_status"], "PUBLISHED")

        version_id = publish_response.json()["medical_document_version_id"]
        version = MedicalDocumentVersion.objects.get(id=version_id)
        self.assertEqual(version.version_status, "PUBLISHED")
        self.assertEqual(version.medical_document.status, MedicalDocStatus.PUBLISHED)

    def test_medical_documents_list_get(self) -> None:
        list_empty = self.client.get("/api/v1/medical-documents")
        self.assertEqual(list_empty.status_code, 200)
        data = list_empty.json()
        self.assertIn("items", data)
        self.assertIn("pagination", data)
        self.assertEqual(data["pagination"]["total"], 0)
        self.assertEqual(len(data["items"]), 0)

        self.client.post(
            "/api/v1/medical-documents",
            data=json.dumps(
                {
                    "queue_entry_id": str(self.queue_entry.id),
                    "intake_form_id": str(self.intake_form.id),
                    "created_by_user_id": str(self.doctor_user.id),
                }
            ),
            content_type="application/json",
        )
        list_one = self.client.get("/api/v1/medical-documents")
        self.assertEqual(list_one.status_code, 200)
        data = list_one.json()
        self.assertEqual(data["pagination"]["total"], 1)
        self.assertEqual(len(data["items"]), 1)
        item = data["items"][0]
        self.assertEqual(item["status"], MedicalDocStatus.DRAFT)
        self.assertIn("queue_date", item)
        self.assertIn("patient", item)
        self.assertEqual(item["patient"]["last_name"], "Api")

    def test_medical_document_detail_get(self) -> None:
        create_response = self.client.post(
            "/api/v1/medical-documents",
            data=json.dumps(
                {
                    "queue_entry_id": str(self.queue_entry.id),
                    "intake_form_id": str(self.intake_form.id),
                    "created_by_user_id": str(self.doctor_user.id),
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(create_response.status_code, 201)
        medical_document_id = create_response.json()["medical_document_id"]

        detail = self.client.get(f"/api/v1/medical-documents/{medical_document_id}")
        self.assertEqual(detail.status_code, 200)
        data = detail.json()
        self.assertEqual(data["id"], medical_document_id)
        self.assertEqual(data["queue_entry_id"], str(self.queue_entry.id))
        self.assertEqual(
            data.get("source_type"), MedicalDocumentSourceType.DIGITAL_INTAKE
        )
        self.assertIsNone(data.get("paper_intake_authorization"))
        self.assertIn("intake_summary", data)
        self.assertIn("patient", data["intake_summary"])
        self.assertIn("current_version", data)
        self.assertIsNone(data["current_version"])  # no version yet before first draft

        missing = self.client.get(f"/api/v1/medical-documents/{uuid4()}")
        self.assertEqual(missing.status_code, 404)

    def test_create_medical_document_no_intake_happy_path(self) -> None:
        waiting_entry = QueueEntry.objects.create(
            daily_queue=self.queue_entry.daily_queue,
            patient=self.queue_entry.patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=2,
            appointment_time=timezone.now() - timedelta(hours=4),
            created_by_user=self.reception_user,
        )
        authorize_paper_intake(
            queue_entry_id=waiting_entry.id,
            authorized_by_user_id=self.admin_user.id,
            reason=_PAPER_AUTH_REASON,
        )
        response = self.client.post(
            "/api/v1/medical-documents/no-intake",
            data=json.dumps(
                {
                    "queue_entry_id": str(waiting_entry.id),
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        document = MedicalDocument.objects.get(id=body["medical_document_id"])
        waiting_entry.refresh_from_db()
        self.assertEqual(document.source_type, MedicalDocumentSourceType.PAPER_INTAKE)
        self.assertIsNone(document.intake_form_id)
        self.assertEqual(
            waiting_entry.entry_status,
            QueueEntryStatus.PAPER_INTAKE_COMPLETED,
        )

    def test_create_medical_document_no_intake_reception_forbidden(self) -> None:
        self.client.force_login(self.reception_user)
        response = self.client.post(
            "/api/v1/medical-documents/no-intake",
            data=json.dumps(
                {
                    "queue_entry_id": str(uuid4()),
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_create_medical_document_no_intake_before_3h_returns_400(self) -> None:
        waiting_entry = QueueEntry.objects.create(
            daily_queue=self.queue_entry.daily_queue,
            patient=self.queue_entry.patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=3,
            appointment_time=timezone.now() - timedelta(hours=2, minutes=59),
            created_by_user=self.reception_user,
        )
        response = self.client.post(
            "/api/v1/medical-documents/no-intake",
            data=json.dumps(
                {
                    "queue_entry_id": str(waiting_entry.id),
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json().get("error_key"),
            "other.domain.paper_intake_earliest_after_appointment",
        )

    def _paper_auth_url(self, queue_entry_id) -> str:
        return f"/api/v1/queue-entries/{queue_entry_id}/paper-intake-authorization"

    def test_paper_intake_authorization_post_doctor_forbidden(self) -> None:
        waiting_entry = QueueEntry.objects.create(
            daily_queue=self.queue_entry.daily_queue,
            patient=self.queue_entry.patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=40,
            appointment_time=timezone.now() - timedelta(hours=4),
            created_by_user=self.reception_user,
        )
        self.client.force_login(self.doctor_user)
        r = self.client.post(
            self._paper_auth_url(waiting_entry.id),
            data=json.dumps({"reason": _PAPER_AUTH_REASON}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 403)

    def test_paper_intake_authorization_post_reception_forbidden(self) -> None:
        waiting_entry = QueueEntry.objects.create(
            daily_queue=self.queue_entry.daily_queue,
            patient=self.queue_entry.patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=41,
            appointment_time=timezone.now() - timedelta(hours=4),
            created_by_user=self.reception_user,
        )
        self.client.force_login(self.reception_user)
        r = self.client.post(
            self._paper_auth_url(waiting_entry.id),
            data=json.dumps({"reason": _PAPER_AUTH_REASON}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 403)

    def test_paper_intake_authorization_post_short_reason_returns_400(self) -> None:
        waiting_entry = QueueEntry.objects.create(
            daily_queue=self.queue_entry.daily_queue,
            patient=self.queue_entry.patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=42,
            appointment_time=timezone.now() - timedelta(hours=4),
            created_by_user=self.reception_user,
        )
        self.client.force_login(self.admin_user)
        r = self.client.post(
            self._paper_auth_url(waiting_entry.id),
            data=json.dumps({"reason": "short"}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json().get("error_key"), "other.api.invalid_request_body")

    def test_paper_intake_authorization_manager_out_of_assigned_clinic_succeeds(
        self,
    ) -> None:
        other_site = ClinicSite.objects.create(code="API-OTHER", name="Other Site")
        other_room = ConsultingRoom.objects.create(
            clinic_site=other_site, code="X1", name="X1"
        )
        other_queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=other_site,
            consulting_room=other_room,
            status=QueueStatus.OPEN,
            created_by_user=self.reception_user,
            assigned_doctor=self.doctor_user,
        )
        waiting_entry = QueueEntry.objects.create(
            daily_queue=other_queue,
            patient=self.queue_entry.patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=1,
            appointment_time=timezone.now() - timedelta(hours=4),
            created_by_user=self.reception_user,
        )
        manager = StaffUser.objects.create_user(
            username="api-mgr-paper-scope",
            email="api.mgr.paper.scope@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(manager, "Manager")
        manager.clinic_sites.add(self.queue_entry.daily_queue.clinic_site)
        self.client.force_login(manager)
        r = self.client.post(
            self._paper_auth_url(waiting_entry.id),
            data=json.dumps({"reason": _PAPER_AUTH_REASON}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 201)
        body = r.json()
        self.assertIn("paper_intake_authorization_id", body)
        self.assertEqual(body["queue_entry_id"], str(waiting_entry.id))

    def test_paper_intake_authorization_post_admin_201_duplicate_400_delete_200(
        self,
    ) -> None:
        waiting_entry = QueueEntry.objects.create(
            daily_queue=self.queue_entry.daily_queue,
            patient=self.queue_entry.patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=43,
            appointment_time=timezone.now() - timedelta(hours=4),
            created_by_user=self.reception_user,
        )
        self.client.force_login(self.admin_user)
        url = self._paper_auth_url(waiting_entry.id)
        created = self.client.post(
            url,
            data=json.dumps({"reason": _PAPER_AUTH_REASON}),
            content_type="application/json",
        )
        self.assertEqual(created.status_code, 201)
        body = created.json()
        self.assertIn("paper_intake_authorization_id", body)
        self.assertEqual(body["queue_entry_id"], str(waiting_entry.id))

        dup = self.client.post(
            url,
            data=json.dumps(
                {
                    "reason": (
                        "Second authorization attempt must fail for this queue entry."
                    )
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(dup.status_code, 400)
        self.assertEqual(
            dup.json().get("error_key"),
            "other.domain.paper_intake_authorization_already_exists",
        )

        revoke_reason = (
            "Manager or admin revoking paper path in API test (long enough text)."
        )
        deleted = self.client.delete(
            url,
            data=json.dumps({"reason": revoke_reason}),
            content_type="application/json",
        )
        self.assertEqual(deleted.status_code, 200)
        self.assertTrue(deleted.json().get("revoked"))

        again = self.client.delete(
            url,
            data=json.dumps({"reason": revoke_reason}),
            content_type="application/json",
        )
        self.assertEqual(again.status_code, 400)
        self.assertEqual(
            again.json().get("error_key"),
            "other.domain.paper_intake_authorization_not_found",
        )

    def test_medical_document_detail_get_for_no_intake_returns_null_intake(
        self,
    ) -> None:
        waiting_entry = QueueEntry.objects.create(
            daily_queue=self.queue_entry.daily_queue,
            patient=self.queue_entry.patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=4,
            appointment_time=timezone.now() - timedelta(hours=4),
            created_by_user=self.reception_user,
        )
        authorize_paper_intake(
            queue_entry_id=waiting_entry.id,
            authorized_by_user_id=self.admin_user.id,
            reason=_PAPER_AUTH_REASON,
        )
        create_response = self.client.post(
            "/api/v1/medical-documents/no-intake",
            data=json.dumps(
                {
                    "queue_entry_id": str(waiting_entry.id),
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(create_response.status_code, 201)
        medical_document_id = create_response.json()["medical_document_id"]

        detail = self.client.get(f"/api/v1/medical-documents/{medical_document_id}")
        self.assertEqual(detail.status_code, 200)
        payload = detail.json()
        self.assertEqual(payload["source_type"], MedicalDocumentSourceType.PAPER_INTAKE)
        self.assertIsNone(payload["intake_form_id"])
        paper = payload["paper_intake_authorization"]
        self.assertIsNotNone(paper)
        self.assertEqual(paper["reason"], _PAPER_AUTH_REASON)
        self.assertEqual(paper["authorized_by_user_id"], str(self.admin_user.id))
        self.assertIsInstance(paper.get("authorized_at"), str)
        self.assertTrue((paper.get("authorized_by_username") or "").strip())
        self.assertEqual(payload["intake_summary"]["consents"], [])
        self.assertEqual(payload["intake_summary"]["anamnesis_questions"], [])
        self.assertEqual(
            payload["intake_summary"]["patient"]["id"],
            str(self.queue_entry.patient_id),
        )
        patient = self.queue_entry.patient
        self.assertEqual(
            payload["intake_summary"]["patient"]["first_name"], patient.first_name
        )
        self.assertEqual(
            payload["intake_summary"]["patient"]["last_name"], patient.last_name
        )
        self.assertEqual(
            payload["intake_summary"]["patient"]["date_of_birth"],
            patient.date_of_birth.isoformat() if patient.date_of_birth else None,
        )
        self.assertEqual(payload["intake_summary"]["patient"]["phone"], patient.phone)
        self.assertEqual(payload["intake_summary"]["patient"]["email"], patient.email)

    def test_medical_document_detail_get_paper_without_audit_snapshot_returns_422(
        self,
    ) -> None:
        waiting_entry = QueueEntry.objects.create(
            daily_queue=self.queue_entry.daily_queue,
            patient=self.queue_entry.patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=44,
            appointment_time=timezone.now() - timedelta(hours=4),
            created_by_user=self.reception_user,
        )
        authorize_paper_intake(
            queue_entry_id=waiting_entry.id,
            authorized_by_user_id=self.admin_user.id,
            reason=_PAPER_AUTH_REASON,
        )
        create_response = self.client.post(
            "/api/v1/medical-documents/no-intake",
            data=json.dumps({"queue_entry_id": str(waiting_entry.id)}),
            content_type="application/json",
        )
        self.assertEqual(create_response.status_code, 201)
        medical_document_id = create_response.json()["medical_document_id"]
        AuditEvent.objects.filter(
            medical_document_id=medical_document_id,
            event_type="MEDICAL_DOCUMENT_CREATED_WITHOUT_INTAKE",
        ).delete()
        detail = self.client.get(f"/api/v1/medical-documents/{medical_document_id}")
        self.assertEqual(detail.status_code, 422)
        self.assertEqual(
            detail.json().get("error_key"),
            "other.domain.paper_intake_document_audit_snapshot_missing",
        )

    def test_published_version_keeps_template_snapshot_after_template_change(
        self,
    ) -> None:
        create_response = self.client.post(
            "/api/v1/medical-documents",
            data=json.dumps(
                {
                    "queue_entry_id": str(self.queue_entry.id),
                    "intake_form_id": str(self.intake_form.id),
                    "created_by_user_id": str(self.doctor_user.id),
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(create_response.status_code, 201)
        medical_document_id = create_response.json()["medical_document_id"]

        template_response = self.client.post(
            "/api/v1/doctor-text-templates",
            data=json.dumps(
                {
                    "name": "Snapshot Template",
                    "template_locale": "de-DE",
                    "template_body": "Version A header.",
                    "is_global": False,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(template_response.status_code, 201)
        template_id = template_response.json()["id"]
        template_context = {
            "template_id": str(template_id),
            "template_name": "Snapshot Template",
            "template_locale": "de-DE",
        }
        summary_generated_text = "Version A header."

        draft_response = self.client.put(
            f"/api/v1/medical-documents/{medical_document_id}/draft",
            data=json.dumps(
                {
                    "medical_payload_schema_version": 1,
                    "medical_payload": {
                        "schema_version": 1,
                        "authoring_locale": "de-DE",
                        "lesions": [],
                        "examination_scope": ["INTIMATE_AREA_NOT_EXAMINED"],
                        "fitzpatrick_type": "TYPE_III",
                        "overall_image_assessment": "NO_CONTROL_NEEDED",
                        "recommendations": ["NO_SHORT_TERM_FOLLOWUP_REQUIRED"],
                        "final_assessment": "NO_HIGH_GRADE_SUSPICION",
                        "summary_generated_text": summary_generated_text,
                        "template_context": template_context,
                    },
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(draft_response.status_code, 200)

        publish_response = self.client.post(
            f"/api/v1/medical-documents/{medical_document_id}/publish",
            data=json.dumps(
                {
                    "publish_request_id": str(uuid4()),
                    "published_by_user_id": str(self.doctor_user.id),
                    "resend_sms": False,
                    "publish_locale": "de-DE",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(publish_response.status_code, 200)

        patch_template = self.client.patch(
            f"/api/v1/doctor-text-templates/{template_id}",
            data=json.dumps(
                {
                    "name": "Snapshot Template Changed",
                    "template_body": "Version B header.",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(patch_template.status_code, 200)

        versions = self.client.get(
            f"/api/v1/medical-documents/{medical_document_id}/versions"
        )
        self.assertEqual(versions.status_code, 200)
        published_version = versions.json()["items"][0]
        version_detail = self.client.get(
            f"/api/v1/medical-document-versions/{published_version['id']}"
        )
        self.assertEqual(version_detail.status_code, 200)
        payload = version_detail.json()["medical_payload"]
        self.assertIn("Version A header.", payload.get("summary_generated_text", ""))
        self.assertEqual(
            payload.get("template_context", {}).get("template_name"),
            "Snapshot Template",
        )

    def test_medical_document_versions_and_version_detail(self) -> None:
        create_response = self.client.post(
            "/api/v1/medical-documents",
            data=json.dumps(
                {
                    "queue_entry_id": str(self.queue_entry.id),
                    "intake_form_id": str(self.intake_form.id),
                    "created_by_user_id": str(self.doctor_user.id),
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(create_response.status_code, 201)
        medical_document_id = create_response.json()["medical_document_id"]

        versions_list = self.client.get(
            f"/api/v1/medical-documents/{medical_document_id}/versions"
        )
        self.assertEqual(versions_list.status_code, 200)
        self.assertEqual(versions_list.json()["items"], [])

        self.client.put(
            f"/api/v1/medical-documents/{medical_document_id}/draft",
            data=json.dumps(
                {
                    "updated_by_user_id": str(self.doctor_user.id),
                    "medical_payload_schema_version": 1,
                    "medical_payload": {
                        "schema_version": 1,
                        "authoring_locale": "de-DE",
                        "lesions": [],
                    },
                }
            ),
            content_type="application/json",
        )
        versions_list2 = self.client.get(
            f"/api/v1/medical-documents/{medical_document_id}/versions"
        )
        self.assertEqual(versions_list2.status_code, 200)
        items = versions_list2.json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["version_no"], 1)
        self.assertEqual(items[0]["version_status"], "DRAFT")
        version_id = items[0]["id"]

        version_detail = self.client.get(
            f"/api/v1/medical-document-versions/{version_id}"
        )
        self.assertEqual(version_detail.status_code, 200)
        v = version_detail.json()
        self.assertEqual(v["medical_document_id"], medical_document_id)
        self.assertEqual(v["version_no"], 1)
        self.assertEqual(v["medical_payload_schema_version"], 1)
        self.assertIn("lesions", v["medical_payload"])

        self.assertEqual(
            self.client.get(f"/api/v1/medical-document-versions/{uuid4()}").status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                f"/api/v1/medical-documents/{uuid4()}/versions"
            ).status_code,
            404,
        )

    def test_medical_document_draft_v1_validation_rejects_duplicate_lesion_numbers(
        self,
    ) -> None:
        create_response = self.client.post(
            "/api/v1/medical-documents",
            data=json.dumps(
                {
                    "queue_entry_id": str(self.queue_entry.id),
                    "intake_form_id": str(self.intake_form.id),
                    "created_by_user_id": str(self.doctor_user.id),
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(create_response.status_code, 201)
        medical_document_id = create_response.json()["medical_document_id"]
        r = self.client.put(
            f"/api/v1/medical-documents/{medical_document_id}/draft",
            data=json.dumps(
                {
                    "medical_payload_schema_version": 1,
                    "medical_payload": {
                        "schema_version": 1,
                        "lesions": [
                            {
                                "lesion_numbers": [2, 3, 2],
                                "clinical_assessment": "CONTROL_NEEDED",
                                "malignancy_risk": "NO_SUSPICION",
                            }
                        ],
                    },
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn("details", r.json())

    def test_medical_document_draft_v1_validation_rejects_control_needed_without_lesions(
        self,
    ) -> None:
        create_response = self.client.post(
            "/api/v1/medical-documents",
            data=json.dumps(
                {
                    "queue_entry_id": str(self.queue_entry.id),
                    "intake_form_id": str(self.intake_form.id),
                    "created_by_user_id": str(self.doctor_user.id),
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(create_response.status_code, 201)
        medical_document_id = create_response.json()["medical_document_id"]
        r = self.client.put(
            f"/api/v1/medical-documents/{medical_document_id}/draft",
            data=json.dumps(
                {
                    "medical_payload_schema_version": 1,
                    "medical_payload": {
                        "schema_version": 1,
                        "overall_image_assessment": "CONTROL_NEEDED",
                        "lesions": [],
                    },
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn("details", r.json())

    def test_medical_document_draft_preserves_full_v1_payload(self) -> None:
        """Draft with full medical_payload v1: roundtrip via MedicalPayloadMinimal + validate_medical_payload_v1 preserves all fields."""
        create_response = self.client.post(
            "/api/v1/medical-documents",
            data=json.dumps(
                {
                    "queue_entry_id": str(self.queue_entry.id),
                    "intake_form_id": str(self.intake_form.id),
                    "created_by_user_id": str(self.doctor_user.id),
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(create_response.status_code, 201)
        medical_document_id = create_response.json()["medical_document_id"]
        full_payload = {
            "schema_version": 1,
            "authoring_locale": "de-DE",
            "examination_scope": ["INTIMATE_AREA_NOT_EXAMINED"],
            "fitzpatrick_type": "TYPE_III",
            "overall_image_assessment": "NO_CONTROL_NEEDED",
            "recommendations": ["FOLLOWUP_3_MONTHS"],
            "final_assessment": "NO_HIGH_GRADE_SUSPICION",
            "lesions": [
                {
                    "lesion_numbers": [5],
                    "dermatoscopic_features": ["ASYMMETRY"],
                    "clinical_assessment": "CONTROL_NEEDED",
                    "malignancy_risk": "NO_SUSPICION",
                    "edited_text": "Befundtext Läsion 5",
                }
            ],
            "summary_edited_text": "Zusammenfassung Befund",
            "template_context": {
                "template_id": None,
                "template_name": "Test",
                "template_locale": "de-DE",
            },
        }
        draft_response = self.client.put(
            f"/api/v1/medical-documents/{medical_document_id}/draft",
            data=json.dumps(
                {
                    "medical_payload_schema_version": 1,
                    "medical_payload": full_payload,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(draft_response.status_code, 200)
        version_id = draft_response.json()["medical_document_version_id"]
        version_detail = self.client.get(
            f"/api/v1/medical-document-versions/{version_id}"
        )
        self.assertEqual(version_detail.status_code, 200)
        saved = version_detail.json()["medical_payload"]
        self.assertEqual(saved["schema_version"], 1)
        self.assertEqual(saved["authoring_locale"], "de-DE")
        self.assertEqual(saved["examination_scope"], ["INTIMATE_AREA_NOT_EXAMINED"])
        self.assertEqual(saved["fitzpatrick_type"], "TYPE_III")
        self.assertEqual(saved["overall_image_assessment"], "NO_CONTROL_NEEDED")
        self.assertEqual(len(saved["lesions"]), 1)
        self.assertEqual(saved["lesions"][0]["lesion_numbers"], [5])
        self.assertEqual(saved["lesions"][0]["edited_text"], "Befundtext Läsion 5")
        self.assertEqual(saved["summary_edited_text"], "Zusammenfassung Befund")
        self.assertIsNotNone(saved.get("template_context"))

    def test_publish_accepts_resend_sms(self) -> None:
        create_response = self.client.post(
            "/api/v1/medical-documents",
            data=json.dumps(
                {
                    "queue_entry_id": str(self.queue_entry.id),
                    "intake_form_id": str(self.intake_form.id),
                    "created_by_user_id": str(self.doctor_user.id),
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(create_response.status_code, 201)
        medical_document_id = create_response.json()["medical_document_id"]
        self.client.put(
            f"/api/v1/medical-documents/{medical_document_id}/draft",
            data=json.dumps(
                {
                    "medical_payload_schema_version": 1,
                    "medical_payload": {
                        "schema_version": 1,
                        "authoring_locale": "de-DE",
                        "lesions": [],
                        "examination_scope": ["INTIMATE_AREA_NOT_EXAMINED"],
                        "fitzpatrick_type": "TYPE_III",
                        "overall_image_assessment": "NO_CONTROL_NEEDED",
                        "recommendations": ["NO_SHORT_TERM_FOLLOWUP_REQUIRED"],
                        "final_assessment": "NO_HIGH_GRADE_SUSPICION",
                    },
                }
            ),
            content_type="application/json",
        )
        publish_response = self.client.post(
            f"/api/v1/medical-documents/{medical_document_id}/publish",
            data=json.dumps(
                {
                    "publish_request_id": str(uuid4()),
                    "published_by_user_id": str(self.doctor_user.id),
                    "resend_sms": True,
                    "publish_locale": "de-DE",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(publish_response.status_code, 200)

    def test_publish_without_draft_returns_400(self) -> None:
        """Publish without prior 'Zapisz szkic' returns 400; full validation via draft is required."""
        create_response = self.client.post(
            "/api/v1/medical-documents",
            data=json.dumps(
                {
                    "queue_entry_id": str(self.queue_entry.id),
                    "intake_form_id": str(self.intake_form.id),
                    "created_by_user_id": str(self.doctor_user.id),
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(create_response.status_code, 201)
        medical_document_id = create_response.json()["medical_document_id"]
        # Do NOT save draft; publish directly
        publish_response = self.client.post(
            f"/api/v1/medical-documents/{medical_document_id}/publish",
            data=json.dumps(
                {
                    "publish_request_id": str(uuid4()),
                    "published_by_user_id": str(self.doctor_user.id),
                    "publish_locale": "de-DE",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(publish_response.status_code, 400)
        err = publish_response.json().get("error", "")
        self.assertTrue(
            "draft" in err.lower()
            or "entwurf" in err.lower()
            or "szkic" in err.lower(),
            f"Expected draft-related publish error, got: {err!r}",
        )

    def test_publish_with_incomplete_draft_returns_400(self) -> None:
        """Draft bez wypełnionego Untersuchungsumfang lub Fitzpatrick nie może być opublikowany."""
        create_response = self.client.post(
            "/api/v1/medical-documents",
            data=json.dumps(
                {
                    "queue_entry_id": str(self.queue_entry.id),
                    "intake_form_id": str(self.intake_form.id),
                    "created_by_user_id": str(self.doctor_user.id),
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(create_response.status_code, 201)
        medical_document_id = create_response.json()["medical_document_id"]
        self.client.put(
            f"/api/v1/medical-documents/{medical_document_id}/draft",
            data=json.dumps(
                {
                    "updated_by_user_id": str(self.doctor_user.id),
                    "medical_payload_schema_version": 1,
                    "medical_payload": {
                        "schema_version": 1,
                        "authoring_locale": "de-DE",
                        "lesions": [],
                    },
                }
            ),
            content_type="application/json",
        )
        publish_response = self.client.post(
            f"/api/v1/medical-documents/{medical_document_id}/publish",
            data=json.dumps(
                {
                    "publish_request_id": str(uuid4()),
                    "published_by_user_id": str(self.doctor_user.id),
                    "publish_locale": "de-DE",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(publish_response.status_code, 400)
        error_msg = publish_response.json().get("error", "")
        # Komunikat w języku publish_locale (lub fallback EN); w teście bez seed tłumaczeń = angielski fallback
        self.assertTrue(
            "Before publishing" in error_msg
            or "Untersuchungsumfang" in error_msg
            or "Przed publikacją" in error_msg,
            f"Expected validation message in error, got: {error_msg!r}",
        )

    def test_publish_missing_publish_locale_returns_400(self) -> None:
        create_response = self.client.post(
            "/api/v1/medical-documents",
            data=json.dumps(
                {
                    "queue_entry_id": str(self.queue_entry.id),
                    "intake_form_id": str(self.intake_form.id),
                    "created_by_user_id": str(self.doctor_user.id),
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(create_response.status_code, 201)
        medical_document_id = create_response.json()["medical_document_id"]
        self.client.put(
            f"/api/v1/medical-documents/{medical_document_id}/draft",
            data=json.dumps(
                {
                    "medical_payload_schema_version": 1,
                    "medical_payload": {
                        "schema_version": 1,
                        "authoring_locale": "de-DE",
                        "overall_image_assessment": "NO_CONTROL_NEEDED",
                        "lesions": [],
                    },
                }
            ),
            content_type="application/json",
        )
        publish_response = self.client.post(
            f"/api/v1/medical-documents/{medical_document_id}/publish",
            data=json.dumps(
                {
                    "publish_request_id": str(uuid4()),
                    "published_by_user_id": str(self.doctor_user.id),
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(publish_response.status_code, 400)
        self.assertEqual(
            publish_response.json().get("error_key"),
            "other.api.invalid_request_body",
        )

    def test_publish_same_request_id_with_different_locale_returns_409(self) -> None:
        create_response = self.client.post(
            "/api/v1/medical-documents",
            data=json.dumps(
                {
                    "queue_entry_id": str(self.queue_entry.id),
                    "intake_form_id": str(self.intake_form.id),
                    "created_by_user_id": str(self.doctor_user.id),
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(create_response.status_code, 201)
        medical_document_id = create_response.json()["medical_document_id"]

        draft_response = self.client.put(
            f"/api/v1/medical-documents/{medical_document_id}/draft",
            data=json.dumps(
                {
                    "medical_payload_schema_version": 1,
                    "medical_payload": {
                        "schema_version": 1,
                        "authoring_locale": "de-DE",
                        "lesions": [],
                        "examination_scope": ["INTIMATE_AREA_NOT_EXAMINED"],
                        "fitzpatrick_type": "TYPE_III",
                        "overall_image_assessment": "NO_CONTROL_NEEDED",
                        "recommendations": ["NO_SHORT_TERM_FOLLOWUP_REQUIRED"],
                        "final_assessment": "NO_HIGH_GRADE_SUSPICION",
                    },
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(draft_response.status_code, 200)

        request_id = str(uuid4())
        first_publish = self.client.post(
            f"/api/v1/medical-documents/{medical_document_id}/publish",
            data=json.dumps(
                {
                    "publish_request_id": request_id,
                    "published_by_user_id": str(self.doctor_user.id),
                    "publish_locale": "de-DE",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(first_publish.status_code, 200)

        second_publish = self.client.post(
            f"/api/v1/medical-documents/{medical_document_id}/publish",
            data=json.dumps(
                {
                    "publish_request_id": request_id,
                    "published_by_user_id": str(self.doctor_user.id),
                    "publish_locale": "en-GB",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(second_publish.status_code, 409)
        err = (second_publish.json().get("error") or "").lower()
        self.assertIn("publish_locale", err)
        self.assertTrue(
            "different" in err or "anderem" in err or "inny" in err or "other" in err,
            f"Expected locale conflict wording, got: {second_publish.json().get('error')!r}",
        )

    def test_medical_document_endpoints_return_404_for_missing_resources(self) -> None:
        missing_doc_id = uuid4()

        create_missing_dependencies = self.client.post(
            "/api/v1/medical-documents",
            data=json.dumps(
                {
                    "queue_entry_id": str(uuid4()),
                    "intake_form_id": str(self.intake_form.id),
                    "created_by_user_id": str(self.doctor_user.id),
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(create_missing_dependencies.status_code, 404)

        draft_missing_doc = self.client.put(
            f"/api/v1/medical-documents/{missing_doc_id}/draft",
            data=json.dumps(
                {
                    "updated_by_user_id": str(self.doctor_user.id),
                    "medical_payload_schema_version": 1,
                    "medical_payload": {"schema_version": 1},
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(draft_missing_doc.status_code, 404)

        publish_missing_doc = self.client.post(
            f"/api/v1/medical-documents/{missing_doc_id}/publish",
            data=json.dumps(
                {
                    "publish_request_id": str(uuid4()),
                    "published_by_user_id": str(self.doctor_user.id),
                    "publish_locale": "de-DE",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(publish_missing_doc.status_code, 404)

    def test_retry_processing_endpoint_allows_admin_and_rejects_doctor(self) -> None:
        create_response = self.client.post(
            "/api/v1/medical-documents",
            data=json.dumps(
                {
                    "queue_entry_id": str(self.queue_entry.id),
                    "intake_form_id": str(self.intake_form.id),
                    "created_by_user_id": str(self.doctor_user.id),
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(create_response.status_code, 201)
        medical_document_id = create_response.json()["medical_document_id"]
        self.client.put(
            f"/api/v1/medical-documents/{medical_document_id}/draft",
            data=json.dumps(
                {
                    "medical_payload_schema_version": 1,
                    "medical_payload": {
                        "schema_version": 1,
                        "authoring_locale": "de-DE",
                        "lesions": [],
                        "examination_scope": ["INTIMATE_AREA_NOT_EXAMINED"],
                        "fitzpatrick_type": "TYPE_III",
                        "overall_image_assessment": "NO_CONTROL_NEEDED",
                        "recommendations": ["NO_SHORT_TERM_FOLLOWUP_REQUIRED"],
                        "final_assessment": "NO_HIGH_GRADE_SUSPICION",
                    },
                }
            ),
            content_type="application/json",
        )
        publish_response = self.client.post(
            f"/api/v1/medical-documents/{medical_document_id}/publish",
            data=json.dumps(
                {"publish_request_id": str(uuid4()), "publish_locale": "de-DE"}
            ),
            content_type="application/json",
        )
        self.assertEqual(publish_response.status_code, 200)
        version_id = publish_response.json()["medical_document_version_id"]
        event = OutboxEvent.objects.get(
            medical_document_version_id=version_id,
            event_type=OutboxEventType.GENERATE_PDF,
        )
        event.status = OutboxStatus.FAILED
        event.error_message = "Simulated failure."
        event.save(update_fields=["status", "error_message", "updated_at"])

        doctor_retry = self.client.post(
            f"/api/v1/medical-documents/{medical_document_id}/retry-processing",
            data=json.dumps({"reason": "retry"}),
            content_type="application/json",
        )
        self.assertEqual(doctor_retry.status_code, 403)

        self.client.force_login(self.admin_user)
        admin_retry = self.client.post(
            f"/api/v1/medical-documents/{medical_document_id}/retry-processing",
            data=json.dumps({"reason": "manual retry"}),
            content_type="application/json",
        )
        self.assertEqual(admin_retry.status_code, 200)
        event.refresh_from_db()
        self.assertEqual(event.status, OutboxStatus.PENDING)

    def test_medical_endpoints_require_authentication(self) -> None:
        self.client.logout()
        response = self.client.post(
            "/api/v1/medical-documents",
            data=json.dumps(
                {
                    "queue_entry_id": str(self.queue_entry.id),
                    "intake_form_id": str(self.intake_form.id),
                    "created_by_user_id": str(self.doctor_user.id),
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)

    def test_draft_423_when_locked_by_other_doctor_unlock_releases(self) -> None:
        other = StaffUser.objects.create_user(
            username="api-doc-lock-2",
            email="api.doc.lock2@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(other, "Doctor")

        create_response = self.client.post(
            "/api/v1/medical-documents",
            data=json.dumps(
                {
                    "queue_entry_id": str(self.queue_entry.id),
                    "intake_form_id": str(self.intake_form.id),
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(create_response.status_code, 201)
        mid = create_response.json()["medical_document_id"]

        dq = self.queue_entry.daily_queue
        dq.assigned_doctor = other
        dq.save(update_fields=["assigned_doctor", "updated_at"])

        MedicalDocument.objects.filter(id=mid).update(
            locked_by_user_id=self.doctor_user.id,
            locked_at=timezone.now(),
        )

        draft_body = {
            "medical_payload_schema_version": 1,
            "medical_payload": {
                "schema_version": 1,
                "authoring_locale": "de-DE",
                "lesions": [],
                "examination_scope": ["INTIMATE_AREA_NOT_EXAMINED"],
                "fitzpatrick_type": "TYPE_III",
                "overall_image_assessment": "NO_CONTROL_NEEDED",
                "recommendations": ["NO_SHORT_TERM_FOLLOWUP_REQUIRED"],
                "final_assessment": "NO_HIGH_GRADE_SUSPICION",
            },
        }

        self.client.force_login(other)
        blocked = self.client.put(
            f"/api/v1/medical-documents/{mid}/draft",
            data=json.dumps(draft_body),
            content_type="application/json",
        )
        self.assertEqual(blocked.status_code, 423)
        self.assertIn("locked_by_username", blocked.json())

        self.client.force_login(self.doctor_user)
        unlocked = self.client.post(
            f"/api/v1/medical-documents/{mid}/unlock",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(unlocked.status_code, 200)
        self.assertTrue(unlocked.json().get("released"))

        self.client.force_login(other)
        ok = self.client.put(
            f"/api/v1/medical-documents/{mid}/draft",
            data=json.dumps(draft_body),
            content_type="application/json",
        )
        self.assertEqual(ok.status_code, 200)

    def test_draft_manager_bypasses_lock_when_other_doctor_blocked(self) -> None:
        other = StaffUser.objects.create_user(
            username="api-doc-lock-mgr",
            email="api.doc.lock.mgr@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(other, "Doctor")
        manager = StaffUser.objects.create_user(
            username="api-manager-draft-lock",
            email="api.manager.draft@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(manager, "Manager")
        site = self.queue_entry.daily_queue.clinic_site
        manager.clinic_sites.add(site)

        self.client.force_login(self.doctor_user)
        create_response = self.client.post(
            "/api/v1/medical-documents",
            data=json.dumps(
                {
                    "queue_entry_id": str(self.queue_entry.id),
                    "intake_form_id": str(self.intake_form.id),
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(create_response.status_code, 201)
        mid = create_response.json()["medical_document_id"]

        dq = self.queue_entry.daily_queue
        dq.assigned_doctor = other
        dq.save(update_fields=["assigned_doctor", "updated_at"])

        MedicalDocument.objects.filter(id=mid).update(
            locked_by_user_id=self.doctor_user.id,
            locked_at=timezone.now(),
        )

        draft_body = {
            "medical_payload_schema_version": 1,
            "medical_payload": {
                "schema_version": 1,
                "authoring_locale": "de-DE",
                "lesions": [],
                "examination_scope": ["INTIMATE_AREA_NOT_EXAMINED"],
                "fitzpatrick_type": "TYPE_III",
                "overall_image_assessment": "NO_CONTROL_NEEDED",
                "recommendations": ["NO_SHORT_TERM_FOLLOWUP_REQUIRED"],
                "final_assessment": "NO_HIGH_GRADE_SUSPICION",
            },
        }

        self.client.force_login(other)
        blocked = self.client.put(
            f"/api/v1/medical-documents/{mid}/draft",
            data=json.dumps(draft_body),
            content_type="application/json",
        )
        self.assertEqual(blocked.status_code, 423)

        self.client.force_login(manager)
        ok = self.client.put(
            f"/api/v1/medical-documents/{mid}/draft",
            data=json.dumps(draft_body),
            content_type="application/json",
        )
        self.assertEqual(ok.status_code, 200)

    def test_publish_423_when_locked_by_other_doctor(self) -> None:
        other = StaffUser.objects.create_user(
            username="api-doc-pub-lock",
            email="api.doc.pub.lock@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(other, "Doctor")

        create_response = self.client.post(
            "/api/v1/medical-documents",
            data=json.dumps(
                {
                    "queue_entry_id": str(self.queue_entry.id),
                    "intake_form_id": str(self.intake_form.id),
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(create_response.status_code, 201)
        mid = create_response.json()["medical_document_id"]

        draft_body = {
            "medical_payload_schema_version": 1,
            "medical_payload": {
                "schema_version": 1,
                "authoring_locale": "de-DE",
                "lesions": [],
                "examination_scope": ["INTIMATE_AREA_NOT_EXAMINED"],
                "fitzpatrick_type": "TYPE_III",
                "overall_image_assessment": "NO_CONTROL_NEEDED",
                "recommendations": ["NO_SHORT_TERM_FOLLOWUP_REQUIRED"],
                "final_assessment": "NO_HIGH_GRADE_SUSPICION",
            },
        }
        self.client.put(
            f"/api/v1/medical-documents/{mid}/draft",
            data=json.dumps(draft_body),
            content_type="application/json",
        )

        dq = self.queue_entry.daily_queue
        dq.assigned_doctor = other
        dq.save(update_fields=["assigned_doctor", "updated_at"])

        MedicalDocument.objects.filter(id=mid).update(
            locked_by_user_id=self.doctor_user.id,
            locked_at=timezone.now(),
        )

        self.client.force_login(other)
        publish_response = self.client.post(
            f"/api/v1/medical-documents/{mid}/publish",
            data=json.dumps(
                {
                    "publish_request_id": str(uuid4()),
                    "publish_locale": "de-DE",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(publish_response.status_code, 423)
        self.assertIn("locked_by_username", publish_response.json())

        doc = MedicalDocument.objects.get(id=mid)
        self.assertEqual(doc.status, MedicalDocStatus.DRAFT)
        self.assertEqual(doc.locked_by_user_id, self.doctor_user.id)

    def test_publish_succeeds_for_lock_holder(self) -> None:
        create_response = self.client.post(
            "/api/v1/medical-documents",
            data=json.dumps(
                {
                    "queue_entry_id": str(self.queue_entry.id),
                    "intake_form_id": str(self.intake_form.id),
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(create_response.status_code, 201)
        mid = create_response.json()["medical_document_id"]

        draft_body = {
            "medical_payload_schema_version": 1,
            "medical_payload": {
                "schema_version": 1,
                "authoring_locale": "de-DE",
                "lesions": [],
                "examination_scope": ["INTIMATE_AREA_NOT_EXAMINED"],
                "fitzpatrick_type": "TYPE_III",
                "overall_image_assessment": "NO_CONTROL_NEEDED",
                "recommendations": ["NO_SHORT_TERM_FOLLOWUP_REQUIRED"],
                "final_assessment": "NO_HIGH_GRADE_SUSPICION",
            },
        }
        self.client.put(
            f"/api/v1/medical-documents/{mid}/draft",
            data=json.dumps(draft_body),
            content_type="application/json",
        )

        MedicalDocument.objects.filter(id=mid).update(
            locked_by_user_id=self.doctor_user.id,
            locked_at=timezone.now(),
        )

        publish_response = self.client.post(
            f"/api/v1/medical-documents/{mid}/publish",
            data=json.dumps(
                {
                    "publish_request_id": str(uuid4()),
                    "publish_locale": "de-DE",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(publish_response.status_code, 200)
        self.assertEqual(publish_response.json()["version_status"], "PUBLISHED")

        doc = MedicalDocument.objects.get(id=mid)
        self.assertEqual(doc.status, MedicalDocStatus.PUBLISHED)
        self.assertIsNone(doc.locked_by_user_id)
        self.assertIsNone(doc.locked_at)

    def test_unlock_returns_403_when_non_holder_non_admin(self) -> None:
        other = StaffUser.objects.create_user(
            username="api-doc-unlock-403",
            email="api.doc.unlock403@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(other, "Doctor")
        create_resp = self.client.post(
            "/api/v1/medical-documents",
            data=json.dumps(
                {
                    "queue_entry_id": str(self.queue_entry.id),
                    "intake_form_id": str(self.intake_form.id),
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(create_resp.status_code, 201)
        mid = create_resp.json()["medical_document_id"]
        MedicalDocument.objects.filter(id=mid).update(
            locked_by_user_id=self.doctor_user.id,
            locked_at=timezone.now(),
        )
        self.client.force_login(other)
        resp = self.client.post(
            f"/api/v1/medical-documents/{mid}/unlock",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(resp.json()["released"])
        self.assertIn("error", resp.json())

    def test_unlock_returns_404_for_missing_document(self) -> None:
        resp = self.client.post(
            f"/api/v1/medical-documents/{uuid4()}/unlock",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 404)

    def test_unlock_returns_405_for_get(self) -> None:
        create_resp = self.client.post(
            "/api/v1/medical-documents",
            data=json.dumps(
                {
                    "queue_entry_id": str(self.queue_entry.id),
                    "intake_form_id": str(self.intake_form.id),
                }
            ),
            content_type="application/json",
        )
        mid = create_resp.json()["medical_document_id"]
        resp = self.client.get(f"/api/v1/medical-documents/{mid}/unlock")
        self.assertEqual(resp.status_code, 405)

    def test_unlock_returns_403_for_reception_role(self) -> None:
        create_resp = self.client.post(
            "/api/v1/medical-documents",
            data=json.dumps(
                {
                    "queue_entry_id": str(self.queue_entry.id),
                    "intake_form_id": str(self.intake_form.id),
                }
            ),
            content_type="application/json",
        )
        mid = create_resp.json()["medical_document_id"]
        self.client.force_login(self.reception_user)
        resp = self.client.post(
            f"/api/v1/medical-documents/{mid}/unlock",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 403)
        self.assertIn("error", resp.json())

    def test_unlock_returns_404_when_release_raises_not_found(self) -> None:
        create_resp = self.client.post(
            "/api/v1/medical-documents",
            data=json.dumps(
                {
                    "queue_entry_id": str(self.queue_entry.id),
                    "intake_form_id": str(self.intake_form.id),
                }
            ),
            content_type="application/json",
        )
        mid = create_resp.json()["medical_document_id"]
        with patch(
            "apps.medical.api_views.release_document_lock",
            side_effect=ObjectDoesNotExist(),
        ):
            resp = self.client.post(
                f"/api/v1/medical-documents/{mid}/unlock",
                data=json.dumps({}),
                content_type="application/json",
            )
        self.assertEqual(resp.status_code, 404)
        self.assertIn("error", resp.json())

    def test_admin_can_override_lock_on_draft_save(self) -> None:
        create_resp = self.client.post(
            "/api/v1/medical-documents",
            data=json.dumps(
                {
                    "queue_entry_id": str(self.queue_entry.id),
                    "intake_form_id": str(self.intake_form.id),
                }
            ),
            content_type="application/json",
        )
        mid = create_resp.json()["medical_document_id"]
        MedicalDocument.objects.filter(id=mid).update(
            locked_by_user_id=self.doctor_user.id,
            locked_at=timezone.now(),
        )
        self.client.force_login(self.admin_user)
        draft_body = {
            "medical_payload_schema_version": 1,
            "medical_payload": {
                "schema_version": 1,
                "authoring_locale": "de-DE",
                "lesions": [],
                "examination_scope": ["INTIMATE_AREA_NOT_EXAMINED"],
                "fitzpatrick_type": "TYPE_III",
                "overall_image_assessment": "NO_CONTROL_NEEDED",
                "recommendations": ["NO_SHORT_TERM_FOLLOWUP_REQUIRED"],
                "final_assessment": "NO_HIGH_GRADE_SUSPICION",
            },
        }
        resp = self.client.put(
            f"/api/v1/medical-documents/{mid}/draft",
            data=json.dumps(draft_body),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)

    def test_admin_can_override_lock_on_publish(self) -> None:
        create_resp = self.client.post(
            "/api/v1/medical-documents",
            data=json.dumps(
                {
                    "queue_entry_id": str(self.queue_entry.id),
                    "intake_form_id": str(self.intake_form.id),
                }
            ),
            content_type="application/json",
        )
        mid = create_resp.json()["medical_document_id"]
        draft_body = {
            "medical_payload_schema_version": 1,
            "medical_payload": {
                "schema_version": 1,
                "authoring_locale": "de-DE",
                "lesions": [],
                "examination_scope": ["INTIMATE_AREA_NOT_EXAMINED"],
                "fitzpatrick_type": "TYPE_III",
                "overall_image_assessment": "NO_CONTROL_NEEDED",
                "recommendations": ["NO_SHORT_TERM_FOLLOWUP_REQUIRED"],
                "final_assessment": "NO_HIGH_GRADE_SUSPICION",
            },
        }
        self.client.put(
            f"/api/v1/medical-documents/{mid}/draft",
            data=json.dumps(draft_body),
            content_type="application/json",
        )
        MedicalDocument.objects.filter(id=mid).update(
            locked_by_user_id=self.doctor_user.id,
            locked_at=timezone.now(),
        )
        self.client.force_login(self.admin_user)
        resp = self.client.post(
            f"/api/v1/medical-documents/{mid}/publish",
            data=json.dumps(
                {"publish_request_id": str(uuid4()), "publish_locale": "de-DE"}
            ),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["version_status"], "PUBLISHED")

    def test_admin_can_unlock_another_users_lock(self) -> None:
        create_resp = self.client.post(
            "/api/v1/medical-documents",
            data=json.dumps(
                {
                    "queue_entry_id": str(self.queue_entry.id),
                    "intake_form_id": str(self.intake_form.id),
                }
            ),
            content_type="application/json",
        )
        mid = create_resp.json()["medical_document_id"]
        MedicalDocument.objects.filter(id=mid).update(
            locked_by_user_id=self.doctor_user.id,
            locked_at=timezone.now(),
        )
        self.client.force_login(self.admin_user)
        resp = self.client.post(
            f"/api/v1/medical-documents/{mid}/unlock",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["released"])

    def test_list_includes_lock_fields(self) -> None:
        self.client.post(
            "/api/v1/medical-documents",
            data=json.dumps(
                {
                    "queue_entry_id": str(self.queue_entry.id),
                    "intake_form_id": str(self.intake_form.id),
                }
            ),
            content_type="application/json",
        )
        resp = self.client.get("/api/v1/medical-documents")
        self.assertEqual(resp.status_code, 200)
        item = resp.json()["items"][0]
        self.assertIn("locked_by_username", item)
        self.assertIn("locked_at", item)
        self.assertIsNone(item["locked_by_username"])

    def test_list_shows_active_lock(self) -> None:
        create_resp = self.client.post(
            "/api/v1/medical-documents",
            data=json.dumps(
                {
                    "queue_entry_id": str(self.queue_entry.id),
                    "intake_form_id": str(self.intake_form.id),
                }
            ),
            content_type="application/json",
        )
        mid = create_resp.json()["medical_document_id"]
        MedicalDocument.objects.filter(id=mid).update(
            locked_by_user_id=self.doctor_user.id,
            locked_at=timezone.now(),
        )
        resp = self.client.get("/api/v1/medical-documents")
        self.assertEqual(resp.status_code, 200)
        item = resp.json()["items"][0]
        self.assertIsNotNone(item["locked_by_username"])
        self.assertIsNotNone(item["locked_at"])

    def test_detail_includes_lock_fields(self) -> None:
        create_resp = self.client.post(
            "/api/v1/medical-documents",
            data=json.dumps(
                {
                    "queue_entry_id": str(self.queue_entry.id),
                    "intake_form_id": str(self.intake_form.id),
                }
            ),
            content_type="application/json",
        )
        mid = create_resp.json()["medical_document_id"]
        detail = self.client.get(f"/api/v1/medical-documents/{mid}")
        self.assertEqual(detail.status_code, 200)
        data = detail.json()
        self.assertIn("locked_by_user_id", data)
        self.assertIn("locked_by_username", data)
        self.assertIn("locked_at", data)
        self.assertIsNone(data["locked_by_user_id"])

    def test_unlock_on_already_unlocked_document(self) -> None:
        create_resp = self.client.post(
            "/api/v1/medical-documents",
            data=json.dumps(
                {
                    "queue_entry_id": str(self.queue_entry.id),
                    "intake_form_id": str(self.intake_form.id),
                }
            ),
            content_type="application/json",
        )
        mid = create_resp.json()["medical_document_id"]
        resp = self.client.post(
            f"/api/v1/medical-documents/{mid}/unlock",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["released"])

    def test_draft_save_by_lock_holder_succeeds_and_refreshes(self) -> None:
        create_resp = self.client.post(
            "/api/v1/medical-documents",
            data=json.dumps(
                {
                    "queue_entry_id": str(self.queue_entry.id),
                    "intake_form_id": str(self.intake_form.id),
                }
            ),
            content_type="application/json",
        )
        mid = create_resp.json()["medical_document_id"]
        lock_time = timezone.now() - timedelta(minutes=30)
        MedicalDocument.objects.filter(id=mid).update(
            locked_by_user_id=self.doctor_user.id,
            locked_at=lock_time,
        )
        draft_body = {
            "medical_payload_schema_version": 1,
            "medical_payload": {
                "schema_version": 1,
                "authoring_locale": "de-DE",
                "lesions": [],
                "examination_scope": ["INTIMATE_AREA_NOT_EXAMINED"],
                "fitzpatrick_type": "TYPE_III",
                "overall_image_assessment": "NO_CONTROL_NEEDED",
                "recommendations": ["NO_SHORT_TERM_FOLLOWUP_REQUIRED"],
                "final_assessment": "NO_HIGH_GRADE_SUSPICION",
            },
        }
        resp = self.client.put(
            f"/api/v1/medical-documents/{mid}/draft",
            data=json.dumps(draft_body),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        doc = MedicalDocument.objects.get(id=mid)
        self.assertEqual(doc.locked_by_user_id, self.doctor_user.id)
        self.assertGreater(doc.locked_at, lock_time)

    def test_non_assigned_doctor_can_access_draft_document(self) -> None:
        other = StaffUser.objects.create_user(
            username="api-doc-shared-access",
            email="api.doc.shared@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(other, "Doctor")
        create_resp = self.client.post(
            "/api/v1/medical-documents",
            data=json.dumps(
                {
                    "queue_entry_id": str(self.queue_entry.id),
                    "intake_form_id": str(self.intake_form.id),
                }
            ),
            content_type="application/json",
        )
        mid = create_resp.json()["medical_document_id"]
        dq = self.queue_entry.daily_queue
        dq.assigned_doctor = None
        dq.save(update_fields=["assigned_doctor", "updated_at"])
        self.client.force_login(other)
        detail = self.client.get(f"/api/v1/medical-documents/{mid}")
        self.assertEqual(detail.status_code, 200)

    def test_non_assigned_doctor_cannot_access_published_document(self) -> None:
        other = StaffUser.objects.create_user(
            username="api-doc-no-pub",
            email="api.doc.nopub@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(other, "Doctor")
        create_resp = self.client.post(
            "/api/v1/medical-documents",
            data=json.dumps(
                {
                    "queue_entry_id": str(self.queue_entry.id),
                    "intake_form_id": str(self.intake_form.id),
                }
            ),
            content_type="application/json",
        )
        mid = create_resp.json()["medical_document_id"]
        draft_body = {
            "medical_payload_schema_version": 1,
            "medical_payload": {
                "schema_version": 1,
                "authoring_locale": "de-DE",
                "lesions": [],
                "examination_scope": ["INTIMATE_AREA_NOT_EXAMINED"],
                "fitzpatrick_type": "TYPE_III",
                "overall_image_assessment": "NO_CONTROL_NEEDED",
                "recommendations": ["NO_SHORT_TERM_FOLLOWUP_REQUIRED"],
                "final_assessment": "NO_HIGH_GRADE_SUSPICION",
            },
        }
        self.client.put(
            f"/api/v1/medical-documents/{mid}/draft",
            data=json.dumps(draft_body),
            content_type="application/json",
        )
        self.client.post(
            f"/api/v1/medical-documents/{mid}/publish",
            data=json.dumps(
                {"publish_request_id": str(uuid4()), "publish_locale": "de-DE"}
            ),
            content_type="application/json",
        )
        dq = self.queue_entry.daily_queue
        dq.assigned_doctor = None
        dq.save(update_fields=["assigned_doctor", "updated_at"])
        self.client.force_login(other)
        detail = self.client.get(f"/api/v1/medical-documents/{mid}")
        self.assertEqual(detail.status_code, 404)


class MedicalDocumentRevisionApiTests(MedicalApiTests):

    VALID_PAYLOAD = {
        "schema_version": 1,
        "authoring_locale": "de-DE",
        "examination_scope": ["INTIMATE_AREA_NOT_EXAMINED"],
        "fitzpatrick_type": "TYPE_III",
        "overall_image_assessment": "NO_CONTROL_NEEDED",
        "recommendations": ["NO_SHORT_TERM_FOLLOWUP_REQUIRED"],
        "final_assessment": "NO_HIGH_GRADE_SUSPICION",
    }

    def _create_published_document(self) -> str:
        self.client.force_login(self.doctor_user)
        create_response = self.client.post(
            "/api/v1/medical-documents",
            data=json.dumps(
                {
                    "queue_entry_id": str(self.queue_entry.id),
                    "intake_form_id": str(self.intake_form.id),
                    "created_by_user_id": str(self.doctor_user.id),
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(create_response.status_code, 201)
        medical_document_id = create_response.json()["medical_document_id"]
        draft_response = self.client.put(
            f"/api/v1/medical-documents/{medical_document_id}/draft",
            data=json.dumps(
                {
                    "medical_payload_schema_version": 1,
                    "medical_payload": self.VALID_PAYLOAD,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(draft_response.status_code, 200)
        publish_response = self.client.post(
            f"/api/v1/medical-documents/{medical_document_id}/publish",
            data=json.dumps(
                {
                    "publish_request_id": str(uuid4()),
                    "publish_locale": "de-DE",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(publish_response.status_code, 200)
        return medical_document_id

    def test_draft_on_published_without_intent_returns_409(self) -> None:
        medical_document_id = self._create_published_document()
        response = self.client.put(
            f"/api/v1/medical-documents/{medical_document_id}/draft",
            data=json.dumps(
                {
                    "medical_payload_schema_version": 1,
                    "medical_payload": self.VALID_PAYLOAD,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 409)
        body = response.json()
        self.assertEqual(
            body.get("error_key") or body.get("api_message_key"),
            "other.api.amend_intent_required",
        )
        doc = MedicalDocument.objects.get(id=medical_document_id)
        self.assertEqual(doc.status, MedicalDocStatus.PUBLISHED)
        self.assertFalse(doc.has_pending_revision)

    def test_draft_invalid_intent_returns_400(self) -> None:
        self.client.force_login(self.doctor_user)
        create_response = self.client.post(
            "/api/v1/medical-documents",
            data=json.dumps(
                {
                    "queue_entry_id": str(self.queue_entry.id),
                    "intake_form_id": str(self.intake_form.id),
                    "created_by_user_id": str(self.doctor_user.id),
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(create_response.status_code, 201)
        medical_document_id = create_response.json()["medical_document_id"]
        response = self.client.put(
            f"/api/v1/medical-documents/{medical_document_id}/draft",
            data=json.dumps(
                {
                    "medical_payload_schema_version": 1,
                    "medical_payload": self.VALID_PAYLOAD,
                    "intent": "typo",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json().get("error_key"), "other.api.invalid_save_draft_intent"
        )

    def test_draft_on_published_with_amend_intent_returns_200_pending_revision(
        self,
    ) -> None:
        medical_document_id = self._create_published_document()
        response = self.client.put(
            f"/api/v1/medical-documents/{medical_document_id}/draft",
            data=json.dumps(
                {
                    "medical_payload_schema_version": 1,
                    "medical_payload": self.VALID_PAYLOAD,
                    "intent": "amend",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["document_status"], MedicalDocStatus.PUBLISHED)
        self.assertTrue(body["has_pending_revision"])
        self.assertEqual(body["published_version_no"], 1)
        self.assertEqual(body["version_no"], 2)
        self.assertEqual(body["version_status"], "DRAFT")

    def test_discard_revision_clears_pending_state(self) -> None:
        medical_document_id = self._create_published_document()
        amend_response = self.client.put(
            f"/api/v1/medical-documents/{medical_document_id}/draft",
            data=json.dumps(
                {
                    "medical_payload_schema_version": 1,
                    "medical_payload": self.VALID_PAYLOAD,
                    "intent": "amend",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(amend_response.status_code, 200)

        discard_response = self.client.post(
            f"/api/v1/medical-documents/{medical_document_id}/discard-revision",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(discard_response.status_code, 200)
        body = discard_response.json()
        self.assertTrue(body["discarded"])
        self.assertEqual(body["status"], MedicalDocStatus.PUBLISHED)
        self.assertEqual(body["published_version_no"], 1)
        self.assertEqual(body["current_version_no"], 1)
        self.assertFalse(body["has_pending_revision"])

    def test_discard_revision_without_pending_returns_409(self) -> None:
        medical_document_id = self._create_published_document()
        response = self.client.post(
            f"/api/v1/medical-documents/{medical_document_id}/discard-revision",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 409)
        body = response.json()
        self.assertEqual(
            body.get("error_key") or body.get("api_message_key"),
            "other.api.no_pending_revision_to_discard",
        )

    def test_preview_pdf_invalid_source_returns_400(self) -> None:
        medical_document_id = self._create_published_document()
        response = self.client.get(
            f"/api/v1/medical-documents/{medical_document_id}/preview-pdf?source=garbage"
        )
        self.assertEqual(response.status_code, 400)


class DoctorTemplatesApiTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.admin_user = StaffUser.objects.create_user(
            username="api-admin-templates",
            email="api.admin.templates@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.admin_user, "Admin")

        self.doctor_user = StaffUser.objects.create_user(
            username="api-doctor-templates",
            email="api.doctor.templates@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.doctor_user, "Doctor")

        self.other_doctor_user = StaffUser.objects.create_user(
            username="api-doctor-templates-2",
            email="api.doctor.templates2@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.other_doctor_user, "Doctor")

    def test_doctor_templates_create_list_patch_permissions(self) -> None:
        # Doctor can create private template
        self.client.force_login(self.doctor_user)
        create_private = self.client.post(
            "/api/v1/doctor-text-templates",
            data=json.dumps(
                {
                    "actor_user_id": str(self.doctor_user.id),
                    "name": "My Template",
                    "template_locale": "pl-PL",
                    "template_body": "Text",
                    "lesion_group_favorites": [
                        {
                            "name": "Atypical control",
                            "dermatoscopic_features": ["ASYMMETRY", "MULTICOLOR"],
                            "clinical_assessment": "CONTROL_NEEDED",
                            "malignancy_risk": "LOW_SUSPICION",
                            "text": "Zmiana kontrolna do obserwacji.",
                        }
                    ],
                    "is_global": False,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(create_private.status_code, 201)
        self.assertEqual(create_private.json()["template_locale"], "pl-PL")
        self.assertEqual(len(create_private.json()["lesion_group_favorites"]), 1)
        template_id = create_private.json()["id"]

        template_detail = self.client.get(
            f"/api/v1/doctor-text-templates/{template_id}"
        )
        self.assertEqual(template_detail.status_code, 200)
        self.assertEqual(
            template_detail.json()["lesion_group_favorites"][0]["clinical_assessment"],
            "CONTROL_NEEDED",
        )

        # Doctor cannot create global template
        create_global_forbidden = self.client.post(
            "/api/v1/doctor-text-templates",
            data=json.dumps(
                {
                    "actor_user_id": str(self.doctor_user.id),
                    "name": "Global Forbidden",
                    "template_locale": "de-DE",
                    "template_body": "Text",
                    "is_global": True,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(create_global_forbidden.status_code, 400)

        # Admin can create global template
        self.client.force_login(self.admin_user)
        create_global = self.client.post(
            "/api/v1/doctor-text-templates",
            data=json.dumps(
                {
                    "actor_user_id": str(self.admin_user.id),
                    "name": "Global Allowed",
                    "template_locale": "de-DE",
                    "template_body": "Global text",
                    "is_global": True,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(create_global.status_code, 201)

        # Doctor sees own + global templates
        self.client.force_login(self.doctor_user)
        doctor_list = self.client.get(
            f"/api/v1/doctor-text-templates?actor_user_id={self.doctor_user.id}&include_inactive=true"
        )
        self.assertEqual(doctor_list.status_code, 200)
        self.assertGreaterEqual(len(doctor_list.json()["results"]), 2)

        # Other doctor cannot patch someone else's private template
        self.client.force_login(self.other_doctor_user)
        patch_forbidden = self.client.patch(
            f"/api/v1/doctor-text-templates/{template_id}",
            data=json.dumps(
                {
                    "actor_user_id": str(self.other_doctor_user.id),
                    "name": "Hack",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(patch_forbidden.status_code, 400)

        # Owner can patch own private template
        self.client.force_login(self.doctor_user)
        patch_owner = self.client.patch(
            f"/api/v1/doctor-text-templates/{template_id}",
            data=json.dumps(
                {
                    "actor_user_id": str(self.doctor_user.id),
                    "is_active": False,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(patch_owner.status_code, 200)
        self.assertFalse(patch_owner.json()["is_active"])


class ExternalUploadApiTests(MedicalApiTests):
    @patch("apps.medical.services.get_hidrive_adapter")
    def test_external_upload_happy_path(self, adapter_factory) -> None:
        self.client.force_login(self.reception_user)
        adapter_factory.return_value.upload.return_value = None
        response = self.client.post(
            "/api/v1/medical-documents/external-upload/upload",
            data={
                "queue_entry_id": str(self.queue_entry.id),
                "file": self._external_upload_file(name="Lab Result.pdf"),
            },
        )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertIn("document_id", body)
        self.assertIn("draft_version_id", body)
        self.assertIn("attachment_id", body)
        self.assertIn("/external-upload/", body["hidrive_remote_path"])
        self.assertEqual(body["original_filename"], "Lab_Result.pdf")

        doc = MedicalDocument.objects.get(id=body["document_id"])
        self.assertEqual(doc.source_type, MedicalDocumentSourceType.EXTERNAL_UPLOAD)
        att = ExternalPdfAttachment.objects.get(id=body["attachment_id"])
        self.assertEqual(att.status, ExternalPdfStatus.MATCHED)

    def test_external_upload_requires_reception_admin_manager(self) -> None:
        self.client.force_login(self.doctor_user)
        response = self.client.post(
            "/api/v1/medical-documents/external-upload/upload",
            data={
                "queue_entry_id": str(self.queue_entry.id),
                "file": self._external_upload_file(),
            },
        )
        self.assertEqual(response.status_code, 403)

    @patch("apps.medical.services.EXTERNAL_UPLOAD_MAX_BYTES", 10)
    @patch("apps.medical.services.get_hidrive_adapter")
    def test_external_upload_too_large_returns_413(self, adapter_factory) -> None:
        self.client.force_login(self.reception_user)
        upload = self._external_upload_file()
        response = self.client.post(
            "/api/v1/medical-documents/external-upload/upload",
            data={"queue_entry_id": str(self.queue_entry.id), "file": upload},
        )
        self.assertEqual(response.status_code, 413)
        adapter_factory.assert_not_called()

    @patch("apps.medical.services.get_hidrive_adapter")
    def test_external_upload_invalid_mime_returns_415(self, adapter_factory) -> None:
        self.client.force_login(self.reception_user)
        bad = SimpleUploadedFile("x.txt", b"%PDF-1.4\nx", content_type="text/plain")
        response = self.client.post(
            "/api/v1/medical-documents/external-upload/upload",
            data={"queue_entry_id": str(self.queue_entry.id), "file": bad},
        )
        self.assertEqual(response.status_code, 415)
        adapter_factory.assert_not_called()

    @patch(
        "apps.medical.api_views.upload_external_pdf_to_incoming",
        side_effect=DomainError(
            "not found",
            api_message_key="other.api.medical_document_not_found",
        ),
    )
    def test_external_upload_medical_document_not_found_returns_404(
        self, _mock_upload: object
    ) -> None:
        self.client.force_login(self.reception_user)
        response = self.client.post(
            "/api/v1/medical-documents/external-upload/upload",
            data={
                "queue_entry_id": str(self.queue_entry.id),
                "file": self._external_upload_file(),
            },
        )
        self.assertEqual(response.status_code, 404)

    @patch(
        "apps.medical.api_views.create_external_upload_medical_document",
        side_effect=DomainError(
            "forbidden",
            api_message_key="other.domain.external_upload_staff_role_required",
        ),
    )
    def test_external_upload_staff_role_required_returns_403(
        self, _mock_create: object
    ) -> None:
        self.client.force_login(self.reception_user)
        response = self.client.post(
            "/api/v1/medical-documents/external-upload/upload",
            data={
                "queue_entry_id": str(self.queue_entry.id),
                "file": self._external_upload_file(),
            },
        )
        self.assertEqual(response.status_code, 403)

    @patch(
        "apps.medical.api_views.create_external_upload_medical_document",
        side_effect=DomainError(
            "no staff",
            api_message_key="other.api.staff_user_not_found",
        ),
    )
    def test_external_upload_staff_user_not_found_returns_404(
        self, _mock_create: object
    ) -> None:
        self.client.force_login(self.reception_user)
        response = self.client.post(
            "/api/v1/medical-documents/external-upload/upload",
            data={
                "queue_entry_id": str(self.queue_entry.id),
                "file": self._external_upload_file(),
            },
        )
        self.assertEqual(response.status_code, 404)
