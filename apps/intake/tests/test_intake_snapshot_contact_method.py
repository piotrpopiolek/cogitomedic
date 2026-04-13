"""Intake PDF snapshot: Präventions Kontaktweg (no WeasyPrint import chain)."""

from __future__ import annotations

from datetime import date, timedelta

from django.test import TestCase
from django.utils import timezone

from apps.intake.models import (
    ConsentDefinition,
    IntakeStatus,
    PatientIntakeConsent,
    PatientIntakeForm,
)
from apps.intake.services import (
    CONTACT_METHOD_CONSENT_CODE,
    _build_intake_snapshot_payload,
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


class IntakeSnapshotPreventionContactTests(TestCase):
    def setUp(self) -> None:
        user = StaffUser.objects.create_user(
            username="snap-intake-contact",
            email="snap.contact@example.com",
            password="safe-password",
            is_staff=True,
        )
        clinic = ClinicSite.objects.create(code="SNP", name="Snapshot clinic")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="R1", name="R1")
        daily_queue = DailyQueue.objects.create(
            queue_date=timezone.localdate(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            created_by_user=user,
        )
        patient = Patient.objects.create(
            first_name="Snap",
            last_name="Patient",
            date_of_birth=date(1991, 3, 3),
            phone="+48111222333",
        )
        self.queue_entry = QueueEntry.objects.create(
            daily_queue=daily_queue,
            patient=patient,
            entry_status=QueueEntryStatus.IN_PROGRESS,
            position_no=1,
            created_by_user=user,
        )
        self.session = PatientFormSession.objects.create(
            queue_entry=self.queue_entry,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(minutes=30),
            created_by_user=user,
        )
        self.intake_form = PatientIntakeForm.objects.create(
            queue_entry=self.queue_entry,
            session=self.session,
            form_status=IntakeStatus.IN_PROGRESS,
            anamnesis_payload={"answers": []},
        )

    def test_build_snapshot_includes_contact_method_selection(self) -> None:
        definition = (
            ConsentDefinition.objects.filter(
                code=CONTACT_METHOD_CONSENT_CODE, is_active=True
            )
            .order_by("-version")
            .first()
        )
        if definition is None:
            self.skipTest("Contact method consent definition not seeded")
        PatientIntakeConsent.objects.create(
            intake_form=self.intake_form,
            consent_definition=definition,
            accepted=True,
            accepted_at=timezone.now(),
            selected_option_codes=["email", "PHONE"],
        )
        payload = _build_intake_snapshot_payload(
            intake_form=self.intake_form, now=timezone.now()
        )
        row = next(
            (
                c
                for c in payload["consents"]
                if c["code"] == CONTACT_METHOD_CONSENT_CODE
            ),
            None,
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["selected_option_codes"], ["EMAIL", "PHONE"])
        opts = row.get("contact_method_all_options") or []
        self.assertEqual(len(opts), 3)
        by_code = {o["option_code"]: o for o in opts}
        self.assertTrue(by_code["EMAIL"]["selected"])
        self.assertFalse(by_code["SMS"]["selected"])
        self.assertTrue(by_code["PHONE"]["selected"])
