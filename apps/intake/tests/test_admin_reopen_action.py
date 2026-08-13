"""Admin action ``reopen_intake_for_patient_editing`` (permission + skip + success)."""

from __future__ import annotations

from datetime import date, timedelta

from django.contrib import admin, messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.api_utils import assign_group_to_test_user
from apps.intake.admin import PatientIntakeFormAdmin
from apps.intake.models import IntakeStatus, PatientIntakeForm
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


def _request_with_messages(user: StaffUser):
    factory = RequestFactory()
    request = factory.get("/admin/intake/patientintakeform/")
    request.user = user
    middleware = SessionMiddleware(lambda r: None)
    middleware.process_request(request)
    request.session.save()
    request._messages = FallbackStorage(request)
    return request


class PatientIntakeFormAdminReopenActionTests(TestCase):
    def setUp(self) -> None:
        self.reception = StaffUser.objects.create_user(
            username="adm-reopen-rec",
            email="adm-reopen-rec@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.reception, "Reception")
        self.doctor = StaffUser.objects.create_user(
            username="adm-reopen-doc",
            email="adm-reopen-doc@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.doctor, "Doctor")
        self.superuser = StaffUser.objects.create_superuser(
            username="adm-reopen-su",
            email="adm-reopen-su@example.com",
            password="x",
        )
        clinic = ClinicSite.objects.create(code="AR", name="Admin reopen clinic")
        room = ConsultingRoom.objects.create(
            clinic_site=clinic, code="R1", name="Room 1"
        )
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            created_by_user=self.reception,
        )
        patient = Patient.objects.create(
            first_name="A",
            last_name="B",
            date_of_birth=date(1991, 1, 1),
            phone="+48111222333",
            email="adm-reopen-patient@example.com",
        )
        self.entry = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
            position_no=1,
            created_by_user=self.reception,
        )
        self.session = PatientFormSession.objects.create(
            queue_entry=self.entry,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=self.reception,
        )

    def _submitted_form(self) -> PatientIntakeForm:
        return PatientIntakeForm.objects.create(
            queue_entry=self.entry,
            session=self.session,
            form_status=IntakeStatus.SUBMITTED,
            submitted_at=timezone.now(),
            signature_sha256="c" * 64,
        )

    def test_reopen_action_permission_denied_for_doctor(self) -> None:
        admin_inst = PatientIntakeFormAdmin(PatientIntakeForm, admin.site)
        req = _request_with_messages(self.doctor)
        admin_inst.reopen_intake_for_patient_editing(
            req, PatientIntakeForm.objects.none()
        )
        stored = list(req._messages)
        self.assertTrue(stored)
        self.assertEqual(stored[0].level, messages.ERROR)

    def test_reopen_action_skips_already_reopened_form(self) -> None:
        form = PatientIntakeForm.objects.create(
            queue_entry=self.entry,
            session=self.session,
            form_status=IntakeStatus.REOPENED,
            submitted_at=timezone.now(),
            signature_sha256="d" * 64,
        )
        admin_inst = PatientIntakeFormAdmin(PatientIntakeForm, admin.site)
        req = _request_with_messages(self.superuser)
        admin_inst.reopen_intake_for_patient_editing(
            req, PatientIntakeForm.objects.filter(pk=form.pk)
        )
        stored = list(req._messages)
        self.assertTrue(stored)
        self.assertEqual(stored[0].level, messages.WARNING)

    def test_reopen_action_via_changelist_post_succeeds_for_superuser(self) -> None:
        form = self._submitted_form()
        client = Client()
        client.force_login(self.superuser)
        url = reverse("admin:intake_patientintakeform_changelist")
        response = client.post(
            url,
            {
                "action": "reopen_intake_for_patient_editing",
                "_selected_action": [str(form.pk)],
                "index": "0",
            },
        )
        self.assertEqual(response.status_code, 302)
        form.refresh_from_db()
        self.assertEqual(form.form_status, IntakeStatus.REOPENED)


