"""Contract tests for audit events: immutable refs and required references per event type."""

from __future__ import annotations

from uuid import uuid4

from django.test import TestCase
from django.utils import timezone

from apps.operations.api_views import _serialize_audit_event
from apps.operations.services import REF_KEY, create_audit_event
from apps.reception.models import (
    ClinicSite,
    ConsultingRoom,
    DailyQueue,
    Patient,
    QueueEntry,
    QueueEntryStatus,
    QueueStatus,
)
from apps.users.models import StaffUser


class CreateAuditEventContractTests(TestCase):
    """Assert create_audit_event stores immutable refs and accepts context_clinic_site_id."""

    def test_create_audit_event_stores_immutable_refs_in_metadata(self) -> None:
        """IDs passed to create_audit_event are copied into metadata['_ref'] for compliance."""
        user = StaffUser.objects.create_user(
            username="audit_ref_user",
            email="ref@test.com",
            password="x",
            is_staff=True,
        )
        clinic = ClinicSite.objects.create(code="R1", name="RefTest")
        patient = Patient.objects.create(
            first_name="R",
            last_name="T",
            date_of_birth=timezone.now().date(),
            phone="+48999888777",
            email="r@t.com",
        )

        event = create_audit_event(
            event_type="TEST_EVENT",
            patient_id=patient.id,
            context_clinic_site_id=clinic.id,
            actor_user_id=user.id,
        )

        ref = event.metadata.get(REF_KEY)
        self.assertIsNotNone(ref)
        self.assertEqual(ref.get("patient_id"), str(patient.id))
        self.assertEqual(ref.get("context_clinic_site_id"), str(clinic.id))
        self.assertEqual(ref.get("actor_user_id"), str(user.id))

    def test_create_audit_event_stores_context_clinic_site_id_on_model(self) -> None:
        """context_clinic_site_id is persisted on the model when provided."""
        clinic = ClinicSite.objects.create(code="C1", name="Clinic1")
        event = create_audit_event(
            event_type="TEST_EVENT",
            context_clinic_site_id=clinic.id,
        )
        self.assertEqual(event.context_clinic_site_id, clinic.id)

    def test_serialize_uses_ref_when_fk_null(self) -> None:
        """After SET_NULL (e.g. anonymization), API still exposes IDs from metadata._ref."""
        patient_id = uuid4()
        event = create_audit_event(
            event_type="TEST_EVENT",
            patient_id=patient_id,
        )
        # Simulate SET_NULL: FK was cleared but _ref remains
        event.patient_id = None
        event.save(update_fields=["patient_id"])

        payload = _serialize_audit_event(event)
        self.assertEqual(payload["patient_id"], str(patient_id))

    def test_serialize_prefers_fk_over_ref(self) -> None:
        """When FK is set, response uses FK; _ref is for fallback only."""
        user = StaffUser.objects.create_user(
            username="audit_test_user",
            email="audit@test.com",
            password="x",
            is_staff=True,
        )
        clinic = ClinicSite.objects.create(code="T1", name="Test")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="R1", name="R1")
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            created_by_user=user,
        )
        patient = Patient.objects.create(
            first_name="A",
            last_name="B",
            date_of_birth=timezone.now().date(),
            phone="+48111222333",
            email="a@b.c",
        )
        QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
            position_no=1,
            created_by_user=user,
        )

        event = create_audit_event(
            event_type="TEST_EVENT",
            patient_id=patient.id,
            context_clinic_site_id=clinic.id,
        )
        payload = _serialize_audit_event(event)
        self.assertEqual(payload["patient_id"], str(patient.id))
        self.assertEqual(payload["context_clinic_site_id"], str(clinic.id))
