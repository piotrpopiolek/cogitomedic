"""API tests for intake documents (list/detail/preview-pdf) for RECEPTION/ADMIN."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.test import Client, TestCase
from django.utils import timezone

from apps.core.api_utils import assign_group_to_test_user
from apps.operations.models import AuditEvent
from apps.intake.models import (
    IntakeDocumentVersion,
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
    pdf_generation_status: str = IntakePdfStatus.PENDING,
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
        self.client.login(
            username="reception-intake-docs", password="safe-password"
        )
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
        self.client.login(
            username="doctor-intake-docs", password="safe-password"
        )
        response = self.client.get("/api/v1/intake-documents")
        self.assertEqual(response.status_code, 403)

    def test_reception_gets_403_for_document_out_of_scope(self) -> None:
        version_b, _, _ = _make_intake_document_version(
            clinic_site=self.clinic_b,
            consulting_room=self.room_b,
            created_by_user=self.admin_user,
        )
        self.client.login(
            username="reception-intake-docs", password="safe-password"
        )
        response = self.client.get(
            f"/api/v1/intake-documents/{version_b.id}"
        )
        self.assertEqual(response.status_code, 404)

    def test_reception_gets_detail_in_scope(self) -> None:
        version_a, patient, _ = _make_intake_document_version(
            clinic_site=self.clinic_a,
            consulting_room=self.room_a,
            created_by_user=self.reception_user,
        )
        self.client.login(
            username="reception-intake-docs", password="safe-password"
        )
        response = self.client.get(
            f"/api/v1/intake-documents/{version_a.id}"
        )
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
            pdf_generation_status=IntakePdfStatus.PENDING,
        )
        self.client.login(
            username="reception-intake-docs", password="safe-password"
        )
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
            pdf_generation_status=IntakePdfStatus.COMPLETED,
            pdf_local_path="pdfs/intake/2099/01/nonexistent.pdf",
        )
        self.client.login(
            username="reception-intake-docs", password="safe-password"
        )
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
            pdf_generation_status=IntakePdfStatus.COMPLETED,
            pdf_local_path=rel_path,
        )
        self.client.login(
            username="reception-intake-docs", password="safe-password"
        )
        response = self.client.get(
            f"/api/v1/intake-documents/{version_a.id}/preview-pdf"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("inline", response.get("Content-Disposition", ""))
        self.assertEqual(response.content, b"%PDF-1.0 minimal\n")

    def test_intake_document_not_found_returns_404(self) -> None:
        self.client.login(
            username="reception-intake-docs", password="safe-password"
        )
        response = self.client.get(
            f"/api/v1/intake-documents/{uuid4()}"
        )
        self.assertEqual(response.status_code, 404)

    def test_list_empty_returns_200(self) -> None:
        self.client.login(
            username="reception-intake-docs", password="safe-password"
        )
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
        ev = AuditEvent.objects.filter(
            event_type="OPERATIONS_INTAKE_OUTBOX_BATCH_TRIGGERED",
            actor_user_id=self.admin_user.id,
        ).order_by("-event_time").first()
        self.assertIsNotNone(ev)
        self.assertEqual(ev.metadata.get("limit"), 3)
        self.assertIn("client_ip", ev.metadata)
