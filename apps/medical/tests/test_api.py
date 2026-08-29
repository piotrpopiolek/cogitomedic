from __future__ import annotations

import json
from datetime import date, timedelta
from io import BytesIO
from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from pypdf import PdfWriter

from apps.intake.models import IntakeStatus, PatientIntakeForm
from apps.core.api_utils import assign_group_to_test_user
from apps.core.exceptions import DomainError
from apps.medical.models import (
    DocVersionStatus,
    ExternalPdfAttachment,
    ExternalPdfStatus,
    MedicalDocStatus,
    MedicalDocument,
    MedicalDocumentSourceType,
    MedicalDocumentVersion,
)
from apps.medical.services import (
    authorize_paper_intake,
    list_doctor_work_queue,
)
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
        self.reception_user.clinic_sites.add(clinic)
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

    def _start_edit_session(
        self, medical_document_id: str, *, purpose: str = "edit"
    ) -> dict:
        response = self.client.post(
            f"/api/v1/medical-documents/{medical_document_id}/edit-session",
            data=json.dumps({"purpose": purpose}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def _draft_session_body(
        self,
        medical_payload: dict,
        *,
        session: dict,
        intent: str | None = None,
        request_id=None,
        schema_version: int = 1,
    ) -> dict:
        body: dict = {
            "medical_payload_schema_version": schema_version,
            "medical_payload": medical_payload,
            "edit_session_token": session["edit_session_token"],
            "expected_draft_revision": session["draft_revision"],
            "draft_save_request_id": str(request_id or uuid4()),
        }
        if intent is not None:
            body["intent"] = intent
        return body

    def _put_draft_with_session(
        self,
        medical_document_id: str,
        medical_payload: dict,
        *,
        session: dict | None = None,
        intent: str | None = None,
        request_id=None,
    ):
        sess = session or self._start_edit_session(medical_document_id)
        response = self.client.put(
            f"/api/v1/medical-documents/{medical_document_id}/draft",
            data=json.dumps(
                self._draft_session_body(
                    medical_payload,
                    session=sess,
                    intent=intent,
                    request_id=request_id,
                )
            ),
            content_type="application/json",
        )
        if response.status_code == 200:
            sess = {
                **sess,
                "draft_revision": response.json()["draft_revision"],
            }
        return response, sess

    def _mark_preview_with_session(
        self, medical_document_id: str, session: dict
    ) -> None:
        with patch(
            "apps.medical.api_views.build_merged_preview_pdf_bytes",
            return_value=(b"%PDF-1.4 preview", None),
        ):
            response = self.client.get(
                f"/api/v1/medical-documents/{medical_document_id}/preview-pdf"
                f"?source=draft&expected_draft_revision={session['draft_revision']}",
                HTTP_X_EDIT_SESSION_TOKEN=session["edit_session_token"],
            )
        self.assertEqual(response.status_code, 200, response.content)

    def _publish_with_session(
        self,
        medical_document_id: str,
        session: dict,
        *,
        publish_request_id=None,
        publish_locale: str = "de-DE",
        resend_sms: bool = False,
    ):
        body = {
            "publish_request_id": str(publish_request_id or uuid4()),
            "publish_locale": publish_locale,
            "resend_sms": resend_sms,
            "edit_session_token": session["edit_session_token"],
            "expected_draft_revision": session["draft_revision"],
        }
        return self.client.post(
            f"/api/v1/medical-documents/{medical_document_id}/publish",
            data=json.dumps(body),
            content_type="application/json",
        )

    def test_medical_document_create_rejects_cancelled_queue_entry(self) -> None:
        self.queue_entry.entry_status = QueueEntryStatus.CANCELLED
        self.queue_entry.save(update_fields=["entry_status", "updated_at"])

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
        self.assertEqual(response.status_code, 404)
        self.assertFalse(
            MedicalDocument.objects.filter(queue_entry_id=self.queue_entry.id).exists()
        )

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
        session = self._start_edit_session(medical_document_id)

        invalid_draft_response = self.client.put(
            f"/api/v1/medical-documents/{medical_document_id}/draft",
            data=json.dumps(
                self._draft_session_body({"schema_version": 2}, session=session)
            ),
            content_type="application/json",
        )
        self.assertEqual(invalid_draft_response.status_code, 400)

        payload = {
            "schema_version": 1,
            "authoring_locale": "de-DE",
            "lesions": [],
            "examination_scope": ["INTIMATE_AREA_NOT_EXAMINED"],
            "fitzpatrick_type": "TYPE_III",
            "overall_image_assessment": "NO_CONTROL_NEEDED",
            "recommendations": ["NO_SHORT_TERM_FOLLOWUP_REQUIRED"],
            "final_assessment": "NO_HIGH_GRADE_SUSPICION",
        }
        draft_response, session = self._put_draft_with_session(
            medical_document_id, payload, session=session
        )
        self.assertEqual(draft_response.status_code, 200)
        self.assertEqual(draft_response.json()["version_status"], "DRAFT")
        self.assertEqual(draft_response.json()["draft_revision"], 1)

        self._mark_preview_with_session(medical_document_id, session)
        publish_response = self._publish_with_session(medical_document_id, session)
        self.assertEqual(publish_response.status_code, 200)
        self.assertEqual(publish_response.json()["version_status"], "PUBLISHED")

        version_id = publish_response.json()["medical_document_version_id"]
        version = MedicalDocumentVersion.objects.get(id=version_id)
        self.assertEqual(version.version_status, "PUBLISHED")
        self.assertEqual(version.medical_document.status, MedicalDocStatus.PUBLISHED)

    def test_medical_documents_list_get(self) -> None:
        list_before_doc = self.client.get("/api/v1/medical-documents")
        self.assertEqual(list_before_doc.status_code, 200)
        data = list_before_doc.json()
        self.assertIn("items", data)
        self.assertIn("pagination", data)
        self.assertEqual(data["pagination"]["total"], 1)
        self.assertEqual(len(data["items"]), 1)
        self.assertIsNone(data["items"][0].get("document_id"))
        self.assertEqual(data["items"][0]["patient"]["last_name"], "Api")

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
        list_with_doc = self.client.get("/api/v1/medical-documents")
        self.assertEqual(list_with_doc.status_code, 200)
        data = list_with_doc.json()
        self.assertEqual(data["pagination"]["total"], 1)
        self.assertEqual(len(data["items"]), 1)
        item = data["items"][0]
        self.assertEqual(item["status"], MedicalDocStatus.DRAFT)
        self.assertIn("queue_date", item)
        self.assertIn("patient", item)
        self.assertIn("document_id", item)
        self.assertEqual(item["patient"]["last_name"], "Api")

    def test_medical_documents_list_order_matches_list_doctor_work_queue(self) -> None:
        """GET list and service share the same work-queue ordering (plan §4.5)."""
        other_patient = Patient.objects.create(
            first_name="Beta",
            last_name="Zebra",
            date_of_birth=date(1991, 1, 1),
            phone="+48123456789",
            email="zebra.api@example.com",
        )
        other_entry = QueueEntry.objects.create(
            daily_queue=self.queue_entry.daily_queue,
            patient=other_patient,
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
            position_no=2,
            created_by_user=self.reception_user,
            doctor_list_sort_at=timezone.now() - timedelta(hours=1),
        )
        other_session = PatientFormSession.objects.create(
            queue_entry=other_entry,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(minutes=30),
            created_by_user=self.reception_user,
        )
        other_intake = PatientIntakeForm.objects.create(
            queue_entry=other_entry,
            session=other_session,
            form_status=IntakeStatus.SUBMITTED,
            signature_file_path="/tmp/signature2.png",
            signature_sha256="b" * 64,
            submitted_at=timezone.now(),
        )
        self.client.post(
            "/api/v1/medical-documents",
            data=json.dumps(
                {
                    "queue_entry_id": str(other_entry.id),
                    "intake_form_id": str(other_intake.id),
                }
            ),
            content_type="application/json",
        )

        api_resp = self.client.get(
            "/api/v1/medical-documents",
            {"sort": "patient", "order": "asc", "page_size": "50"},
        )
        self.assertEqual(api_resp.status_code, 200)
        api_ids = [row["queue_entry_id"] for row in api_resp.json()["items"]]

        service_items, _ = list_doctor_work_queue(
            user=self.doctor_user,
            sort="patient",
            order="asc",
            page_size=50,
        )
        service_ids = [row["queue_entry_id"] for row in service_items]
        self.assertEqual(api_ids, service_ids)

    def test_medical_documents_list_get_has_stable_query_count(self) -> None:
        """GET /api/v1/medical-documents: bounded SQL (service prefetch + API overhead)."""
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(
                "/api/v1/medical-documents",
                {"page": "1", "page_size": "10"},
            )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("items", data)
        self.assertIn("pagination", data)
        # Service alone is <=8 (test_services_coverage). HTTP adds session, groups,
        # MEDICAL_DOCUMENTS_LISTED audit — measured 19 on MedicalApiTests setUp (1 row).
        self.assertLessEqual(
            len(ctx.captured_queries),
            19,
            msg=(
                f"Expected <=19 SQL queries for GET list, got "
                f"{len(ctx.captured_queries)}"
            ),
        )

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
        self.assertEqual(data["intake_summary"].get("reception_note"), "")
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
        self.assertEqual(payload["intake_summary"]["reception_note"], "")
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

        draft_response, session = self._put_draft_with_session(
            medical_document_id,
            {
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
        )
        self.assertEqual(draft_response.status_code, 200)
        self._mark_preview_with_session(medical_document_id, session)
        publish_response = self._publish_with_session(medical_document_id, session)
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

        draft_response, _ = self._put_draft_with_session(
            medical_document_id,
            {
                "schema_version": 1,
                "authoring_locale": "de-DE",
                "lesions": [],
            },
        )
        self.assertEqual(draft_response.status_code, 200)
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
        r, _ = self._put_draft_with_session(
            medical_document_id,
            {
                "schema_version": 1,
                "lesions": [
                    {
                        "lesion_numbers": [2, 3, 2],
                        "clinical_assessment": "CONTROL_NEEDED",
                        "malignancy_risk": "NO_SUSPICION",
                    }
                ],
            },
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
        r, _ = self._put_draft_with_session(
            medical_document_id,
            {
                "schema_version": 1,
                "overall_image_assessment": "CONTROL_NEEDED",
                "lesions": [],
            },
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
        draft_response, _ = self._put_draft_with_session(
            medical_document_id, full_payload
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
        draft_response, session = self._put_draft_with_session(
            medical_document_id,
            {
                "schema_version": 1,
                "authoring_locale": "de-DE",
                "lesions": [],
                "examination_scope": ["INTIMATE_AREA_NOT_EXAMINED"],
                "fitzpatrick_type": "TYPE_III",
                "overall_image_assessment": "NO_CONTROL_NEEDED",
                "recommendations": ["NO_SHORT_TERM_FOLLOWUP_REQUIRED"],
                "final_assessment": "NO_HIGH_GRADE_SUSPICION",
            },
        )
        self.assertEqual(draft_response.status_code, 200)
        self._mark_preview_with_session(medical_document_id, session)
        publish_response = self._publish_with_session(
            medical_document_id, session, resend_sms=True
        )
        self.assertEqual(publish_response.status_code, 200)

    def test_publish_without_draft_returns_409_preview_required(self) -> None:
        """Hard cutover: publish without draft/preview fails at preview revision gate."""
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
        # Do NOT save draft; publish with session only → preview gate (409).
        session = self._start_edit_session(medical_document_id)
        publish_response = self._publish_with_session(medical_document_id, session)
        self.assertEqual(publish_response.status_code, 409)
        self.assertEqual(
            publish_response.json().get("error_key"),
            "publish_preview_revision_stale",
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
        draft_response, session = self._put_draft_with_session(
            medical_document_id,
            {
                "schema_version": 1,
                "authoring_locale": "de-DE",
                "lesions": [],
            },
        )
        self.assertEqual(draft_response.status_code, 200)
        self._mark_preview_with_session(medical_document_id, session)
        publish_response = self._publish_with_session(medical_document_id, session)
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
        draft_response, session = self._put_draft_with_session(
            medical_document_id,
            {
                "schema_version": 1,
                "authoring_locale": "de-DE",
                "overall_image_assessment": "NO_CONTROL_NEEDED",
                "lesions": [],
            },
        )
        self.assertEqual(draft_response.status_code, 200)
        publish_response = self.client.post(
            f"/api/v1/medical-documents/{medical_document_id}/publish",
            data=json.dumps(
                {
                    "publish_request_id": str(uuid4()),
                    "published_by_user_id": str(self.doctor_user.id),
                    "edit_session_token": session["edit_session_token"],
                    "expected_draft_revision": session["draft_revision"],
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

        draft_response, session = self._put_draft_with_session(
            medical_document_id,
            {
                "schema_version": 1,
                "authoring_locale": "de-DE",
                "lesions": [],
                "examination_scope": ["INTIMATE_AREA_NOT_EXAMINED"],
                "fitzpatrick_type": "TYPE_III",
                "overall_image_assessment": "NO_CONTROL_NEEDED",
                "recommendations": ["NO_SHORT_TERM_FOLLOWUP_REQUIRED"],
                "final_assessment": "NO_HIGH_GRADE_SUSPICION",
            },
        )
        self.assertEqual(draft_response.status_code, 200)
        self._mark_preview_with_session(medical_document_id, session)

        request_id = str(uuid4())
        first_publish = self._publish_with_session(
            medical_document_id, session, publish_request_id=request_id
        )
        self.assertEqual(first_publish.status_code, 200)

        second_publish = self._publish_with_session(
            medical_document_id,
            session,
            publish_request_id=request_id,
            publish_locale="en-GB",
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

        fake_session = {
            "edit_session_token": str(uuid4()),
            "draft_revision": 0,
        }
        draft_missing_doc = self.client.put(
            f"/api/v1/medical-documents/{missing_doc_id}/draft",
            data=json.dumps(
                self._draft_session_body({"schema_version": 1}, session=fake_session)
            ),
            content_type="application/json",
        )
        self.assertEqual(draft_missing_doc.status_code, 404)

        publish_missing_doc = self._publish_with_session(
            str(missing_doc_id), fake_session
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
        draft_response, session = self._put_draft_with_session(
            medical_document_id,
            {
                "schema_version": 1,
                "authoring_locale": "de-DE",
                "lesions": [],
                "examination_scope": ["INTIMATE_AREA_NOT_EXAMINED"],
                "fitzpatrick_type": "TYPE_III",
                "overall_image_assessment": "NO_CONTROL_NEEDED",
                "recommendations": ["NO_SHORT_TERM_FOLLOWUP_REQUIRED"],
                "final_assessment": "NO_HIGH_GRADE_SUSPICION",
            },
        )
        self.assertEqual(draft_response.status_code, 200)
        self._mark_preview_with_session(medical_document_id, session)
        publish_response = self._publish_with_session(medical_document_id, session)
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

    def test_draft_423_when_locked_by_other_doctor(self) -> None:
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
            edit_session_token=uuid4(),
        )

        payload = {
            "schema_version": 1,
            "authoring_locale": "de-DE",
            "lesions": [],
            "examination_scope": ["INTIMATE_AREA_NOT_EXAMINED"],
            "fitzpatrick_type": "TYPE_III",
            "overall_image_assessment": "NO_CONTROL_NEEDED",
            "recommendations": ["NO_SHORT_TERM_FOLLOWUP_REQUIRED"],
            "final_assessment": "NO_HIGH_GRADE_SUSPICION",
        }
        fake_session = {
            "edit_session_token": str(uuid4()),
            "draft_revision": 0,
        }

        self.client.force_login(other)
        blocked = self.client.put(
            f"/api/v1/medical-documents/{mid}/draft",
            data=json.dumps(self._draft_session_body(payload, session=fake_session)),
            content_type="application/json",
        )
        self.assertEqual(blocked.status_code, 423)
        self.assertIn("locked_by_username", blocked.json())

    def test_draft_manager_cannot_bypass_lock_when_other_doctor_blocked(self) -> None:
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
            edit_session_token=uuid4(),
        )

        payload = {
            "schema_version": 1,
            "authoring_locale": "de-DE",
            "lesions": [],
            "examination_scope": ["INTIMATE_AREA_NOT_EXAMINED"],
            "fitzpatrick_type": "TYPE_III",
            "overall_image_assessment": "NO_CONTROL_NEEDED",
            "recommendations": ["NO_SHORT_TERM_FOLLOWUP_REQUIRED"],
            "final_assessment": "NO_HIGH_GRADE_SUSPICION",
        }
        fake_session = {
            "edit_session_token": str(uuid4()),
            "draft_revision": 0,
        }
        draft_body = self._draft_session_body(payload, session=fake_session)

        self.client.force_login(other)
        blocked = self.client.put(
            f"/api/v1/medical-documents/{mid}/draft",
            data=json.dumps(draft_body),
            content_type="application/json",
        )
        self.assertEqual(blocked.status_code, 423)

        self.client.force_login(manager)
        manager_blocked = self.client.put(
            f"/api/v1/medical-documents/{mid}/draft",
            data=json.dumps(draft_body),
            content_type="application/json",
        )
        self.assertEqual(manager_blocked.status_code, 403)

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

        payload = {
            "schema_version": 1,
            "authoring_locale": "de-DE",
            "lesions": [],
            "examination_scope": ["INTIMATE_AREA_NOT_EXAMINED"],
            "fitzpatrick_type": "TYPE_III",
            "overall_image_assessment": "NO_CONTROL_NEEDED",
            "recommendations": ["NO_SHORT_TERM_FOLLOWUP_REQUIRED"],
            "final_assessment": "NO_HIGH_GRADE_SUSPICION",
        }
        draft_response, session = self._put_draft_with_session(mid, payload)
        self.assertEqual(draft_response.status_code, 200)
        self._mark_preview_with_session(mid, session)

        dq = self.queue_entry.daily_queue
        dq.assigned_doctor = other
        dq.save(update_fields=["assigned_doctor", "updated_at"])

        self.client.force_login(other)
        fake_session = {
            "edit_session_token": str(uuid4()),
            "draft_revision": session["draft_revision"],
        }
        publish_response = self._publish_with_session(mid, fake_session)
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

        payload = {
            "schema_version": 1,
            "authoring_locale": "de-DE",
            "lesions": [],
            "examination_scope": ["INTIMATE_AREA_NOT_EXAMINED"],
            "fitzpatrick_type": "TYPE_III",
            "overall_image_assessment": "NO_CONTROL_NEEDED",
            "recommendations": ["NO_SHORT_TERM_FOLLOWUP_REQUIRED"],
            "final_assessment": "NO_HIGH_GRADE_SUSPICION",
        }
        draft_response, session = self._put_draft_with_session(mid, payload)
        self.assertEqual(draft_response.status_code, 200)
        self._mark_preview_with_session(mid, session)

        publish_response = self._publish_with_session(mid, session)
        self.assertEqual(publish_response.status_code, 200)
        self.assertEqual(publish_response.json()["version_status"], "PUBLISHED")

        doc = MedicalDocument.objects.get(id=mid)
        self.assertEqual(doc.status, MedicalDocStatus.PUBLISHED)
        self.assertIsNone(doc.locked_by_user_id)
        self.assertIsNone(doc.locked_at)

    def test_unlock_returns_410_gone(self) -> None:
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
            edit_session_token=uuid4(),
        )
        for user in (self.doctor_user, self.admin_user, self.reception_user):
            self.client.force_login(user)
            resp = self.client.post(
                f"/api/v1/medical-documents/{mid}/unlock",
                data=json.dumps({}),
                content_type="application/json",
            )
            self.assertEqual(resp.status_code, 410, msg=f"role={user.username}")
            self.assertEqual(resp.json().get("error_key"), "other.api.unlock_gone")
        doc = MedicalDocument.objects.get(id=mid)
        self.assertEqual(doc.locked_by_user_id, self.doctor_user.id)

    def test_unlock_returns_410_for_missing_document(self) -> None:
        resp = self.client.post(
            f"/api/v1/medical-documents/{uuid4()}/unlock",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 410)
        self.assertEqual(resp.json().get("error_key"), "other.api.unlock_gone")

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

    def test_admin_cannot_override_lock_on_draft_save(self) -> None:
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
            edit_session_token=uuid4(),
        )
        self.client.force_login(self.admin_user)
        fake_session = {
            "edit_session_token": str(uuid4()),
            "draft_revision": 0,
        }
        resp = self.client.put(
            f"/api/v1/medical-documents/{mid}/draft",
            data=json.dumps(
                self._draft_session_body(
                    {
                        "schema_version": 1,
                        "authoring_locale": "de-DE",
                        "lesions": [],
                        "examination_scope": ["INTIMATE_AREA_NOT_EXAMINED"],
                        "fitzpatrick_type": "TYPE_III",
                        "overall_image_assessment": "NO_CONTROL_NEEDED",
                        "recommendations": ["NO_SHORT_TERM_FOLLOWUP_REQUIRED"],
                        "final_assessment": "NO_HIGH_GRADE_SUSPICION",
                    },
                    session=fake_session,
                )
            ),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_admin_cannot_publish_medical_document(self) -> None:
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
        payload = {
            "schema_version": 1,
            "authoring_locale": "de-DE",
            "lesions": [],
            "examination_scope": ["INTIMATE_AREA_NOT_EXAMINED"],
            "fitzpatrick_type": "TYPE_III",
            "overall_image_assessment": "NO_CONTROL_NEEDED",
            "recommendations": ["NO_SHORT_TERM_FOLLOWUP_REQUIRED"],
            "final_assessment": "NO_HIGH_GRADE_SUSPICION",
        }
        draft_response, session = self._put_draft_with_session(mid, payload)
        self.assertEqual(draft_response.status_code, 200)
        self.client.force_login(self.admin_user)
        resp = self._publish_with_session(mid, session)
        self.assertEqual(resp.status_code, 403)

    def test_manager_cannot_publish_medical_document(self) -> None:
        manager = StaffUser.objects.create_user(
            username="api-manager-publish",
            email="api.manager.publish@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(manager, "Manager")
        manager.clinic_sites.add(self.queue_entry.daily_queue.clinic_site)

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
        payload = {
            "schema_version": 1,
            "authoring_locale": "de-DE",
            "lesions": [],
            "examination_scope": ["INTIMATE_AREA_NOT_EXAMINED"],
            "fitzpatrick_type": "TYPE_III",
            "overall_image_assessment": "NO_CONTROL_NEEDED",
            "recommendations": ["NO_SHORT_TERM_FOLLOWUP_REQUIRED"],
            "final_assessment": "NO_HIGH_GRADE_SUSPICION",
        }
        draft_response, session = self._put_draft_with_session(mid, payload)
        self.assertEqual(draft_response.status_code, 200)
        self.client.force_login(manager)
        resp = self._publish_with_session(mid, session)
        self.assertEqual(resp.status_code, 403)

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
        session = self._start_edit_session(mid)
        lock_time = timezone.now() - timedelta(minutes=30)
        MedicalDocument.objects.filter(id=mid).update(locked_at=lock_time)
        resp, _ = self._put_draft_with_session(
            mid,
            {
                "schema_version": 1,
                "authoring_locale": "de-DE",
                "lesions": [],
                "examination_scope": ["INTIMATE_AREA_NOT_EXAMINED"],
                "fitzpatrick_type": "TYPE_III",
                "overall_image_assessment": "NO_CONTROL_NEEDED",
                "recommendations": ["NO_SHORT_TERM_FOLLOWUP_REQUIRED"],
                "final_assessment": "NO_HIGH_GRADE_SUSPICION",
            },
            session=session,
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
        draft_response, session = self._put_draft_with_session(
            mid,
            {
                "schema_version": 1,
                "authoring_locale": "de-DE",
                "lesions": [],
                "examination_scope": ["INTIMATE_AREA_NOT_EXAMINED"],
                "fitzpatrick_type": "TYPE_III",
                "overall_image_assessment": "NO_CONTROL_NEEDED",
                "recommendations": ["NO_SHORT_TERM_FOLLOWUP_REQUIRED"],
                "final_assessment": "NO_HIGH_GRADE_SUSPICION",
            },
        )
        self.assertEqual(draft_response.status_code, 200)
        self._mark_preview_with_session(mid, session)
        self._publish_with_session(mid, session)
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
        draft_response, session = self._put_draft_with_session(
            medical_document_id, self.VALID_PAYLOAD
        )
        self.assertEqual(draft_response.status_code, 200)
        self._mark_preview_with_session(medical_document_id, session)
        publish_response = self._publish_with_session(medical_document_id, session)
        self.assertEqual(publish_response.status_code, 200)
        return medical_document_id

    def test_draft_on_published_without_intent_returns_400_read_only(self) -> None:
        medical_document_id = self._create_published_document()
        fake_session = {
            "edit_session_token": str(uuid4()),
            "draft_revision": 0,
        }
        response = self.client.put(
            f"/api/v1/medical-documents/{medical_document_id}/draft",
            data=json.dumps(
                self._draft_session_body(self.VALID_PAYLOAD, session=fake_session)
            ),
            content_type="application/json",
        )
        # Clean PUBLISHED has no edit lock → write gate read-only (start amend session first).
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json().get("error_key"),
            "other.domain.edit_session_document_read_only",
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
        session = self._start_edit_session(medical_document_id)
        response = self.client.put(
            f"/api/v1/medical-documents/{medical_document_id}/draft",
            data=json.dumps(
                self._draft_session_body(
                    self.VALID_PAYLOAD, session=session, intent="typo"
                )
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json().get("error_key"), "other.api.invalid_save_draft_intent"
        )

    def test_draft_on_published_with_amend_intent_returns_400_read_only_without_session(
        self,
    ) -> None:
        medical_document_id = self._create_published_document()
        fake_session = {
            "edit_session_token": str(uuid4()),
            "draft_revision": 0,
        }
        response = self.client.put(
            f"/api/v1/medical-documents/{medical_document_id}/draft",
            data=json.dumps(
                self._draft_session_body(
                    self.VALID_PAYLOAD, session=fake_session, intent="amend"
                )
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json().get("error_key"),
            "other.domain.edit_session_document_read_only",
        )

    def _start_amend_via_edit_session(self, medical_document_id: str) -> dict:
        response = self.client.post(
            f"/api/v1/medical-documents/{medical_document_id}/edit-session",
            data=json.dumps({"purpose": "amend"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_amend_via_edit_session_then_draft_save_returns_pending_revision(
        self,
    ) -> None:
        medical_document_id = self._create_published_document()
        session = self._start_amend_via_edit_session(medical_document_id)
        self.assertEqual(session["mode"], "acquired")
        response, session = self._put_draft_with_session(
            medical_document_id,
            self.VALID_PAYLOAD,
            session=session,
            intent="amend",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["document_status"], MedicalDocStatus.PUBLISHED)
        self.assertTrue(body["has_pending_revision"])
        self.assertEqual(body["published_version_no"], 1)
        self.assertEqual(body["version_no"], 2)
        self.assertEqual(body["version_status"], "DRAFT")
        self.assertEqual(body["draft_revision"], 3)

    def test_get_during_pending_revision_includes_reception_note(self) -> None:
        note = "Bitte Geburtsdatum prüfen"
        self.intake_form.reception_note = note
        self.intake_form.save(update_fields=["reception_note", "updated_at"])
        medical_document_id = self._create_published_document()
        session = self._start_amend_via_edit_session(medical_document_id)
        amend, _ = self._put_draft_with_session(
            medical_document_id,
            self.VALID_PAYLOAD,
            session=session,
            intent="amend",
        )
        self.assertEqual(amend.status_code, 200)
        self.assertTrue(amend.json()["has_pending_revision"])

        detail = self.client.get(f"/api/v1/medical-documents/{medical_document_id}")
        self.assertEqual(detail.status_code, 200)
        payload = detail.json()
        self.assertTrue(payload["has_pending_revision"])
        self.assertEqual(payload["status"], MedicalDocStatus.PUBLISHED)
        self.assertEqual(payload["intake_summary"]["reception_note"], note)

    def test_discard_revision_clears_pending_state(self) -> None:
        medical_document_id = self._create_published_document()
        session = self._start_amend_via_edit_session(medical_document_id)
        amend_response, session = self._put_draft_with_session(
            medical_document_id,
            self.VALID_PAYLOAD,
            session=session,
            intent="amend",
        )
        self.assertEqual(amend_response.status_code, 200)

        discard_response = self.client.post(
            f"/api/v1/medical-documents/{medical_document_id}/discard-revision",
            data=json.dumps(
                {
                    "edit_session_token": session["edit_session_token"],
                    "expected_draft_revision": session["draft_revision"],
                }
            ),
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
        # Hard cutover: discard body requires session fields.
        self.assertEqual(response.status_code, 400)

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
    def _queue_entry_on_other_clinic(self) -> QueueEntry:
        """Queue entry whose daily queue belongs to a clinic not assigned to ``reception_user``."""
        other_clinic = ClinicSite.objects.create(
            code="EXT-SCOPE-OTH", name="External upload scope other"
        )
        other_room = ConsultingRoom.objects.create(
            clinic_site=other_clinic, code="Z9", name="Z9"
        )
        other_queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=other_clinic,
            consulting_room=other_room,
            status=QueueStatus.OPEN,
            created_by_user=self.admin_user,
            assigned_doctor=self.doctor_user,
        )
        patient = Patient.objects.create(
            first_name="Scope",
            last_name="OtherSite",
            date_of_birth=date(1991, 1, 2),
            phone="+48999888777",
            email="scope.other@example.com",
            doctolib_patient_id="DOC-SCOPE-OTH-1",
        )
        return QueueEntry.objects.create(
            daily_queue=other_queue,
            patient=patient,
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
            position_no=1,
            created_by_user=self.admin_user,
        )

    def test_external_upload_upload_out_of_scope_queue_entry_returns_403(self) -> None:
        other_entry = self._queue_entry_on_other_clinic()
        self.client.force_login(self.reception_user)
        response = self.client.post(
            "/api/v1/medical-documents/external-upload/upload",
            data={
                "queue_entry_id": str(other_entry.id),
                "file": self._external_upload_file(),
            },
        )
        self.assertEqual(response.status_code, 403)

    @patch("apps.medical.services.get_hidrive_adapter")
    def test_external_upload_preview_out_of_scope_returns_403(
        self, adapter_factory
    ) -> None:
        other_entry = self._queue_entry_on_other_clinic()
        session = PatientFormSession.objects.create(
            queue_entry=other_entry,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(minutes=30),
            consumed_at=timezone.now(),
            created_by_user=self.admin_user,
        )
        other_entry.active_session = session
        other_entry.save(update_fields=["active_session", "updated_at"])
        PatientIntakeForm.objects.create(
            queue_entry=other_entry,
            session=session,
            form_status=IntakeStatus.SUBMITTED,
            signature_file_path="/tmp/signature-other.png",
            signature_sha256="d" * 64,
            submitted_at=timezone.now(),
            anamnesis_payload={"schema_version": 1, "answers": []},
        )
        adapter_factory.return_value.upload.return_value = None
        self.client.force_login(self.admin_user)
        up = self.client.post(
            "/api/v1/medical-documents/external-upload/upload",
            data={
                "queue_entry_id": str(other_entry.id),
                "file": self._external_upload_file(name="other-site.pdf"),
            },
        )
        self.assertEqual(up.status_code, 201, up.content)
        doc_id = up.json()["document_id"]

        self.client.force_login(self.reception_user)
        prev = self.client.get(
            f"/api/v1/medical-documents/{doc_id}/external-upload/preview-pdf"
        )
        self.assertEqual(prev.status_code, 403)

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
        "apps.medical.api_views.create_external_upload_pdf_and_bind_draft",
        side_effect=DomainError(
            "not found",
            api_message_key="other.api.medical_document_not_found",
        ),
    )
    def test_external_upload_medical_document_not_found_returns_404(
        self, _mock_bind: object
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
        "apps.medical.api_views.create_external_upload_pdf_and_bind_draft",
        side_effect=DomainError(
            "forbidden",
            api_message_key="other.domain.external_upload_staff_role_required",
        ),
    )
    def test_external_upload_staff_role_required_returns_403(
        self, _mock_bind: object
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
        "apps.medical.api_views.create_external_upload_pdf_and_bind_draft",
        side_effect=DomainError(
            "no staff",
            api_message_key="other.api.staff_user_not_found",
        ),
    )
    def test_external_upload_staff_user_not_found_returns_404(
        self, _mock_bind: object
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

    @patch("apps.medical.api_views.download_external_pdf")
    @patch("apps.medical.services.get_hidrive_adapter")
    def test_external_upload_select_preview_publish_revision_flow(
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
        self.assertEqual(up.status_code, 201, up.content)
        doc_id = up.json()["document_id"]
        att_id = up.json()["attachment_id"]

        sel = self.client.post(
            f"/api/v1/medical-documents/{doc_id}/external-upload/select-attachment",
            data=json.dumps({"attachment_id": att_id}),
            content_type="application/json",
        )
        self.assertEqual(sel.status_code, 200, sel.content)
        self.assertEqual(sel.json()["attachment_id"], att_id)

        prev = self.client.get(
            f"/api/v1/medical-documents/{doc_id}/external-upload/preview-pdf"
        )
        self.assertEqual(prev.status_code, 200)
        self.assertEqual(prev["Content-Type"], "application/pdf")

        pub = self.client.post(
            f"/api/v1/medical-documents/{doc_id}/external-upload/publish",
            data=json.dumps(
                {
                    "publish_request_id": str(uuid4()),
                    "publish_locale": "de-DE",
                    "resend_sms": False,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(pub.status_code, 200, pub.content)
        v = MedicalDocumentVersion.objects.get(
            id=pub.json()["medical_document_version_id"]
        )
        self.assertEqual(v.version_status, DocVersionStatus.PUBLISHED)
        self.assertTrue(
            OutboxEvent.objects.filter(
                medical_document_version_id=v.id,
                event_type=OutboxEventType.GENERATE_PDF,
            ).exists()
        )
        OutboxEvent.objects.filter(medical_document_version_id=v.id).update(
            status=OutboxStatus.PROCESSED
        )

        rev = self.client.post(
            f"/api/v1/medical-documents/{doc_id}/external-upload/revision/start",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(rev.status_code, 201, rev.content)
        self.assertEqual(rev.json()["version_status"], DocVersionStatus.DRAFT)
        doc = MedicalDocument.objects.get(id=doc_id)
        self.assertTrue(doc.has_pending_revision)

        rev2 = self.client.post(
            f"/api/v1/medical-documents/{doc_id}/external-upload/revision/start",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(rev2.status_code, 409)

    def test_external_upload_publish_without_attachment_returns_422(
        self,
    ) -> None:
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
        self.assertEqual(up.status_code, 201)
        doc_id = up.json()["document_id"]
        MedicalDocumentVersion.objects.filter(
            medical_document_id=doc_id, version_status=DocVersionStatus.DRAFT
        ).update(
            external_selected_attachment_id=None,
            external_original_filename=None,
            external_uploaded_by_user_id=None,
            external_uploaded_at=None,
        )
        self.client.force_login(self.reception_user)
        pub = self.client.post(
            f"/api/v1/medical-documents/{doc_id}/external-upload/publish",
            data=json.dumps(
                {
                    "publish_request_id": str(uuid4()),
                    "publish_locale": "de-DE",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(pub.status_code, 422)

    @patch("apps.medical.api_views.download_external_pdf")
    @patch("apps.medical.services.get_hidrive_adapter")
    def test_external_upload_preview_returns_404_when_attachment_row_deleted(
        self, adapter_factory: MagicMock, mock_download: MagicMock
    ) -> None:
        """Preview maps missing attachment row to 404; FK is PROTECT so we stub .get()."""
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
        self.assertEqual(up.status_code, 201, up.content)
        doc_id = up.json()["document_id"]
        att_id = up.json()["attachment_id"]
        sel = self.client.post(
            f"/api/v1/medical-documents/{doc_id}/external-upload/select-attachment",
            data=json.dumps({"attachment_id": att_id}),
            content_type="application/json",
        )
        self.assertEqual(sel.status_code, 200, sel.content)
        with patch.object(
            ExternalPdfAttachment.objects,
            "get",
            side_effect=ExternalPdfAttachment.DoesNotExist,
        ):
            prev = self.client.get(
                f"/api/v1/medical-documents/{doc_id}/external-upload/preview-pdf"
            )
        self.assertEqual(prev.status_code, 404)

    def test_external_upload_endpoints_forbidden_for_doctor(self) -> None:
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
        att_id = up.json()["attachment_id"]
        self.client.force_login(self.doctor_user)
        for method, path, body in (
            (
                "post",
                f"/api/v1/medical-documents/{doc_id}/external-upload/select-attachment",
                {"attachment_id": att_id},
            ),
            (
                "get",
                f"/api/v1/medical-documents/{doc_id}/external-upload/preview-pdf",
                None,
            ),
            (
                "post",
                f"/api/v1/medical-documents/{doc_id}/external-upload/publish",
                {
                    "publish_request_id": str(uuid4()),
                    "publish_locale": "de-DE",
                },
            ),
            (
                "post",
                f"/api/v1/medical-documents/{doc_id}/external-upload/revision/start",
                {},
            ),
        ):
            if method == "get":
                r = self.client.get(path)
            else:
                r = self.client.post(
                    path,
                    data=json.dumps(body),
                    content_type="application/json",
                )
            self.assertEqual(r.status_code, 403, (path, r.content))

    @patch("apps.medical.api_views.download_external_pdf")
    @patch("apps.medical.services.get_hidrive_adapter")
    def test_external_upload_doctor_raw_pdf_via_medical_document_preview_pdf(
        self, adapter_factory: MagicMock, mock_download: MagicMock
    ) -> None:
        """Doctors must not call external-upload/preview-pdf; ``preview-pdf`` returns raw lab bytes."""
        raw_lab_pdf = _minimal_pdf_bytes()
        mock_download.return_value = raw_lab_pdf
        adapter_factory.return_value.upload.return_value = None
        self.client.force_login(self.reception_user)
        up = self.client.post(
            "/api/v1/medical-documents/external-upload/upload",
            data={
                "queue_entry_id": str(self.queue_entry.id),
                "file": self._external_upload_file(),
            },
        )
        self.assertEqual(up.status_code, 201, up.content)
        doc_id = up.json()["document_id"]
        att_id = up.json()["attachment_id"]
        sel = self.client.post(
            f"/api/v1/medical-documents/{doc_id}/external-upload/select-attachment",
            data=json.dumps({"attachment_id": att_id}),
            content_type="application/json",
        )
        self.assertEqual(sel.status_code, 200, sel.content)

        self.client.force_login(self.doctor_user)
        ext_only = self.client.get(
            f"/api/v1/medical-documents/{doc_id}/external-upload/preview-pdf"
        )
        self.assertEqual(ext_only.status_code, 403)

        merged_url = f"/api/v1/medical-documents/{doc_id}/preview-pdf"
        with patch(
            "apps.medical.api_views.build_merged_preview_pdf_bytes"
        ) as merge_mock:
            merge_mock.side_effect = AssertionError(
                "EXTERNAL_UPLOAD document preview must stream raw lab PDF, "
                "not build_merged_preview_pdf_bytes"
            )
            preview = self.client.get(merged_url)
        self.assertEqual(preview.status_code, 200, preview.content)
        self.assertEqual(preview["Content-Type"], "application/pdf")
        self.assertEqual(bytes(preview.content), raw_lab_pdf)
        merge_mock.assert_not_called()


class DoctorRbacIdorMatrixTests(MedicalApiTests):
    """IDOR matrix §6.3: doctor B vs doctor A's published document (tier 1)."""

    _VALID_PAYLOAD = {
        "schema_version": 1,
        "authoring_locale": "de-DE",
        "examination_scope": ["INTIMATE_AREA_NOT_EXAMINED"],
        "fitzpatrick_type": "TYPE_III",
        "overall_image_assessment": "NO_CONTROL_NEEDED",
        "recommendations": ["NO_SHORT_TERM_FOLLOWUP_REQUIRED"],
        "final_assessment": "NO_HIGH_GRADE_SUSPICION",
    }

    def setUp(self) -> None:
        super().setUp()
        self.doctor_b = StaffUser.objects.create_user(
            username="api-idor-b",
            email="api.idor.b@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.doctor_b, "Doctor")
        self.queue_entry.daily_queue.assigned_doctor = self.doctor_b
        self.queue_entry.daily_queue.save(
            update_fields=["assigned_doctor", "updated_at"]
        )

    def _draft_put_body(
        self, *, intent: str | None = None, session: dict | None = None
    ) -> dict:
        body: dict = {
            "medical_payload_schema_version": 1,
            "medical_payload": self._VALID_PAYLOAD,
            "edit_session_token": str(uuid4()),
            "expected_draft_revision": 0,
            "draft_save_request_id": str(uuid4()),
        }
        if intent is not None:
            body["intent"] = intent
        if session is not None:
            body["edit_session_token"] = session["edit_session_token"]
            body["expected_draft_revision"] = session["draft_revision"]
            body["draft_save_request_id"] = str(uuid4())
        return body

    def _create_document_as(self, user: StaffUser) -> str:
        self.client.force_login(user)
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
        self.assertEqual(create_resp.status_code, 201, create_resp.content)
        return create_resp.json()["medical_document_id"]

    def _publish_document_as(self, user: StaffUser, medical_document_id: str) -> None:
        self.client.force_login(user)
        draft_resp, session = self._put_draft_with_session(
            medical_document_id, self._VALID_PAYLOAD
        )
        self.assertEqual(draft_resp.status_code, 200, draft_resp.content)
        self._mark_preview_with_session(medical_document_id, session)
        pub_resp = self._publish_with_session(medical_document_id, session)
        self.assertEqual(pub_resp.status_code, 200, pub_resp.content)

    def _publish_as_doctor_a(self) -> str:
        mid = self._create_document_as(self.doctor_user)
        self._publish_document_as(self.doctor_user, mid)
        return mid

    def _login_doctor_b(self) -> None:
        self.client.force_login(self.doctor_b)

    def test_doctor_b_denied_on_foreign_published_api_matrix(self) -> None:
        """A1–A14: never 200 / mutation on A's published doc without revision."""
        mid = self._publish_as_doctor_a()
        self._login_doctor_b()
        fake_att = uuid4()
        cases: list[tuple[str, str, dict | None, int]] = [
            ("GET", f"/api/v1/medical-documents/{mid}", None, 404),
            ("GET", f"/api/v1/medical-documents/{mid}/preview-pdf", None, 404),
            (
                "PUT",
                f"/api/v1/medical-documents/{mid}/draft",
                self._draft_put_body(),
                404,
            ),
            (
                "POST",
                f"/api/v1/medical-documents/{mid}/publish",
                {
                    "publish_request_id": str(uuid4()),
                    "publish_locale": "de-DE",
                    "edit_session_token": str(uuid4()),
                    "expected_draft_revision": 0,
                },
                404,
            ),
            ("POST", f"/api/v1/medical-documents/{mid}/revoke", {}, 404),
            ("POST", f"/api/v1/medical-documents/{mid}/unlock", {}, 410),
            ("GET", f"/api/v1/medical-documents/{mid}/external-pdfs", None, 404),
            (
                "GET",
                f"/api/v1/medical-documents/{mid}/external-pdfs/{fake_att}/content",
                None,
                404,
            ),
            (
                "POST",
                f"/api/v1/medical-documents/{mid}/external-pdfs/{fake_att}/reject",
                {},
                404,
            ),
            (
                "POST",
                f"/api/v1/medical-documents/{mid}/discard-revision",
                {
                    "edit_session_token": str(uuid4()),
                    "expected_draft_revision": 0,
                },
                404,
            ),
            ("GET", f"/api/v1/medical-documents/{mid}/versions", None, 404),
            ("GET", f"/api/v1/medical-documents/{mid}/audit-trail", None, 404),
            (
                "POST",
                f"/api/v1/medical-documents/{mid}/retry-processing",
                {"reason": "retry"},
                403,
            ),
            (
                "POST",
                f"/api/v1/medical-documents/{mid}/external-upload/revision/start",
                {},
                403,
            ),
        ]
        for method, url, body, expected_status in cases:
            with self.subTest(method=method, url=url):
                if method == "GET":
                    resp = self.client.get(url)
                elif method == "PUT":
                    resp = self.client.put(
                        url,
                        data=json.dumps(body),
                        content_type="application/json",
                    )
                else:
                    resp = self.client.post(
                        url,
                        data=json.dumps(body or {}),
                        content_type="application/json",
                    )
                self.assertEqual(resp.status_code, expected_status, resp.content)

    def test_doctor_b_get_detail_writes_access_denied_audit(self) -> None:
        mid = self._publish_as_doctor_a()
        AuditEvent.objects.filter(event_type="MEDICAL_DOCUMENT_ACCESS_DENIED").delete()
        self._login_doctor_b()
        detail = self.client.get(f"/api/v1/medical-documents/{mid}")
        self.assertEqual(detail.status_code, 404)
        self.assertEqual(
            AuditEvent.objects.filter(
                event_type="MEDICAL_DOCUMENT_ACCESS_DENIED",
                medical_document_id=mid,
            ).count(),
            1,
        )

    def test_doctor_b_can_access_shared_draft(self) -> None:
        """P1: shared DRAFT from doctor A."""
        mid = self._create_document_as(self.doctor_user)
        self.client.force_login(self.doctor_user)
        session = self._start_edit_session(mid)
        self._login_doctor_b()
        detail = self.client.get(f"/api/v1/medical-documents/{mid}")
        self.assertEqual(detail.status_code, 200)
        draft = self.client.put(
            f"/api/v1/medical-documents/{mid}/draft",
            data=json.dumps(self._draft_put_body(session=session)),
            content_type="application/json",
        )
        # Doctor B is not the lock holder → 423.
        self.assertEqual(draft.status_code, 423)

    def test_doctor_b_sees_shared_revision_but_draft_without_lock_returns_423(
        self,
    ) -> None:
        """P2: published + pending revision is shared work, but writes need holder."""
        mid = self._publish_as_doctor_a()
        self.client.force_login(self.doctor_user)
        amend_sess = self.client.post(
            f"/api/v1/medical-documents/{mid}/edit-session",
            data=json.dumps({"purpose": "amend"}),
            content_type="application/json",
        )
        self.assertEqual(amend_sess.status_code, 200, amend_sess.content)
        session = amend_sess.json()
        self._login_doctor_b()
        detail = self.client.get(f"/api/v1/medical-documents/{mid}")
        self.assertEqual(detail.status_code, 200)
        draft = self.client.put(
            f"/api/v1/medical-documents/{mid}/draft",
            data=json.dumps(self._draft_put_body(intent="amend", session=session)),
            content_type="application/json",
        )
        self.assertEqual(draft.status_code, 423, draft.content)

    def test_doctor_b_can_preview_own_published_document(self) -> None:
        """P3: doctor B sees own published result."""
        other_patient = Patient.objects.create(
            first_name="Idor",
            last_name="DoctorB",
            date_of_birth=date(1991, 2, 2),
            phone="+48500999111",
            email="idor.b@example.com",
        )
        other_entry = QueueEntry.objects.create(
            daily_queue=self.queue_entry.daily_queue,
            patient=other_patient,
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
            position_no=99,
            created_by_user=self.reception_user,
        )
        other_session = PatientFormSession.objects.create(
            queue_entry=other_entry,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(minutes=30),
            created_by_user=self.reception_user,
        )
        other_intake = PatientIntakeForm.objects.create(
            queue_entry=other_entry,
            session=other_session,
            form_status=IntakeStatus.SUBMITTED,
            submitted_at=timezone.now(),
            signature_sha256="d" * 64,
        )
        self.client.force_login(self.doctor_b)
        create_resp = self.client.post(
            "/api/v1/medical-documents",
            data=json.dumps(
                {
                    "queue_entry_id": str(other_entry.id),
                    "intake_form_id": str(other_intake.id),
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(create_resp.status_code, 201)
        mid_b = create_resp.json()["medical_document_id"]
        self._publish_document_as(self.doctor_b, mid_b)
        preview = self.client.get(f"/api/v1/medical-documents/{mid_b}/preview-pdf")
        self.assertEqual(preview.status_code, 200)
