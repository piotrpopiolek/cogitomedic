from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.core.exceptions import DomainError
from apps.intake.models import IntakeStatus, PatientIntakeForm
from apps.medical.models import (
    DocVersionStatus,
    MedicalDocStatus,
    MedicalDocument,
    MedicalDocumentSourceType,
)
from apps.medical.services import (
    create_medical_document_without_intake,
    create_or_get_medical_document,
    publish_document_version,
    save_draft_document_version,
)
from apps.operations.models import AuditEvent
from apps.operations.services import REF_KEY
from apps.outbox.models import OutboxEvent, OutboxEventType
from django.core.exceptions import ObjectDoesNotExist

from apps.core.api_utils import assign_group_to_test_user
import apps.medical.services as medical_services
from apps.medical.services import (
    check_doctor_document_access,
    check_doctor_queue_entry_access,
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

    def test_medical_document_defaults_to_digital_intake(self) -> None:
        self.assertEqual(
            self.medical_document.source_type,
            MedicalDocumentSourceType.DIGITAL_INTAKE,
        )

    def test_medical_document_consistency_constraint_blocks_paper_with_intake(
        self,
    ) -> None:
        other_patient = Patient.objects.create(
            first_name="Other",
            last_name="Patient",
            date_of_birth=date(1988, 4, 4),
            phone="+48700111222",
            email="other.patient@example.com",
        )
        other_queue_entry = QueueEntry.objects.create(
            daily_queue=self.queue_entry.daily_queue,
            patient=other_patient,
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
            position_no=2,
            created_by_user=self.reception_user,
        )
        other_session = PatientFormSession.objects.create(
            queue_entry=other_queue_entry,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(minutes=30),
            consumed_at=timezone.now(),
            created_by_user=self.reception_user,
        )
        other_intake_form = PatientIntakeForm.objects.create(
            queue_entry=other_queue_entry,
            session=other_session,
            form_status=IntakeStatus.SUBMITTED,
            signature_sha256="d" * 64,
            submitted_at=timezone.now(),
            anamnesis_payload={"answers": []},
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                MedicalDocument.objects.create(
                    queue_entry=other_queue_entry,
                    intake_form=other_intake_form,
                    source_type=MedicalDocumentSourceType.PAPER_INTAKE,
                    created_by_user=self.doctor_user,
                )

    def test_medical_document_consistency_constraint_blocks_digital_without_intake(
        self,
    ) -> None:
        other_patient = Patient.objects.create(
            first_name="Queue",
            last_name="NoIntake",
            date_of_birth=date(1989, 5, 5),
            phone="+48700111333",
            email="queue.nointake@example.com",
        )
        other_queue_entry = QueueEntry.objects.create(
            daily_queue=self.queue_entry.daily_queue,
            patient=other_patient,
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
            position_no=3,
            created_by_user=self.reception_user,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                MedicalDocument.objects.create(
                    queue_entry=other_queue_entry,
                    intake_form=None,
                    source_type=MedicalDocumentSourceType.DIGITAL_INTAKE,
                    created_by_user=self.doctor_user,
                )

    def test_create_medical_document_without_intake_happy_path(self) -> None:
        patient = Patient.objects.create(
            first_name="Paper",
            last_name="Candidate",
            date_of_birth=date(1980, 6, 6),
            phone="+48700222444",
            email="paper.candidate@example.com",
        )
        queue_entry = QueueEntry.objects.create(
            daily_queue=self.queue_entry.daily_queue,
            patient=patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=5,
            appointment_time=timezone.now() - timedelta(hours=4),
            created_by_user=self.reception_user,
        )

        doc = create_medical_document_without_intake(
            queue_entry_id=queue_entry.id,
            created_by_user_id=self.doctor_user.id,
            reason="paper fallback",
        )

        queue_entry.refresh_from_db()
        self.assertEqual(doc.queue_entry_id, queue_entry.id)
        self.assertIsNone(doc.intake_form_id)
        self.assertEqual(doc.source_type, MedicalDocumentSourceType.PAPER_INTAKE)
        self.assertEqual(
            queue_entry.entry_status, QueueEntryStatus.PAPER_INTAKE_COMPLETED
        )

    def test_create_medical_document_without_intake_requires_waiting_status(
        self,
    ) -> None:
        with self.assertRaises(DomainError) as ctx:
            create_medical_document_without_intake(
                queue_entry_id=self.queue_entry.id,
                created_by_user_id=self.doctor_user.id,
                reason="paper fallback",
            )
        self.assertEqual(
            ctx.exception.api_message_key,
            "other.domain.queue_entry_must_be_waiting_for_paper_intake",
        )

    def test_create_medical_document_without_intake_requires_appointment_time(
        self,
    ) -> None:
        patient = Patient.objects.create(
            first_name="No",
            last_name="Appointment",
            date_of_birth=date(1979, 7, 7),
            phone="+48700333555",
            email="no.appointment@example.com",
        )
        queue_entry = QueueEntry.objects.create(
            daily_queue=self.queue_entry.daily_queue,
            patient=patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=6,
            appointment_time=None,
            created_by_user=self.reception_user,
        )
        with self.assertRaises(DomainError) as ctx:
            create_medical_document_without_intake(
                queue_entry_id=queue_entry.id,
                created_by_user_id=self.doctor_user.id,
                reason="paper fallback",
            )
        self.assertEqual(
            ctx.exception.api_message_key,
            "other.domain.paper_intake_requires_appointment_time",
        )

    def test_create_medical_document_without_intake_enforces_three_hour_window(
        self,
    ) -> None:
        patient = Patient.objects.create(
            first_name="Too",
            last_name="Early",
            date_of_birth=date(1978, 8, 8),
            phone="+48700444666",
            email="too.early@example.com",
        )
        queue_entry = QueueEntry.objects.create(
            daily_queue=self.queue_entry.daily_queue,
            patient=patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=7,
            appointment_time=timezone.now() - timedelta(hours=2, minutes=59),
            created_by_user=self.reception_user,
        )
        with self.assertRaises(DomainError) as ctx:
            create_medical_document_without_intake(
                queue_entry_id=queue_entry.id,
                created_by_user_id=self.doctor_user.id,
                reason="paper fallback",
            )
        self.assertEqual(
            ctx.exception.api_message_key,
            "other.domain.paper_intake_earliest_after_appointment",
        )

    def test_create_medical_document_without_intake_rejects_existing_document(
        self,
    ) -> None:
        patient = Patient.objects.create(
            first_name="Existing",
            last_name="Document",
            date_of_birth=date(1977, 9, 9),
            phone="+48700555777",
            email="existing.document@example.com",
        )
        queue_entry = QueueEntry.objects.create(
            daily_queue=self.queue_entry.daily_queue,
            patient=patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=8,
            appointment_time=timezone.now() - timedelta(hours=4),
            created_by_user=self.reception_user,
        )
        session = PatientFormSession.objects.create(
            queue_entry=queue_entry,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(minutes=30),
            consumed_at=timezone.now(),
            created_by_user=self.reception_user,
        )
        intake_form = PatientIntakeForm.objects.create(
            queue_entry=queue_entry,
            session=session,
            form_status=IntakeStatus.SUBMITTED,
            signature_sha256="e" * 64,
            submitted_at=timezone.now(),
            anamnesis_payload={"answers": []},
        )
        MedicalDocument.objects.create(
            queue_entry=queue_entry,
            intake_form=intake_form,
            source_type=MedicalDocumentSourceType.DIGITAL_INTAKE,
            created_by_user=self.doctor_user,
            updated_by_user=self.doctor_user,
        )
        with self.assertRaises(DomainError) as ctx:
            create_medical_document_without_intake(
                queue_entry_id=queue_entry.id,
                created_by_user_id=self.doctor_user.id,
                reason="paper fallback",
            )
        self.assertEqual(
            ctx.exception.api_message_key,
            "other.domain.medical_document_already_exists_for_queue_entry",
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
        audit = AuditEvent.objects.filter(
            event_type="DOCUMENT_DRAFT_SAVED",
            medical_document_id=self.medical_document.id,
        ).first()
        self.assertIsNotNone(audit)
        self.assertEqual(
            audit.context_clinic_site_id, self.queue_entry.daily_queue.clinic_site_id
        )
        ref = audit.metadata.get(REF_KEY) or {}
        self.assertEqual(
            ref.get("patient_id"), str(self.medical_document.queue_entry.patient_id)
        )
        self.assertEqual(ref.get("medical_document_id"), str(self.medical_document.id))
        self.assertEqual(
            ref.get("context_clinic_site_id"),
            str(self.queue_entry.daily_queue.clinic_site_id),
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
            medical_payload={
                "schema_version": 1,
                "authoring_locale": "de-DE",
                "examination_scope": ["INTIMATE_AREA_NOT_EXAMINED"],
                "fitzpatrick_type": "TYPE_III",
                "overall_image_assessment": "NO_CONTROL_NEEDED",
                "recommendations": ["NO_SHORT_TERM_FOLLOWUP_REQUIRED"],
                "final_assessment": "NO_HIGH_GRADE_SUSPICION",
            },
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
            medical_payload={
                "schema_version": 1,
                "authoring_locale": "de-DE",
                "examination_scope": ["INTIMATE_AREA_NOT_EXAMINED"],
                "fitzpatrick_type": "TYPE_III",
                "overall_image_assessment": "NO_CONTROL_NEEDED",
                "recommendations": ["NO_SHORT_TERM_FOLLOWUP_REQUIRED"],
                "final_assessment": "NO_HIGH_GRADE_SUSPICION",
            },
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
            OutboxEvent.objects.filter(
                medical_document_version=first, event_type=OutboxEventType.GENERATE_PDF
            ).count(),
            1,
        )

    def test_publish_document_version_returns_in_progress_publication(self) -> None:
        save_draft_document_version(
            medical_document_id=self.medical_document.id,
            updated_by_user_id=self.doctor_user.id,
            medical_payload={
                "schema_version": 1,
                "authoring_locale": "de-DE",
                "examination_scope": ["INTIMATE_AREA_NOT_EXAMINED"],
                "fitzpatrick_type": "TYPE_III",
                "overall_image_assessment": "NO_CONTROL_NEEDED",
                "recommendations": ["NO_SHORT_TERM_FOLLOWUP_REQUIRED"],
                "final_assessment": "NO_HIGH_GRADE_SUSPICION",
            },
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

        # DRAFT: any doctor may access (shared queue)
        check_doctor_document_access(self.medical_document, other_doctor)

        MedicalDocument.objects.filter(pk=self.medical_document.id).update(
            status=MedicalDocStatus.PUBLISHED
        )
        self.medical_document.refresh_from_db()
        with self.assertRaises(ObjectDoesNotExist):
            check_doctor_document_access(self.medical_document, other_doctor)

        # Assign other_doctor to the queue
        self.medical_document.queue_entry.daily_queue.assigned_doctor = other_doctor
        self.medical_document.queue_entry.daily_queue.save()

        # Should not raise now (assigned on published document)
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
        # Creator can open without assigned_doctor while document is DRAFT
        check_doctor_queue_entry_access(self.queue_entry, self.doctor_user)

        other_doctor = StaffUser.objects.create_user(
            username="qe_other",
            email="qe_other@example.com",
            password="pwd",
            is_staff=True,
        )
        assign_group_to_test_user(other_doctor, "Doctor")
        check_doctor_queue_entry_access(self.queue_entry, other_doctor)

        MedicalDocument.objects.filter(pk=self.medical_document.id).update(
            status=MedicalDocStatus.PUBLISHED
        )
        with self.assertRaises(ObjectDoesNotExist):
            check_doctor_queue_entry_access(self.queue_entry, other_doctor)

        self.queue_entry.daily_queue.assigned_doctor = other_doctor
        self.queue_entry.daily_queue.save()
        check_doctor_queue_entry_access(self.queue_entry, other_doctor)

    def test_check_doctor_queue_entry_access_doctor_without_medical_document(
        self,
    ) -> None:
        other_doctor = StaffUser.objects.create_user(
            username="qe_no_doc",
            email="qe_no_doc@example.com",
            password="pwd",
            is_staff=True,
        )
        assign_group_to_test_user(other_doctor, "Doctor")
        patient2 = Patient.objects.create(
            first_name="No",
            last_name="DocYet",
            date_of_birth=date(1982, 2, 2),
            phone="+49999999999",
            email="nodoc@example.com",
            doctolib_patient_id="DOC-NO-M",
        )
        entry2 = QueueEntry.objects.create(
            daily_queue=self.queue_entry.daily_queue,
            patient=patient2,
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
            position_no=2,
            created_by_user=self.reception_user,
        )
        check_doctor_queue_entry_access(entry2, other_doctor)
        with self.assertRaises(ObjectDoesNotExist):
            check_doctor_queue_entry_access(entry2, self.reception_user)

    def test_staff_user_display_name_empty_and_username_fallback(self) -> None:
        self.assertEqual(medical_services._staff_user_display_name(None), "")
        bare = StaffUser.objects.create_user(
            username="uonly",
            email="uonly@example.com",
            password="pwd",
            first_name="",
            last_name="",
            is_staff=True,
        )
        self.assertEqual(medical_services._staff_user_display_name(bare), "uonly")


class LesionGroupFavoritesAdminTests(TestCase):
    """Tests for lesion_group_favorites widget and form validation in admin."""

    def test_widget_render_contains_textarea_and_visual_editor_markup(self) -> None:
        from apps.medical.widgets import LesionGroupFavoritesWidget

        w = LesionGroupFavoritesWidget()
        html = w.render(
            "lesion_group_favorites", [], {"id": "id_lesion_group_favorites"}
        )
        self.assertIn('name="lesion_group_favorites"', html)
        self.assertIn("id_lesion_group_favorites", html)
        self.assertIn("lesionGroupFavoritesWidget", html)
        self.assertIn("lesion-group-favorites-", html)
        self.assertIn('x-data="lesionGroupFavoritesWidget', html)
        self.assertIn("border-base-200", html)

    def test_widget_render_includes_choices_data(self) -> None:
        import base64
        import json

        from apps.medical.widgets import LesionGroupFavoritesWidget

        w = LesionGroupFavoritesWidget()
        html = w.render("lesion_group_favorites", [], {"id": "id_lgf"})
        ctx = w.get_context("lesion_group_favorites", [], {"id": "id_lgf"})
        wgt = ctx["widget"]
        for key in ("dermatoscopic_b64", "clinical_b64", "malignancy_b64"):
            blob = wgt[key]
            self.assertIn(blob, html, msg=f"expected {key} payload in rendered HTML")
        derm = json.loads(base64.b64decode(wgt["dermatoscopic_b64"]))
        clinical = json.loads(base64.b64decode(wgt["clinical_b64"]))
        malignancy = json.loads(base64.b64decode(wgt["malignancy_b64"]))
        self.assertTrue(any(x["value"] == "ASYMMETRY" for x in derm))
        self.assertTrue(any(x["value"] == "CONTROL_NEEDED" for x in clinical))
        self.assertTrue(any(x["value"] == "NO_SUSPICION" for x in malignancy))

    def test_form_clean_lesion_group_favorites_valid_list_passes(self) -> None:
        from apps.medical.admin import DoctorTextTemplateForm

        form = DoctorTextTemplateForm(
            data={
                "name": "Test",
                "template_locale": "pl-PL",
                "template_body": "Body",
                "is_global": True,
                "is_active": True,
                "lesion_group_favorites": '[{"name":"P1","dermatoscopic_features":["ASYMMETRY"],"clinical_assessment":"CONTROL_NEEDED","malignancy_risk":"LOW_SUSPICION","text":"Text."}]',
            },
        )
        form.is_valid()
        self.assertNotIn("lesion_group_favorites", form.errors)

    def test_form_clean_lesion_group_favorites_invalid_code_raises(self) -> None:
        from apps.medical.admin import DoctorTextTemplateForm

        form = DoctorTextTemplateForm(
            data={
                "name": "Test",
                "template_locale": "pl-PL",
                "template_body": "Body",
                "lesion_group_favorites": '[{"name":"P1","dermatoscopic_features":["INVALID_CODE"],"clinical_assessment":"CONTROL_NEEDED","malignancy_risk":"LOW_SUSPICION","text":"Text."}]',
            },
        )
        form.is_valid()
        self.assertIn("lesion_group_favorites", form.errors)

    def test_form_clean_lesion_group_favorites_empty_name_raises(self) -> None:
        from apps.medical.admin import DoctorTextTemplateForm

        form = DoctorTextTemplateForm(
            data={
                "name": "Test",
                "template_locale": "pl-PL",
                "template_body": "Body",
                "lesion_group_favorites": '[{"name":"","dermatoscopic_features":[],"clinical_assessment":"UNREMARKABLE","malignancy_risk":"NO_SUSPICION","text":"Some text."}]',
            },
        )
        form.is_valid()
        self.assertIn("lesion_group_favorites", form.errors)


class DocumentRevisionStateTests(MedicalServicesTests):

    def _publish_initial_version(self):
        save_draft_document_version(
            medical_document_id=self.medical_document.id,
            updated_by_user_id=self.doctor_user.id,
            medical_payload={
                "schema_version": 1,
                "authoring_locale": "de-DE",
                "examination_scope": ["INTIMATE_AREA_NOT_EXAMINED"],
                "fitzpatrick_type": "TYPE_III",
                "overall_image_assessment": "NO_CONTROL_NEEDED",
                "recommendations": ["NO_SHORT_TERM_FOLLOWUP_REQUIRED"],
                "final_assessment": "NO_HIGH_GRADE_SUSPICION",
                "version": 1,
            },
        )
        published = publish_document_version(
            medical_document_id=self.medical_document.id,
            publish_request_id=uuid4(),
            published_by_user_id=self.doctor_user.id,
            publish_locale="de-DE",
        )
        self.medical_document.refresh_from_db()
        return published

    def test_save_draft_invalid_intent_raises_distinct_key(self) -> None:
        from apps.core.exceptions import DomainError

        save_draft_document_version(
            medical_document_id=self.medical_document.id,
            updated_by_user_id=self.doctor_user.id,
            medical_payload={"authoring_locale": "de-DE", "lesions": []},
        )
        with self.assertRaises(DomainError) as ctx:
            save_draft_document_version(
                medical_document_id=self.medical_document.id,
                updated_by_user_id=self.doctor_user.id,
                medical_payload={"authoring_locale": "de-DE", "lesions": [], "x": 1},
                intent="typo",
            )
        self.assertEqual(
            ctx.exception.api_message_key, "other.api.invalid_save_draft_intent"
        )

    def test_save_draft_on_published_without_amend_intent_raises(self) -> None:
        from apps.core.exceptions import DomainError

        self._publish_initial_version()

        with self.assertRaises(DomainError) as ctx:
            save_draft_document_version(
                medical_document_id=self.medical_document.id,
                updated_by_user_id=self.doctor_user.id,
                medical_payload={"authoring_locale": "de-DE", "version": 2},
            )
        self.assertEqual(
            ctx.exception.api_message_key, "other.api.amend_intent_required"
        )

        self.medical_document.refresh_from_db()
        self.assertEqual(self.medical_document.status, MedicalDocStatus.PUBLISHED)
        self.assertFalse(self.medical_document.has_pending_revision)

    def test_save_draft_amend_keeps_status_published_and_flags_pending(self) -> None:
        published = self._publish_initial_version()
        self.assertEqual(self.medical_document.published_version_no, 1)
        self.assertFalse(self.medical_document.has_pending_revision)

        revision = save_draft_document_version(
            medical_document_id=self.medical_document.id,
            updated_by_user_id=self.doctor_user.id,
            medical_payload={"authoring_locale": "de-DE", "version": 2},
            intent="amend",
        )
        self.medical_document.refresh_from_db()

        self.assertEqual(revision.version_no, 2)
        self.assertEqual(revision.version_status, DocVersionStatus.DRAFT)
        self.assertEqual(self.medical_document.status, MedicalDocStatus.PUBLISHED)
        self.assertEqual(self.medical_document.published_version_no, 1)
        self.assertEqual(self.medical_document.current_version_no, 1)
        self.assertTrue(self.medical_document.has_pending_revision)
        self.assertNotEqual(revision.id, published.id)

        revision_started = AuditEvent.objects.filter(
            event_type="DOCUMENT_REVISION_STARTED",
            medical_document_id=self.medical_document.id,
        ).first()
        self.assertIsNotNone(revision_started)

    def test_save_draft_amend_updates_existing_pending_revision_in_place(self) -> None:
        self._publish_initial_version()
        first = save_draft_document_version(
            medical_document_id=self.medical_document.id,
            updated_by_user_id=self.doctor_user.id,
            medical_payload={"authoring_locale": "de-DE", "rev": 1},
            intent="amend",
        )
        second = save_draft_document_version(
            medical_document_id=self.medical_document.id,
            updated_by_user_id=self.doctor_user.id,
            medical_payload={"authoring_locale": "de-DE", "rev": 2},
            intent="amend",
        )
        self.assertEqual(first.id, second.id)
        self.assertEqual(second.medical_payload["rev"], 2)
        self.assertEqual(self.medical_document.versions.count(), 2)

    def test_discard_pending_revision_removes_draft_and_clears_flag(self) -> None:
        from apps.medical.services import discard_pending_revision

        self._publish_initial_version()
        revision = save_draft_document_version(
            medical_document_id=self.medical_document.id,
            updated_by_user_id=self.doctor_user.id,
            medical_payload={"authoring_locale": "de-DE", "rev": 1},
            intent="amend",
        )

        discard_pending_revision(
            medical_document_id=self.medical_document.id,
            actor_user_id=self.doctor_user.id,
        )
        self.medical_document.refresh_from_db()

        self.assertFalse(self.medical_document.has_pending_revision)
        self.assertEqual(self.medical_document.status, MedicalDocStatus.PUBLISHED)
        self.assertEqual(self.medical_document.current_version_no, 1)
        self.assertFalse(self.medical_document.versions.filter(pk=revision.id).exists())

        discarded = AuditEvent.objects.filter(
            event_type="DOCUMENT_REVISION_DISCARDED",
            medical_document_id=self.medical_document.id,
        ).first()
        self.assertIsNotNone(discarded)

    def test_discard_pending_revision_without_pending_raises(self) -> None:
        from apps.core.exceptions import DomainError
        from apps.medical.services import discard_pending_revision

        self._publish_initial_version()

        with self.assertRaises(DomainError) as ctx:
            discard_pending_revision(
                medical_document_id=self.medical_document.id,
                actor_user_id=self.doctor_user.id,
            )
        self.assertEqual(
            ctx.exception.api_message_key,
            "other.api.no_pending_revision_to_discard",
        )

    def test_publish_after_amend_emits_republished_audit_and_updates_state(
        self,
    ) -> None:
        self._publish_initial_version()
        save_draft_document_version(
            medical_document_id=self.medical_document.id,
            updated_by_user_id=self.doctor_user.id,
            medical_payload={
                "schema_version": 1,
                "authoring_locale": "de-DE",
                "examination_scope": ["INTIMATE_AREA_NOT_EXAMINED"],
                "fitzpatrick_type": "TYPE_III",
                "overall_image_assessment": "NO_CONTROL_NEEDED",
                "recommendations": ["NO_SHORT_TERM_FOLLOWUP_REQUIRED"],
                "final_assessment": "NO_HIGH_GRADE_SUSPICION",
                "rev": 1,
            },
            intent="amend",
        )

        republished = publish_document_version(
            medical_document_id=self.medical_document.id,
            publish_request_id=uuid4(),
            published_by_user_id=self.doctor_user.id,
            publish_locale="de-DE",
        )
        self.medical_document.refresh_from_db()

        self.assertEqual(republished.version_no, 2)
        self.assertEqual(republished.version_status, DocVersionStatus.PUBLISHED)
        self.assertEqual(self.medical_document.published_version_no, 2)
        self.assertEqual(self.medical_document.current_version_no, 2)
        self.assertEqual(self.medical_document.status, MedicalDocStatus.PUBLISHED)
        self.assertFalse(self.medical_document.has_pending_revision)

        republished_audit = AuditEvent.objects.filter(
            event_type="DOCUMENT_REPUBLISHED",
            medical_document_id=self.medical_document.id,
        ).first()
        self.assertIsNotNone(republished_audit)
        self.assertEqual(republished_audit.metadata.get("new_published_version_no"), 2)
        self.assertEqual(
            republished_audit.metadata.get("previous_published_version_no"), 1
        )