class PatientIntakeFormAdminReceptionNoteTests(TestCase):
    """Saving Empfangsnotiz must work when body_map_data is empty []."""

    def setUp(self) -> None:
        self.superuser = StaffUser.objects.create_superuser(
            username="adm-note-su",
            email="adm-note-su@example.com",
            password="x",
        )
        clinic = ClinicSite.objects.create(code="AN", name="Admin note clinic")
        room = ConsultingRoom.objects.create(
            clinic_site=clinic, code="R1", name="Room 1"
        )
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            created_by_user=self.superuser,
        )
        patient = Patient.objects.create(
            first_name="Kolja",
            last_name="Holtz",
            date_of_birth=date(1951, 2, 1),
            phone="+48111222334",
            email="adm-note-patient@example.com",
        )
        self.entry = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
            position_no=1,
            created_by_user=self.superuser,
        )
        self.session = PatientFormSession.objects.create(
            queue_entry=self.entry,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=self.superuser,
        )
        self.intake = PatientIntakeForm.objects.create(
            queue_entry=self.entry,
            session=self.session,
            form_status=IntakeStatus.SUBMITTED,
            submitted_at=timezone.now(),
            signature_sha256="e" * 64,
            body_map_schema_version=0,
            body_map_data=[],
            anamnesis_schema_version=1,
            anamnesis_payload={"schema_version": 1, "answers": []},
        )

    def test_empty_body_map_json_is_valid_on_model_form(self) -> None:
        """Regression: Django JSONField treats [] as empty; blank=True must allow it."""
        from django.forms import modelform_factory

        Form = modelform_factory(
            PatientIntakeForm, fields=("body_map_data", "anamnesis_payload")
        )
        form = Form(
            data={"body_map_data": "[]", "anamnesis_payload": "{}"},
            instance=self.intake,
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_admin_save_stamps_reception_note_audit_fields(self) -> None:
        admin_inst = PatientIntakeFormAdmin(PatientIntakeForm, admin.site)
        req = _request_with_messages(self.superuser)
        note = (
            "Patient besorgt wegen Stellen auf der Kopfhaut; "
            "frühere aktinische Keratose."
        )
        Form = admin_inst.get_form(req, obj=self.intake)
        submitted = timezone.localtime(self.intake.submitted_at)
        form = Form(
            data={
                "queue_entry": str(self.entry.pk),
                "session": str(self.session.pk),
                "form_status": IntakeStatus.SUBMITTED,
                "submitted_at_0": submitted.strftime("%d.%m.%Y"),
                "submitted_at_1": submitted.strftime("%H:%M:%S"),
                "reception_note": note,
                "signature_file_path": "",
                "signature_sha256": "e" * 64,
            },
            instance=self.intake,
        )
        self.assertTrue(form.is_valid(), form.errors)
        obj = form.save(commit=False)
        admin_inst.save_model(req, obj, form, change=True)
        self.intake.refresh_from_db()
        self.assertEqual(self.intake.reception_note, note)
        self.assertEqual(self.intake.body_map_data, [])
        self.assertIsNotNone(self.intake.reception_note_updated_at)
        self.assertEqual(self.intake.reception_note_updated_by_id, self.superuser.id)

    def test_admin_change_view_posts_reception_note_with_empty_body_map(self) -> None:
        client = Client()
        client.force_login(self.superuser)
        url = reverse(
            "admin:intake_patientintakeform_change", args=[self.intake.pk]
        )
        note = "Empfangsnotiz für den Arzt"
        submitted = timezone.localtime(self.intake.submitted_at)
        response = client.post(
            url,
            {
                "queue_entry": str(self.entry.pk),
                "session": str(self.session.pk),
                "form_status": IntakeStatus.SUBMITTED,
                "submitted_at_0": submitted.strftime("%d.%m.%Y"),
                "submitted_at_1": submitted.strftime("%H:%M:%S"),
                "reception_note": note,
                "signature_file_path": "",
                "signature_sha256": "e" * 64,
                "_save": "Save",
            },
        )
        if response.status_code != 302:
            errors = {}
            if hasattr(response, "context") and response.context:
                adminform = response.context.get("adminform")
                if adminform is not None:
                    errors = dict(adminform.form.errors)
            self.fail(f"expected redirect, got {response.status_code}: {errors}")
        self.intake.refresh_from_db()
        self.assertEqual(self.intake.reception_note, note)
        self.assertEqual(self.intake.body_map_data, [])
        self.assertEqual(self.intake.reception_note_updated_by_id, self.superuser.id)
