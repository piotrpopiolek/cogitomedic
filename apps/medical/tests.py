from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

from django.test import TestCase
from django.utils import timezone

from apps.intake.models import IntakeStatus, PatientIntakeForm
from apps.medical.models import DocVersionStatus, MedicalDocument, MedicalDocStatus
from apps.medical.services import create_or_get_medical_document, publish_document_version, save_draft_document_version
from apps.operations.models import AuditEvent
from apps.outbox.models import OutboxEvent, OutboxEventType
from django.core.exceptions import ObjectDoesNotExist

from apps.core.api_utils import assign_group_to_test_user
from apps.medical.services import check_doctor_document_access, check_doctor_queue_entry_access
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


class MedicalServicesTests(TestCase):
    def setUp(self) -> None:
        self.doctor_user = StaffUser.objects.create_user(
            username="doctor1",
            email="doctor1@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.doctor_user, "Doctor")
        
        self.reception_user = StaffUser.objects.create_user(
            username="reception1",
            email="reception1@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.reception_user, "Reception")
        clinic = ClinicSite.objects.create(code="MUC", name="Munich")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="M1", name="M1")
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            created_by_user=self.reception_user,
        )
        patient = Patient.objects.create(
            first_name="Med",
            last_name="Patient",
            date_of_birth=date(1981, 1, 1),
            phone="+49888888888",
            email="med.patient@example.com",
            doctolib_patient_id="DOC-M-1",
        )
        self.queue_entry = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
            position_no=1,
            created_by_user=self.reception_user,
        )
        self.session = PatientFormSession.objects.create(
            queue_entry=self.queue_entry,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(minutes=30),
            consumed_at=timezone.now(),
            created_by_user=self.reception_user,
        )
        self.queue_entry.active_session = self.session
        self.queue_entry.save(update_fields=["active_session", "updated_at"])
        self.intake_form = PatientIntakeForm.objects.create(
            queue_entry=self.queue_entry,
            session=self.session,
            form_status=IntakeStatus.SUBMITTED,
            signature_file_path="/tmp/signature.png",
            signature_sha256="c" * 64,
            submitted_at=timezone.now(),
            anamnesis_payload={"answers": []},
        )
        self.medical_document = create_or_get_medical_document(
            queue_entry_id=self.queue_entry.id,
            intake_form_id=self.intake_form.id,
            created_by_user_id=self.doctor_user.id,
        )

    def test_save_draft_document_version_creates_new_version(self) -> None:
        version = save_draft_document_version(
            medical_document_id=self.medical_document.id,
            updated_by_user_id=self.doctor_user.id,
            medical_payload={"authoring_locale": "de-DE", "lesions": []},
            diagnosis_code="D1",
            procedure_code="P1",
        )
        self.medical_document.refresh_from_db()

        self.assertEqual(version.version_no, 1)
        self.assertEqual(version.version_status, DocVersionStatus.DRAFT)
        self.assertEqual(self.medical_document.current_version_no, 1)
        self.assertEqual(self.medical_document.status, MedicalDocStatus.DRAFT)
        self.assertTrue(
            AuditEvent.objects.filter(
                event_type="DOCUMENT_DRAFT_SAVED",
                medical_document_id=self.medical_document.id,
            ).exists()
        )

    def test_save_draft_document_version_updates_existing_draft(self) -> None:
        first = save_draft_document_version(
            medical_document_id=self.medical_document.id,
            updated_by_user_id=self.doctor_user.id,
            medical_payload={"authoring_locale": "de-DE", "value": 1},
        )
        second = save_draft_document_version(
            medical_document_id=self.medical_document.id,
            updated_by_user_id=self.doctor_user.id,
            medical_payload={"authoring_locale": "de-DE", "value": 2},
        )

        self.assertEqual(first.id, second.id)
        self.assertEqual(second.medical_payload["value"], 2)
        self.assertEqual(
            self.medical_document.versions.count(),
            1,
        )

    def test_publish_document_version_sets_published_and_enqueues_outbox(self) -> None:
        draft = save_draft_document_version(
            medical_document_id=self.medical_document.id,
            updated_by_user_id=self.doctor_user.id,
            medical_payload={"authoring_locale": "de-DE"},
        )
        request_id = uuid4()

        published = publish_document_version(
            medical_document_id=self.medical_document.id,
            publish_request_id=request_id,
            published_by_user_id=self.doctor_user.id,
            publish_locale="de-DE",
        )
        self.medical_document.refresh_from_db()

        self.assertEqual(published.id, draft.id)
        self.assertEqual(published.version_status, DocVersionStatus.PUBLISHED)
        self.assertEqual(published.publish_request_id, request_id)
        self.assertEqual(self.medical_document.status, MedicalDocStatus.PUBLISHED)
        self.assertTrue(
            OutboxEvent.objects.filter(
                medical_document_version=published,
                event_type=OutboxEventType.GENERATE_PDF,
            ).exists()
        )
        self.assertTrue(
            AuditEvent.objects.filter(
                event_type="DOCUMENT_PUBLISHED",
                medical_document_id=self.medical_document.id,
            ).exists()
        )

    def test_publish_document_version_is_idempotent_for_same_request_id(self) -> None:
        save_draft_document_version(
            medical_document_id=self.medical_document.id,
            updated_by_user_id=self.doctor_user.id,
            medical_payload={"authoring_locale": "de-DE"},
        )
        request_id = uuid4()
        first = publish_document_version(
            medical_document_id=self.medical_document.id,
            publish_request_id=request_id,
            published_by_user_id=self.doctor_user.id,
            publish_locale="de-DE",
        )
        second = publish_document_version(
            medical_document_id=self.medical_document.id,
            publish_request_id=request_id,
            published_by_user_id=self.doctor_user.id,
            publish_locale="de-DE",
        )

        self.assertEqual(first.id, second.id)
        self.assertEqual(
            OutboxEvent.objects.filter(medical_document_version=first, event_type=OutboxEventType.GENERATE_PDF).count(),
            1,
        )

    def test_publish_document_version_returns_in_progress_publication(self) -> None:
        save_draft_document_version(
            medical_document_id=self.medical_document.id,
            updated_by_user_id=self.doctor_user.id,
            medical_payload={"authoring_locale": "de-DE"},
        )
        first = publish_document_version(
            medical_document_id=self.medical_document.id,
            publish_request_id=uuid4(),
            published_by_user_id=self.doctor_user.id,
            publish_locale="de-DE",
        )
        second = publish_document_version(
            medical_document_id=self.medical_document.id,
            publish_request_id=uuid4(),
            published_by_user_id=self.doctor_user.id,
            publish_locale="de-DE",
        )

        self.assertEqual(first.id, second.id)
        self.assertEqual(self.medical_document.versions.count(), 1)


    def test_check_doctor_document_access_allows_author(self) -> None:
        # doctor_user is the author of self.medical_document
        # Should not raise exception
        check_doctor_document_access(self.medical_document, self.doctor_user)

    def test_check_doctor_document_access_allows_assigned_doctor(self) -> None:
        other_doctor = StaffUser.objects.create_user(
            username="otherdoc",
            email="otherdoc@example.com",
            password="pwd",
            is_staff=True,
        )
        assign_group_to_test_user(other_doctor, "Doctor")

        # Should raise initially
        with self.assertRaises(ObjectDoesNotExist):
            check_doctor_document_access(self.medical_document, other_doctor)

        # Assign other_doctor to the queue
        self.medical_document.queue_entry.daily_queue.assigned_doctor = other_doctor
        self.medical_document.queue_entry.daily_queue.save()

        # Should not raise now
        check_doctor_document_access(self.medical_document, other_doctor)

    def test_check_doctor_document_access_allows_admin(self) -> None:
        admin_user = StaffUser.objects.create_user(
            username="adminuser",
            email="admin@example.com",
            password="pwd",
            is_staff=True,
        )
        assign_group_to_test_user(admin_user, "Admin")

        # Admin can access any document
        check_doctor_document_access(self.medical_document, admin_user)

    def test_check_doctor_queue_entry_access(self) -> None:
        # Initial state: queue has no assigned_doctor
        with self.assertRaises(ObjectDoesNotExist):
            check_doctor_queue_entry_access(self.queue_entry, self.doctor_user)
            
        # Assign to queue
        self.queue_entry.daily_queue.assigned_doctor = self.doctor_user
        self.queue_entry.daily_queue.save()
        
        # Now it works
        check_doctor_queue_entry_access(self.queue_entry, self.doctor_user)
