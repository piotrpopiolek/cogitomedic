"""API tests for intake documents (list/detail/preview-pdf) for RECEPTION/ADMIN."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.conf import settings
from django.test import Client, TestCase
from django.utils import timezone

from apps.core.api_utils import assign_group_to_test_user
from apps.operations.models import AuditEvent
from apps.intake.models import (
    IntakeDocumentVersion,
    IntakeOutboxEvent,
    IntakeOutboxEventType,
    IntakeOutboxStatus,
    IntakePdfStatus,
    PatientIntakeForm,
)
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


def _make_intake_document_version(
    *,
    clinic_site: ClinicSite,
    consulting_room: ConsultingRoom,
    created_by_user: StaffUser,
    pdf_generation_status: str = IntakePdfStatus.PENDING,  # type: ignore[assignment]
    pdf_local_path: str | None = None,
) -> tuple[IntakeDocumentVersion, Patient, QueueEntry]:
    """Create minimal intake form + document version for API tests."""
    suffix = uuid4().hex[:8]
    # Phone must match [0-9+() -]{7,20}; use only digits for uniqueness
    phone_suffix = "".join(str(ord(c) % 10) for c in suffix[:4])
    patient = Patient.objects.create(
        first_name="PDF",
        last_name="Viewer",
        date_of_birth=date(1990, 1, 1),
        phone=f"+4811122{phone_suffix}",
        email=f"pdf-{suffix}@example.com",
        doctolib_patient_id=f"DOC-PDF-{suffix}",
    )
    queue = DailyQueue.objects.create(
        queue_date=timezone.now().date(),
        clinic_site=clinic_site,
        consulting_room=consulting_room,
        status=QueueStatus.OPEN,
        created_by_user=created_by_user,
    )
    entry = QueueEntry.objects.create(
        daily_queue=queue,
        patient=patient,
        position_no=1,
        entry_status=QueueEntryStatus.PATIENT_COMPLETED,
        created_by_user=created_by_user,
    )
    session = PatientFormSession.objects.create(
        queue_entry=entry,
        form_locale="de-DE",
        expires_at=timezone.now() + timedelta(minutes=60),
        created_by_user_id=created_by_user.id,
    )
    intake_form = PatientIntakeForm.objects.create(
        queue_entry=entry,
        session=session,
        form_status="SUBMITTED",
        submitted_at=timezone.now(),
        signature_file_path="signatures/2025/01/foo.png",
    )
    version = IntakeDocumentVersion.objects.create(
        intake_form=intake_form,
        version_no=1,
        form_locale="de-DE",
        pdf_generation_status=pdf_generation_status,
        pdf_local_path=pdf_local_path,
        snapshot_payload={"patient": {"first_name": "PDF", "last_name": "Viewer"}},
    )
    return version, patient, entry


class IntakeDocumentsApiTests(TestCase):
    """RECEPTION/ADMIN can list and preview intake PDFs; DOCTOR/TABLET get 403."""

    def setUp(self) -> None:
        self.client = Client()
        self.reception_user = StaffUser.objects.create_user(
            username="reception-intake-docs",
            email="reception-intake-docs@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.reception_user, "Reception")
        self.admin_user = StaffUser.objects.create_user(
            username="admin-intake-docs",
            email="admin-intake-docs@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.admin_user, "Admin")
        self.doctor_user = StaffUser.objects.create_user(
            username="doctor-intake-docs",
            email="doctor-intake-docs@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.doctor_user, "Doctor")
        self.clinic_a = ClinicSite.objects.create(code="IDA", name="Clinic A")
        self.clinic_b = ClinicSite.objects.create(code="IDB", name="Clinic B")
        self.room_a = ConsultingRoom.objects.create(
            clinic_site=self.clinic_a, code="RA", name="Room A"
        )
        self.room_b = ConsultingRoom.objects.create(
            clinic_site=self.clinic_b, code="RB", name="Room B"
        )
        self.reception_user.clinic_sites.add(self.clinic_a)

    def test_reception_sees_only_scoped_documents(self) -> None:
        version_a, _, _ = _make_intake_document_version(
            clinic_site=self.clinic_a,
            consulting_room=self.room_a,
            created_by_user=self.reception_user,
        )
        _make_intake_document_version(
            clinic_site=self.clinic_b,
            consulting_room=self.room_b,
            created_by_user=self.admin_user,
        )
        self.client.login(username="reception-intake-docs", password="safe-password")
        response = self.client.get("/api/v1/intake-documents")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["items"]), 1)
        self.assertEqual(data["items"][0]["id"], str(version_a.id))
        self.assertEqual(data["pagination"]["total"], 1)

    def test_admin_sees_all_documents(self) -> None:
        _make_intake_document_version(
            clinic_site=self.clinic_a,
            consulting_room=self.room_a,
            created_by_user=self.reception_user,
        )
        version_b, _, _ = _make_intake_document_version(
            clinic_site=self.clinic_b,
            consulting_room=self.room_b,
            created_by_user=self.admin_user,
        )
        self.client.login(username="admin-intake-docs", password="safe-password")
        response = self.client.get("/api/v1/intake-documents")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["pagination"]["total"], 2)
        ids = {item["id"] for item in data["items"]}
        self.assertIn(str(version_b.id), ids)

    def test_doctor_gets_403_for_list(self) -> None:
        self.client.login(username="doctor-intake-docs", password="safe-password")
        response = self.client.get("/api/v1/intake-documents")
        self.assertEqual(response.status_code, 403)

    def test_reception_gets_403_for_document_out_of_scope(self) -> None:
        version_b, _, _ = _make_intake_document_version(
            clinic_site=self.clinic_b,
            consulting_room=self.room_b,
            created_by_user=self.admin_user,
        )
        self.client.login(username="reception-intake-docs", password="safe-password")
        response = self.client.get(f"/api/v1/intake-documents/{version_b.id}")
        self.assertEqual(response.status_code, 404)

    def test_reception_gets_detail_in_scope(self) -> None:
        version_a, patient, _ = _make_intake_document_version(
            clinic_site=self.clinic_a,
            consulting_room=self.room_a,
            created_by_user=self.reception_user,
        )
        self.client.login(username="reception-intake-docs", password="safe-password")
        response = self.client.get(f"/api/v1/intake-documents/{version_a.id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], str(version_a.id))
        self.assertEqual(data["patient"]["last_name"], patient.last_name)
        self.assertEqual(data["clinic_site_id"], str(self.clinic_a.id))

    def test_preview_pdf_returns_404_when_not_generated(self) -> None:
        version_a, _, _ = _make_intake_document_version(
            clinic_site=self.clinic_a,
            consulting_room=self.room_a,
            created_by_user=self.reception_user,
            pdf_generation_status=IntakePdfStatus.PENDING,  # type: ignore[arg-type]
        )
        self.client.login(username="reception-intake-docs", password="safe-password")
        response = self.client.get(
            f"/api/v1/intake-documents/{version_a.id}/preview-pdf"
        )
        self.assertEqual(response.status_code, 404)
        self.assertIn("error", response.json())

    def test_preview_pdf_returns_404_when_file_missing(self) -> None:
        version_a, _, _ = _make_intake_document_version(
            clinic_site=self.clinic_a,
            consulting_room=self.room_a,
            created_by_user=self.reception_user,
            pdf_generation_status=IntakePdfStatus.COMPLETED,  # type: ignore[arg-type]
            pdf_local_path="pdfs/intake/2099/01/nonexistent.pdf",
        )
        self.client.login(username="reception-intake-docs", password="safe-password")
        response = self.client.get(
            f"/api/v1/intake-documents/{version_a.id}/preview-pdf"
        )
        self.assertEqual(response.status_code, 404)

    def test_preview_pdf_returns_inline_pdf_when_file_exists(self) -> None:
        rel_path = f"pdfs/intake/2099/01/{uuid4()}.pdf"
        full_path = Path(settings.MEDIA_ROOT) / rel_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_bytes(b"%PDF-1.0 minimal\n")
        version_a, _, _ = _make_intake_document_version(
            clinic_site=self.clinic_a,
            consulting_room=self.room_a,
            created_by_user=self.reception_user,
            pdf_generation_status=IntakePdfStatus.COMPLETED,  # type: ignore[arg-type]
            pdf_local_path=rel_path,
        )
        self.client.login(username="reception-intake-docs", password="safe-password")
        response = self.client.get(
            f"/api/v1/intake-documents/{version_a.id}/preview-pdf"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("inline", response.get("Content-Disposition", ""))
        self.assertEqual(response.content, b"%PDF-1.0 minimal\n")

    def test_intake_document_not_found_returns_404(self) -> None:
        self.client.login(username="reception-intake-docs", password="safe-password")
        response = self.client.get(f"/api/v1/intake-documents/{uuid4()}")
        self.assertEqual(response.status_code, 404)

    def test_list_empty_returns_200(self) -> None:
        self.client.login(username="reception-intake-docs", password="safe-password")
        response = self.client.get("/api/v1/intake-documents")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"], [])
        self.assertEqual(response.json()["pagination"]["total"], 0)


class IntakeOutboxOperationsApiTests(TestCase):
    """ADMIN batch intake outbox — audit for who triggered the tool."""

    def setUp(self) -> None:
        self.client = Client()
        self.admin_user = StaffUser.objects.create_user(
            username="intake-ops-admin",
            email="intake.ops.admin@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.admin_user, "Admin")
        self.client.login(username="intake-ops-admin", password="safe-password")

    def test_intake_outbox_process_creates_batch_triggered_audit(self) -> None:
        response = self.client.post(
            "/api/v1/operations/intake-outbox/process",
            data=json.dumps({"limit": 3}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 202)
        ev = (
            AuditEvent.objects.filter(
                event_type="OPERATIONS_INTAKE_OUTBOX_BATCH_TRIGGERED",
                actor_user_id=self.admin_user.id,
            )
            .order_by("-event_time")
            .first()
        )
        self.assertIsNotNone(ev)
        self.assertEqual(ev.metadata.get("limit"), 3)
        self.assertIn("client_ip", ev.metadata)


class IntakeFormsClinicScopeApiTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.reception_user = StaffUser.objects.create_user(
            username="intake-form-reception",
            email="intake.form.reception@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.reception_user, "Reception")
        self.admin_user = StaffUser.objects.create_user(
            username="intake-form-admin",
            email="intake.form.admin@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.admin_user, "Admin")
        self.clinic_a = ClinicSite.objects.create(code="IFA", name="Intake Form A")
        self.clinic_b = ClinicSite.objects.create(code="IFB", name="Intake Form B")
        self.room_a = ConsultingRoom.objects.create(
            clinic_site=self.clinic_a, code="IFA-1", name="A1"
        )
        self.room_b = ConsultingRoom.objects.create(
            clinic_site=self.clinic_b, code="IFB-1", name="B1"
        )
        self.reception_user.clinic_sites.add(self.clinic_a)

        self.form_a = _make_intake_document_version(
            clinic_site=self.clinic_a,
            consulting_room=self.room_a,
            created_by_user=self.reception_user,
        )[0].intake_form
        self.form_b = _make_intake_document_version(
            clinic_site=self.clinic_b,
            consulting_room=self.room_b,
            created_by_user=self.admin_user,
        )[0].intake_form

    def test_reception_cannot_get_intake_form_outside_assigned_clinic(self) -> None:
        self.client.login(username="intake-form-reception", password="safe-password")
        response = self.client.get(f"/api/v1/intake-forms/{self.form_b.id}")
        self.assertEqual(response.status_code, 404)

    def test_reception_cannot_patch_intake_form_outside_assigned_clinic(self) -> None:
        self.client.login(username="intake-form-reception", password="safe-password")
        response = self.client.patch(
            f"/api/v1/intake-forms/{self.form_b.id}",
            data=json.dumps({"body_map_schema_version": 1, "body_map_data": []}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)

    def test_admin_can_get_intake_form_in_any_clinic(self) -> None:
        self.client.login(username="intake-form-admin", password="safe-password")
        response = self.client.get(f"/api/v1/intake-forms/{self.form_b.id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["intake_form_id"], str(self.form_b.id))


class IntakeOutboxClinicScopeApiTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.reception_user = StaffUser.objects.create_user(
            username="intake-outbox-scope-reception",
            email="intake.outbox.scope.reception@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.reception_user, "Reception")
        self.admin_user = StaffUser.objects.create_user(
            username="intake-outbox-scope-admin",
            email="intake.outbox.scope.admin@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.admin_user, "Admin")
        self.clinic_a = ClinicSite.objects.create(code="IOA", name="Intake Outbox A")
        self.clinic_b = ClinicSite.objects.create(code="IOB", name="Intake Outbox B")
        self.room_a = ConsultingRoom.objects.create(
            clinic_site=self.clinic_a, code="IOA-1", name="A1"
        )
        self.room_b = ConsultingRoom.objects.create(
            clinic_site=self.clinic_b, code="IOB-1", name="B1"
        )
        self.reception_user.clinic_sites.add(self.clinic_a)

        self.version_a, _, _ = _make_intake_document_version(
            clinic_site=self.clinic_a,
            consulting_room=self.room_a,
            created_by_user=self.reception_user,
        )
        self.version_b, _, _ = _make_intake_document_version(
            clinic_site=self.clinic_b,
            consulting_room=self.room_b,
            created_by_user=self.admin_user,
        )
        self.event_a = IntakeOutboxEvent.objects.create(
            intake_document_version=self.version_a,
            aggregate_id=self.version_a.id,
            event_type=IntakeOutboxEventType.GENERATE_INTAKE_PDF,
            status=IntakeOutboxStatus.FAILED,
            payload={"x": "a"},
            error_message="A failed",
        )
        self.event_b = IntakeOutboxEvent.objects.create(
            intake_document_version=self.version_b,
            aggregate_id=self.version_b.id,
            event_type=IntakeOutboxEventType.GENERATE_INTAKE_PDF,
            status=IntakeOutboxStatus.FAILED,
            payload={"x": "b"},
            error_message="B failed",
        )

    def test_reception_outbox_list_contains_only_scoped_intake_events(self) -> None:
        self.client.login(
            username="intake-outbox-scope-reception", password="safe-password"
        )
        response = self.client.get(
            "/api/v1/intake-outbox-events?status=FAILED&limit=20"
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["results"][0]["id"], str(self.event_a.id))

    def test_reception_cannot_retry_intake_outbox_event_outside_scope(self) -> None:
        self.client.login(
            username="intake-outbox-scope-reception", password="safe-password"
        )
        response = self.client.post(
            f"/api/v1/intake-outbox-events/{self.event_b.id}/retry",
            data=json.dumps({"reason": "retry test"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)

    def test_admin_can_retry_intake_outbox_event_in_any_clinic(self) -> None:
        self.client.login(
            username="intake-outbox-scope-admin", password="safe-password"
        )
        response = self.client.post(
            f"/api/v1/intake-outbox-events/{self.event_b.id}/retry",
            data=json.dumps({"reason": "retry test"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)


# ---------------------------------------------------------------------------
# Helper shared by IntakeFormDetailViewTests and IntakeFormConsentsViewTests
# ---------------------------------------------------------------------------


def _make_minimal_intake_form(
    *,
    created_by_user: StaffUser,
    clinic_site: ClinicSite,
    consulting_room: ConsultingRoom,
    form_status: str = "IN_PROGRESS",
) -> PatientIntakeForm:
    """Return a PatientIntakeForm linked to the minimal required objects."""
    suffix = uuid4().hex[:6]
    patient = Patient.objects.create(
        first_name="Detail",
        last_name="Patient",
        date_of_birth=date(1985, 3, 10),
        phone=f"4811100{str(abs(hash(suffix)))[:7]}",
        email=f"detail-{suffix}@example.com",
        doctolib_patient_id=f"DETAIL-{suffix}",
    )
    queue = DailyQueue.objects.create(
        queue_date=timezone.now().date(),
        clinic_site=clinic_site,
        consulting_room=consulting_room,
        status=QueueStatus.OPEN,
        created_by_user=created_by_user,
    )
    entry = QueueEntry.objects.create(
        daily_queue=queue,
        patient=patient,
        position_no=1,
        entry_status=QueueEntryStatus.IN_PROGRESS,
        created_by_user=created_by_user,
    )
    session = PatientFormSession.objects.create(
        queue_entry=entry,
        form_locale="de-DE",
        expires_at=timezone.now() + timedelta(minutes=60),
        created_by_user_id=created_by_user.id,
    )
    return PatientIntakeForm.objects.create(
        queue_entry=entry,
        session=session,
        form_status=form_status,
        signature_file_path=None,
    )


# ---------------------------------------------------------------------------
# intake_form_detail_view  (GET + PATCH /api/v1/intake-forms/<id>)
# ---------------------------------------------------------------------------


class IntakeFormDetailViewTests(TestCase):
    """Cover intake_form_detail_view: role check, GET (locale, 404, happy-path),
    PATCH (invalid JSON, validation error, 404, state error, happy-path, 405)."""

    def setUp(self) -> None:
        self.client = Client()
        self.reception_user = StaffUser.objects.create_user(
            username="reception-form-detail",
            email="reception-form-detail@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.reception_user, "Reception")
        self.doctor_user = StaffUser.objects.create_user(
            username="doctor-form-detail",
            email="doctor-form-detail@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.doctor_user, "Doctor")
        self.clinic = ClinicSite.objects.create(code="FDV", name="Form Detail Clinic")
        self.reception_user.clinic_sites.add(self.clinic)
        self.room = ConsultingRoom.objects.create(
            clinic_site=self.clinic, code="FD1", name="FD1"
        )

    # ------------------------------------------------------------------
    # Role enforcement
    # ------------------------------------------------------------------

    def test_doctor_gets_403_on_get(self) -> None:
        self.client.login(username="doctor-form-detail", password="safe-password")
        response = self.client.get(f"/api/v1/intake-forms/{uuid4()}")
        self.assertEqual(response.status_code, 403)

    def test_unauthenticated_gets_401_on_get(self) -> None:
        response = self.client.get(f"/api/v1/intake-forms/{uuid4()}")
        self.assertEqual(response.status_code, 401)

    # ------------------------------------------------------------------
    # GET — locale validation
    # ------------------------------------------------------------------

    def test_get_invalid_locale_returns_400(self) -> None:
        self.client.login(username="reception-form-detail", password="safe-password")
        response = self.client.get(
            f"/api/v1/intake-forms/{uuid4()}?form_locale=INVALID123"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json())

    # ------------------------------------------------------------------
    # GET — 404 for non-existent form
    # ------------------------------------------------------------------

    def test_get_nonexistent_form_returns_404(self) -> None:
        self.client.login(username="reception-form-detail", password="safe-password")
        response = self.client.get(f"/api/v1/intake-forms/{uuid4()}")
        self.assertEqual(response.status_code, 404)

    # ------------------------------------------------------------------
    # GET — happy path (service mocked)
    # ------------------------------------------------------------------

    @patch("apps.intake.api_views.get_intake_form_context")
    def test_get_valid_form_returns_200(self, mock_ctx) -> None:
        mock_ctx.return_value = {
            "consents": [],
            "questions": [],
            "form_status": "IN_PROGRESS",
        }
        intake_form = _make_minimal_intake_form(
            created_by_user=self.reception_user,
            clinic_site=self.clinic,
            consulting_room=self.room,
        )
        self.client.login(username="reception-form-detail", password="safe-password")
        response = self.client.get(f"/api/v1/intake-forms/{intake_form.id}")
        self.assertEqual(response.status_code, 200)
        mock_ctx.assert_called_once()

    # ------------------------------------------------------------------
    # PATCH — input validation
    # ------------------------------------------------------------------

    def test_patch_invalid_json_returns_400(self) -> None:
        self.client.login(username="reception-form-detail", password="safe-password")
        response = self.client.patch(
            f"/api/v1/intake-forms/{uuid4()}",
            data="NOT_JSON{{{",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_patch_invalid_body_schema_returns_400(self) -> None:
        self.client.login(username="reception-form-detail", password="safe-password")
        response = self.client.patch(
            f"/api/v1/intake-forms/{uuid4()}",
            data=json.dumps({"wrong_field": "bad"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    # ------------------------------------------------------------------
    # PATCH — service errors
    # ------------------------------------------------------------------

    def test_patch_nonexistent_form_returns_404(self) -> None:
        self.client.login(username="reception-form-detail", password="safe-password")
        response = self.client.patch(
            f"/api/v1/intake-forms/{uuid4()}",
            data=json.dumps({"body_map_schema_version": 1, "body_map_data": []}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)

    @patch("apps.intake.api_views.save_intake_body_map")
    def test_patch_state_error_returns_409(self, mock_save) -> None:
        from apps.core.exceptions import StateTransitionError
        from apps.core.domain_messages import domain_message

        mock_save.side_effect = StateTransitionError(
            domain_message("other.domain.invalid_shift_code", value="x"),
            api_message_key="other.domain.invalid_shift_code",
        )
        intake_form = _make_minimal_intake_form(
            created_by_user=self.reception_user,
            clinic_site=self.clinic,
            consulting_room=self.room,
        )
        self.client.login(username="reception-form-detail", password="safe-password")
        response = self.client.patch(
            f"/api/v1/intake-forms/{intake_form.id}",
            data=json.dumps({"body_map_schema_version": 1, "body_map_data": []}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 409)

    @patch("apps.intake.api_views.save_intake_body_map")
    def test_patch_happy_path_returns_200(self, mock_save) -> None:
        intake_form = _make_minimal_intake_form(
            created_by_user=self.reception_user,
            clinic_site=self.clinic,
            consulting_room=self.room,
        )
        mock_intake = MagicMock()
        mock_intake.id = intake_form.id
        mock_intake.body_map_schema_version = 1
        mock_intake.body_map_data = []
        mock_save.return_value = mock_intake

        self.client.login(username="reception-form-detail", password="safe-password")
        response = self.client.patch(
            f"/api/v1/intake-forms/{intake_form.id}",
            data=json.dumps({"body_map_schema_version": 1, "body_map_data": []}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("intake_form_id", data)
        self.assertIn("body_map_data", data)

    # ------------------------------------------------------------------
    # Method not allowed
    # ------------------------------------------------------------------

    def test_put_returns_405(self) -> None:
        self.client.login(username="reception-form-detail", password="safe-password")
        response = self.client.put(
            f"/api/v1/intake-forms/{uuid4()}",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 405)

    def test_delete_returns_405(self) -> None:
        self.client.login(username="reception-form-detail", password="safe-password")
        response = self.client.delete(f"/api/v1/intake-forms/{uuid4()}")
        self.assertEqual(response.status_code, 405)


# ---------------------------------------------------------------------------
# intake_form_consents_view  (PUT /api/v1/intake-forms/<id>/consents)
# ---------------------------------------------------------------------------


class IntakeFormConsentsViewTests(TestCase):
    """Cover intake_form_consents_view: role check, JSON error, 404, happy path."""

    def setUp(self) -> None:
        self.client = Client()
        self.reception_user = StaffUser.objects.create_user(
            username="reception-consents",
            email="reception-consents@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.reception_user, "Reception")
        self.doctor_user = StaffUser.objects.create_user(
            username="doctor-consents",
            email="doctor-consents@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.doctor_user, "Doctor")
        self.clinic = ClinicSite.objects.create(code="CSV", name="Consents Clinic")
        self.reception_user.clinic_sites.add(self.clinic)
        self.room = ConsultingRoom.objects.create(
            clinic_site=self.clinic, code="CS1", name="CS1"
        )

    def test_doctor_gets_403(self) -> None:
        self.client.login(username="doctor-consents", password="safe-password")
        response = self.client.put(
            f"/api/v1/intake-forms/{uuid4()}/consents",
            data=json.dumps({"consents": []}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_invalid_json_returns_400(self) -> None:
        self.client.login(username="reception-consents", password="safe-password")
        response = self.client.put(
            f"/api/v1/intake-forms/{uuid4()}/consents",
            data="BAD_JSON{",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_invalid_body_schema_returns_400(self) -> None:
        self.client.login(username="reception-consents", password="safe-password")
        response = self.client.put(
            f"/api/v1/intake-forms/{uuid4()}/consents",
            data=json.dumps({"wrong_key": []}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_nonexistent_form_returns_404(self) -> None:
        self.client.login(username="reception-consents", password="safe-password")
        response = self.client.put(
            f"/api/v1/intake-forms/{uuid4()}/consents",
            data=json.dumps({"consents": []}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)

    @patch("apps.intake.api_views.save_intake_consents")
    def test_happy_path_returns_200_with_consents_list(self, mock_save) -> None:
        intake_form = _make_minimal_intake_form(
            created_by_user=self.reception_user,
            clinic_site=self.clinic,
            consulting_room=self.room,
        )
        mock_save.return_value = intake_form

        self.client.login(username="reception-consents", password="safe-password")
        response = self.client.put(
            f"/api/v1/intake-forms/{intake_form.id}/consents",
            data=json.dumps({"consents": []}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("intake_form_id", data)
        self.assertIn("consents", data)
        self.assertEqual(data["consents"], [])
        mock_save.assert_called_once()

    @patch("apps.intake.api_views.save_intake_consents")
    def test_state_error_returns_409(self, mock_save) -> None:
        from apps.core.exceptions import StateTransitionError
        from apps.core.domain_messages import domain_message

        mock_save.side_effect = StateTransitionError(
            domain_message("other.domain.invalid_shift_code", value="x"),
            api_message_key="other.domain.invalid_shift_code",
        )
        intake_form = _make_minimal_intake_form(
            created_by_user=self.reception_user,
            clinic_site=self.clinic,
            consulting_room=self.room,
        )
        self.client.login(username="reception-consents", password="safe-password")
        response = self.client.put(
            f"/api/v1/intake-forms/{intake_form.id}/consents",
            data=json.dumps({"consents": []}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 409)
