"""Smoke tests for cogitomedica/doctor_views.py."""

from __future__ import annotations

import json
import re
from datetime import date, timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import Client, TestCase
from django.utils import timezone

from apps.core.api_utils import assign_group_to_test_user
from apps.intake.models import IntakeStatus, PatientIntakeForm
from apps.operations.models import AuditEvent
from apps.medical.external_pdf_service import GateResult
from apps.medical.models import (
    DocVersionStatus,
    MedicalDocStatus,
    MedicalDocument,
    MedicalDocumentSourceType,
    MedicalDocumentVersion,
    PaperIntakeAuthorization,
    PdfStatus,
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


class DoctorViewsSmokeTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.password = "test-pass"
        self.doctor = StaffUser.objects.create_user(
            username="doc",
            email="doc@example.com",
            password=self.password,
            is_staff=True,
        )
        assign_group_to_test_user(self.doctor, "Doctor")

        self.reception_user = StaffUser.objects.create_user(
            username="rec",
            email="rec@example.com",
            password=self.password,
            is_staff=True,
        )
        assign_group_to_test_user(self.reception_user, "Reception")

        self.manager_user = StaffUser.objects.create_user(
            username="mgr",
            email="mgr@example.com",
            password=self.password,
            is_staff=True,
        )
        assign_group_to_test_user(self.manager_user, "Manager")

    # -- helpers ------------------------------------------------

    def _login_doctor(self):
        self.client.force_login(self.doctor)

    def _assert_paper_intake_modal_markup(self, html: str) -> None:
        """Regression: in-page modal for paper create; no native window.confirm."""
        self.assertIn('id="paper-intake-confirm-modal"', html)
        self.assertIn("js-paper-intake-create-form", html)
        self.assertNotIn(
            "window.confirm",
            html,
            msg="Paper intake create must not use browser native confirm().",
        )

    # ==========================================================
    # Login
    # ==========================================================

    def test_login_get_returns_200(self):
        resp = self.client.get("/doctor/login/")
        self.assertEqual(resp.status_code, 200)

    def test_login_post_valid_doctor_redirects(self):
        resp = self.client.post(
            "/doctor/login/",
            {"username": "doc", "password": self.password},
        )
        self.assertEqual(resp.status_code, 302)

    def test_login_post_valid_manager_redirects(self):
        resp = self.client.post(
            "/doctor/login/",
            {"username": "mgr", "password": self.password},
        )
        self.assertEqual(resp.status_code, 302)

    # ==========================================================
    # Guard: anonymous and wrong role
    # ==========================================================

    def test_list_anonymous_redirects_to_login(self):
        resp = self.client.get("/doctor/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp.url)

    def test_list_reception_user_redirects(self):
        self.client.force_login(self.reception_user)
        resp = self.client.get("/doctor/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp.url)

    # ==========================================================
    # List
    # ==========================================================

    def test_list_doctor_returns_200(self):
        self._login_doctor()
        resp = self.client.get("/doctor/")
        self.assertEqual(resp.status_code, 200)

    def test_list_includes_published_by_doctor_select(self) -> None:
        self._login_doctor()
        resp = self.client.get("/doctor/")
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('name="published_by_user_id"', html)
        self.assertIn('id="id_published_by_user_id"', html)

    def test_list_manager_returns_200(self):
        self.client.force_login(self.manager_user)
        resp = self.client.get("/doctor/")
        self.assertEqual(resp.status_code, 200)

    def test_list_lang_param_strips_and_redirects(self):
        self._login_doctor()
        resp = self.client.get("/doctor/?lang=pl")
        self.assertEqual(resp.status_code, 302)

    # ==========================================================
    # Logout
    # ==========================================================

    def test_logout_post_redirects_to_login(self):
        self._login_doctor()
        resp = self.client.post("/doctor/logout/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp.url)

    # ==========================================================
    # Document detail – nonexistent UUID
    # ==========================================================

    def test_detail_nonexistent_returns_404(self):
        self._login_doctor()
        url = f"/doctor/{uuid4()}/"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)

    # ==========================================================
    # Open by queue – nonexistent UUID
    # ==========================================================

    def test_open_by_queue_nonexistent_returns_error(self):
        self._login_doctor()
        url = f"/doctor/open/{uuid4()}/"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)

    def test_open_by_queue_returns_400_when_intake_reopened(self):
        """Befund must not be created while intake is REOPENED (patient editing again)."""
        self._login_doctor()
        clinic = ClinicSite.objects.create(code="RO", name="Reopen Open Clinic")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="R1", name="R1")
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            assigned_doctor=self.doctor,
            created_by_user=self.reception_user,
        )
        patient = Patient.objects.create(
            first_name="Pat",
            last_name="ReopenBlock",
            date_of_birth=date(1990, 1, 1),
            phone="+48500999111",
            email="reopenblock@example.com",
        )
        entry = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
            position_no=1,
            created_by_user=self.reception_user,
        )
        session = PatientFormSession.objects.create(
            queue_entry=entry,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=self.reception_user,
        )
        PatientIntakeForm.objects.create(
            queue_entry=entry,
            session=session,
            form_status=IntakeStatus.REOPENED,
            submitted_at=timezone.now(),
            signature_sha256="b" * 64,
        )
        resp = self.client.get(f"/doctor/open/{entry.id}/?lang=en")
        self.assertEqual(resp.status_code, 400)
        self.assertIn(b"reopened", resp.content.lower())

    def test_open_by_queue_external_upload_redirects_skips_create_or_get(
        self,
    ) -> None:
        """Reception external-upload doc on REOPENED intake: doctor opens detail, no Befund create."""
        from apps.medical.services import create_external_upload_medical_document

        self._login_doctor()
        clinic = ClinicSite.objects.create(code="EU", name="Ext Upload Open Clinic")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="E1", name="E1")
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            assigned_doctor=self.doctor,
            created_by_user=self.reception_user,
        )
        patient = Patient.objects.create(
            first_name="Pat",
            last_name="ExtUploadOpen",
            date_of_birth=date(1991, 6, 6),
            phone="+48500111222",
            email="extuploadopen@example.com",
        )
        entry = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
            position_no=1,
            created_by_user=self.reception_user,
        )
        session = PatientFormSession.objects.create(
            queue_entry=entry,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=self.reception_user,
        )
        PatientIntakeForm.objects.create(
            queue_entry=entry,
            session=session,
            form_status=IntakeStatus.REOPENED,
            submitted_at=timezone.now(),
            signature_sha256="b" * 64,
        )
        ext_doc = create_external_upload_medical_document(
            queue_entry_id=entry.id,
            created_by_user_id=self.reception_user.id,
        )
        self.assertEqual(ext_doc.source_type, MedicalDocumentSourceType.EXTERNAL_UPLOAD)

        with patch("cogitomedica.doctor_views.create_or_get_medical_document") as m_cog:
            resp = self.client.get(f"/doctor/open/{entry.id}/?lang=en")
            m_cog.assert_not_called()

        self.assertEqual(resp.status_code, 302)
        self.assertIn(f"/doctor/{ext_doc.id}/", resp.url)
        self.assertIn("lang=en", resp.url)

    def test_open_by_queue_returns_400_when_intake_in_progress(self) -> None:
        """Befund creation requires SUBMITTED intake, not IN_PROGRESS."""
        self._login_doctor()
        clinic = ClinicSite.objects.create(code="IP", name="In Progress Clinic")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="R1", name="R1")
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            assigned_doctor=self.doctor,
            created_by_user=self.reception_user,
        )
        patient = Patient.objects.create(
            first_name="Pat",
            last_name="InProgress",
            date_of_birth=date(1992, 2, 2),
            phone="+48500888777",
            email="inprogress@example.com",
        )
        entry = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
            position_no=1,
            created_by_user=self.reception_user,
        )
        session = PatientFormSession.objects.create(
            queue_entry=entry,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=self.reception_user,
        )
        PatientIntakeForm.objects.create(
            queue_entry=entry,
            session=session,
            form_status=IntakeStatus.IN_PROGRESS,
        )
        resp = self.client.get(f"/doctor/open/{entry.id}/?lang=en")
        self.assertEqual(resp.status_code, 400)
        self.assertIn(b"completed", resp.content.lower())

    def test_open_by_queue_without_intake_returns_400_no_auto_document(self) -> None:
        self._login_doctor()
        clinic = ClinicSite.objects.create(code="NO", name="No Intake Clinic")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="R1", name="R1")
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            assigned_doctor=self.doctor,
            created_by_user=self.reception_user,
        )
        patient = Patient.objects.create(
            first_name="Pat",
            last_name="PaperFlow",
            date_of_birth=date(1995, 3, 3),
            phone="+48500777666",
            email="paperflow@example.com",
        )
        entry = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=1,
            appointment_time=timezone.now() - timedelta(hours=4),
            created_by_user=self.reception_user,
        )

        resp = self.client.get(f"/doctor/open/{entry.id}/?lang=en")
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(MedicalDocument.objects.filter(queue_entry=entry).exists())
        self.assertIn(b"questionnaire", resp.content.lower())

    def test_open_by_queue_without_intake_early_appointment_still_returns_400(
        self,
    ) -> None:
        self._login_doctor()
        clinic = ClinicSite.objects.create(code="N3", name="No Intake Guard Clinic")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="R1", name="R1")
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            assigned_doctor=self.doctor,
            created_by_user=self.reception_user,
        )
        patient = Patient.objects.create(
            first_name="Pat",
            last_name="TooEarly",
            date_of_birth=date(1996, 4, 4),
            phone="+48500666555",
            email="tooearly@example.com",
        )
        entry = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=1,
            appointment_time=timezone.now() - timedelta(hours=1),
            created_by_user=self.reception_user,
        )

        resp = self.client.get(f"/doctor/open/{entry.id}/?lang=en")
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(MedicalDocument.objects.filter(queue_entry=entry).exists())

    def test_open_by_queue_without_intake_with_paper_authorization_returns_action_page(
        self,
    ) -> None:
        self._login_doctor()
        clinic = ClinicSite.objects.create(code="PA", name="Paper Auth Clinic")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="R1", name="R1")
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            assigned_doctor=self.doctor,
            created_by_user=self.reception_user,
        )
        patient = Patient.objects.create(
            first_name="Pat",
            last_name="AuthorizedPaper",
            date_of_birth=date(1993, 3, 3),
            phone="+48500555444",
            email="authorizedpaper@example.com",
        )
        entry = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=1,
            appointment_time=timezone.now() - timedelta(hours=4),
            created_by_user=self.reception_user,
        )
        PaperIntakeAuthorization.objects.create(
            queue_entry=entry,
            authorized_at=timezone.now(),
            authorized_by=self.manager_user,
            reason="Patient delivered paper intake",
        )

        list_resp = self.client.get("/doctor/?lang=en")
        self.assertEqual(list_resp.status_code, 302)
        list_resp = self.client.get("/doctor/")
        self.assertEqual(list_resp.status_code, 200)
        self.assertIn(
            f"/doctor/open/{entry.id}/create-no-intake/", list_resp.content.decode()
        )

        resp = self.client.get(f"/doctor/open/{entry.id}/?lang=en")
        self.assertEqual(resp.status_code, 200)
        lowered = resp.content.lower()
        self.assertTrue(
            b"paper" in lowered or b"papier" in lowered,
            msg="Expected paper-intake wording (EN or DE) in the no-intake action page.",
        )
        self.assertIn(b"create-no-intake", lowered)

    def test_paper_intake_create_confirm_modal_on_list_and_no_intake_page(self) -> None:
        """List + no-intake action page embed shared modal; forms use JS hook, not window.confirm."""
        self._login_doctor()
        clinic = ClinicSite.objects.create(code="PM", name="Paper Modal Clinic")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="R1", name="R1")
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            assigned_doctor=self.doctor,
            created_by_user=self.reception_user,
        )
        patient = Patient.objects.create(
            first_name="Pat",
            last_name="ModalPaper",
            date_of_birth=date(1992, 2, 2),
            phone="+48500333222",
            email="modalpaper@example.com",
        )
        entry = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=1,
            appointment_time=timezone.now() - timedelta(hours=4),
            created_by_user=self.reception_user,
        )
        PaperIntakeAuthorization.objects.create(
            queue_entry=entry,
            authorized_at=timezone.now(),
            authorized_by=self.manager_user,
            reason="Patient delivered paper intake for modal regression test",
        )

        list_resp = self.client.get("/doctor/")
        self.assertEqual(list_resp.status_code, 200)
        self._assert_paper_intake_modal_markup(list_resp.content.decode())

        action_resp = self.client.get(f"/doctor/open/{entry.id}/?lang=en")
        self.assertEqual(action_resp.status_code, 200)
        self._assert_paper_intake_modal_markup(action_resp.content.decode())

    def test_post_create_no_intake_creates_document_and_redirects_to_detail(
        self,
    ) -> None:
        self._login_doctor()
        clinic = ClinicSite.objects.create(code="PC", name="Paper Create Clinic")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="R1", name="R1")
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            assigned_doctor=self.doctor,
            created_by_user=self.reception_user,
        )
        patient = Patient.objects.create(
            first_name="Pat",
            last_name="CreatePaper",
            date_of_birth=date(1991, 8, 8),
            phone="+48500444333",
            email="createpaper@example.com",
        )
        entry = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=1,
            appointment_time=timezone.now() - timedelta(hours=4),
            created_by_user=self.reception_user,
        )
        PaperIntakeAuthorization.objects.create(
            queue_entry=entry,
            authorized_at=timezone.now(),
            authorized_by=self.manager_user,
            reason="Patient delivered paper intake",
        )

        resp = self.client.post(f"/doctor/open/{entry.id}/create-no-intake/?lang=en")

        self.assertEqual(resp.status_code, 302)
        doc = MedicalDocument.objects.get(queue_entry=entry)
        self.assertEqual(doc.source_type, MedicalDocumentSourceType.PAPER_INTAKE)
        self.assertIsNone(doc.intake_form_id)
        self.assertIn(f"/doctor/{doc.id}/?lang=en", resp.url)

    def test_paper_intake_document_detail_panel_has_paper_context_and_ui_keys(
        self,
    ) -> None:
        """Befund detail for PAPER_INTAKE: panel JSON exposes auth snapshot + new UI keys."""
        gate_patcher = patch(
            "cogitomedica.doctor_views.check_external_pdf_gate",
            return_value=GateResult(
                True,
                (),
                None,
                skip_attachment_sync=False,
            ),
        )
        gate_patcher.start()
        self.addCleanup(gate_patcher.stop)

        self._login_doctor()
        clinic = ClinicSite.objects.create(code="PD", name="Paper Detail Clinic")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="R1", name="R1")
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            assigned_doctor=self.doctor,
            created_by_user=self.reception_user,
        )
        patient = Patient.objects.create(
            first_name="Pat",
            last_name="DetailPaper",
            date_of_birth=date(1990, 1, 2),
            phone="+48500111222",
            email="detailpaper@example.com",
        )
        entry = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=1,
            appointment_time=timezone.now() - timedelta(hours=4),
            created_by_user=self.reception_user,
        )
        PaperIntakeAuthorization.objects.create(
            queue_entry=entry,
            authorized_at=timezone.now(),
            authorized_by=self.manager_user,
            reason="Patient delivered paper intake",
        )
        post_resp = self.client.post(
            f"/doctor/open/{entry.id}/create-no-intake/?lang=en",
        )
        self.assertEqual(post_resp.status_code, 302)
        doc = MedicalDocument.objects.get(queue_entry=entry)

        detail_resp = self.client.get(f"/doctor/{doc.id}/?lang=en")
        self.assertEqual(detail_resp.status_code, 200)
        html = detail_resp.content.decode()
        self.assertIn('id="paper-intake-meta"', html)
        m = re.search(
            r'<script[^>]*id="doctor-panel-data"[^>]*>(.*?)</script>',
            html,
            re.DOTALL,
        )
        assert m is not None, "expected doctor-panel-data script in HTML"
        panel = json.loads(m.group(1))
        self.assertEqual(panel["context"]["source_type"], "PAPER_INTAKE")
        auth = panel["context"]["paper_intake_authorization"]
        self.assertIsNotNone(auth)
        self.assertEqual(auth.get("reason"), "Patient delivered paper intake")
        self.assertEqual(
            auth.get("authorized_by_username"),
            self.manager_user.username,
        )
        ui = panel["ui"]
        self.assertIn("detail_paper_intake_notice", ui)
        self.assertIn("detail_paper_auth_heading", ui)
        self.assertTrue(len(ui.get("detail_paper_intake_notice", "")) > 5)

    def test_paper_intake_document_detail_returns_422_when_audit_snapshot_missing(
        self,
    ) -> None:
        gate_patcher = patch(
            "cogitomedica.doctor_views.check_external_pdf_gate",
            return_value=GateResult(
                True,
                (),
                None,
                skip_attachment_sync=False,
            ),
        )
        gate_patcher.start()
        self.addCleanup(gate_patcher.stop)

        self._login_doctor()
        clinic = ClinicSite.objects.create(code="PX", name="Paper Missing Audit Clinic")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="R1", name="R1")
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            assigned_doctor=self.doctor,
            created_by_user=self.reception_user,
        )
        patient = Patient.objects.create(
            first_name="Pat",
            last_name="NoAuditSnap",
            date_of_birth=date(1988, 8, 8),
            phone="+48500222333",
            email="noauditsnap@example.com",
        )
        entry = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=1,
            appointment_time=timezone.now() - timedelta(hours=4),
            created_by_user=self.reception_user,
        )
        PaperIntakeAuthorization.objects.create(
            queue_entry=entry,
            authorized_at=timezone.now(),
            authorized_by=self.manager_user,
            reason="Patient delivered paper intake for missing-audit test",
        )
        post_resp = self.client.post(
            f"/doctor/open/{entry.id}/create-no-intake/?lang=en",
        )
        self.assertEqual(post_resp.status_code, 302)
        doc = MedicalDocument.objects.get(queue_entry=entry)
        AuditEvent.objects.filter(
            medical_document_id=doc.id,
            event_type="MEDICAL_DOCUMENT_CREATED_WITHOUT_INTAKE",
        ).delete()
        detail_resp = self.client.get(f"/doctor/{doc.id}/?lang=en")
        self.assertEqual(detail_resp.status_code, 422)
        self.assertIn(b"audit", detail_resp.content.lower())

    def test_open_by_queue_returns_404_when_published_document_not_accessible(
        self,
    ) -> None:
        """Another doctor must not open queue entry guarded by published document."""
        other = StaffUser.objects.create_user(
            username="doc-other-queue",
            email="doc.other.queue@example.com",
            password=self.password,
            is_staff=True,
        )
        assign_group_to_test_user(other, "Doctor")
        self._login_doctor()
        clinic = ClinicSite.objects.create(code="NA", name="No Access Clinic")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="R1", name="R1")
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            assigned_doctor=self.doctor,
            created_by_user=self.reception_user,
        )
        patient = Patient.objects.create(
            first_name="Pat",
            last_name="NoAccessQueue",
            date_of_birth=date(1994, 4, 4),
            phone="+48500333222",
            email="noaccessqueue@example.com",
        )
        entry = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
            position_no=1,
            created_by_user=self.reception_user,
        )
        session = PatientFormSession.objects.create(
            queue_entry=entry,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=self.reception_user,
        )
        intake = PatientIntakeForm.objects.create(
            queue_entry=entry,
            session=session,
            form_status=IntakeStatus.SUBMITTED,
            submitted_at=timezone.now(),
            signature_sha256="c" * 64,
        )
        MedicalDocument.objects.create(
            queue_entry=entry,
            intake_form=intake,
            status=MedicalDocStatus.PUBLISHED,
            current_version_no=1,
            created_by_user=self.doctor,
        )
        self.client.force_login(other)
        resp = self.client.get(f"/doctor/open/{entry.id}/?lang=en")
        self.assertEqual(resp.status_code, 404)

    def test_create_no_intake_shows_error_when_appointment_too_recent(self) -> None:
        self._login_doctor()
        clinic = ClinicSite.objects.create(code="TE", name="Too Early Create Clinic")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="R1", name="R1")
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            assigned_doctor=self.doctor,
            created_by_user=self.reception_user,
        )
        patient = Patient.objects.create(
            first_name="Pat",
            last_name="TooEarlyCreate",
            date_of_birth=date(1995, 5, 5),
            phone="+48500222111",
            email="tooearlycreate@example.com",
        )
        entry = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=1,
            appointment_time=timezone.now() - timedelta(hours=1),
            created_by_user=self.reception_user,
        )
        PaperIntakeAuthorization.objects.create(
            queue_entry=entry,
            authorized_at=timezone.now(),
            authorized_by=self.manager_user,
            reason="Patient delivered paper intake for early-create test.",
        )
        resp = self.client.post(f"/doctor/open/{entry.id}/create-no-intake/?lang=en")
        self.assertEqual(resp.status_code, 400)
        self.assertContains(resp, "create-no-intake", status_code=400)


class DoctorDetailHappyPathTests(TestCase):
    """Full data chain for the document detail view."""

    def setUp(self):
        self.client = Client()
        self.doctor = StaffUser.objects.create_user(
            username="hp-doc",
            email="hp-doc@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.doctor, "Doctor")

        rec = StaffUser.objects.create_user(
            username="hp-rec",
            email="hp-rec@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(rec, "Reception")

        clinic = ClinicSite.objects.create(code="HP", name="HP Clinic")
        room = ConsultingRoom.objects.create(
            clinic_site=clinic, code="R1", name="Room 1"
        )
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            assigned_doctor=self.doctor,
            created_by_user=rec,
        )
        patient = Patient.objects.create(
            first_name="Jan",
            last_name="Kowalski",
            date_of_birth=date(1985, 6, 15),
            phone="+48500100200",
            email="jan@example.com",
        )
        qe = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
            position_no=1,
            created_by_user=rec,
        )
        sess = PatientFormSession.objects.create(
            queue_entry=qe,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=rec,
        )
        intake = PatientIntakeForm.objects.create(
            queue_entry=qe,
            session=sess,
            form_status=IntakeStatus.SUBMITTED,
            submitted_at=timezone.now(),
            signature_sha256="a" * 64,
            body_map_data=[
                {"x": 0.22, "y": 0.35, "side": "front"},
                {"x": 0.72, "y": 0.4, "side": "back"},
            ],
        )
        self.doc = MedicalDocument.objects.create(
            queue_entry=qe,
            intake_form=intake,
            status=MedicalDocStatus.DRAFT,
            current_version_no=0,
            created_by_user=self.doctor,
        )
        # Default HiDrive /incoming listing is empty in tests → real gate would return 424.
        gate_patcher = patch(
            "cogitomedica.doctor_views.check_external_pdf_gate",
            return_value=GateResult(
                True,
                (),
                None,
                skip_attachment_sync=False,
            ),
        )
        gate_patcher.start()
        self.addCleanup(gate_patcher.stop)

    def test_detail_happy_path_returns_200(self):
        self.client.force_login(self.doctor)
        url = f"/doctor/{self.doc.id}/"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    @patch("cogitomedica.doctor_views.check_external_pdf_gate")
    def test_detail_shows_hidrive_soft_warning_banner(
        self, mock_gate: MagicMock
    ) -> None:
        """Non-blocking HiDrive outage: gate passes but UI shows translated warning."""
        mock_gate.return_value = GateResult(
            True,
            (),
            "HiDrive folder read failed (test).",
            skip_attachment_sync=True,
        )
        self.client.force_login(self.doctor)
        resp = self.client.get(f"/doctor/{self.doc.id}/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("HiDrive folder read failed (test).", resp.content.decode())

    def test_detail_panel_includes_body_map_image_url_and_stored_points(self):
        self.client.force_login(self.doctor)
        url = f"/doctor/{self.doc.id}/"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        m = re.search(
            r'<script[^>]*id="doctor-panel-data"[^>]*>(.*?)</script>',
            html,
            re.DOTALL,
        )
        assert m is not None, "expected doctor-panel-data script in HTML"
        panel = json.loads(m.group(1))
        self.assertIn("bodyMapImageUrl", panel)
        self.assertIn("tablet/body.jpg", panel["bodyMapImageUrl"])
        pts = panel["context"]["intake_summary"]["body_map_data"]
        self.assertEqual(len(pts), 2)
        self.assertEqual(pts[0]["side"], "front")

    def test_detail_returns_423_when_locked_by_another_doctor(self):
        other = StaffUser.objects.create_user(
            username="hp-doc-2",
            email="hp-doc-2@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(other, "Doctor")
        dq = self.doc.queue_entry.daily_queue
        dq.assigned_doctor = other
        dq.save(update_fields=["assigned_doctor", "updated_at"])
        self.doc.locked_by_user = self.doctor
        self.doc.locked_at = timezone.now()
        self.doc.save(update_fields=["locked_by_user", "locked_at", "updated_at"])

        self.client.force_login(other)
        url = f"/doctor/{self.doc.id}/"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 423)

    def test_second_doctor_can_open_draft_without_queue_assignment(self):
        dq = self.doc.queue_entry.daily_queue
        dq.assigned_doctor = None
        dq.save(update_fields=["assigned_doctor", "updated_at"])
        other = StaffUser.objects.create_user(
            username="hp-doc-shared",
            email="hp-doc-shared@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(other, "Doctor")
        self.client.force_login(other)
        resp = self.client.get(f"/doctor/{self.doc.id}/")
        self.assertEqual(resp.status_code, 200)

    @patch(
        "cogitomedica.doctor_views.check_external_pdf_gate",
        return_value=GateResult(
            False,
            (),
            "GATE_BLOCKED",
            skip_attachment_sync=False,
        ),
    )
    def test_detail_returns_424_when_external_pdf_gate_blocks(
        self,
        _mock_gate: MagicMock,
    ) -> None:
        self.client.force_login(self.doctor)
        resp = self.client.get(f"/doctor/{self.doc.id}/")
        self.assertEqual(resp.status_code, 424)
        self.assertIn("GATE_BLOCKED", resp.content.decode())

    @patch(
        "cogitomedica.doctor_views.check_external_pdf_gate",
        return_value=GateResult(
            False,
            (),
            "GATE_BLOCKED",
            skip_attachment_sync=False,
        ),
    )
    def test_detail_bypasses_external_pdf_gate_for_published_document(
        self,
        mock_gate: MagicMock,
    ) -> None:
        self.doc.status = MedicalDocStatus.PUBLISHED
        self.doc.save(update_fields=["status", "updated_at"])

        self.client.force_login(self.doctor)
        resp = self.client.get(f"/doctor/{self.doc.id}/")

        self.assertEqual(resp.status_code, 200)
        mock_gate.assert_not_called()

    @patch(
        "cogitomedica.doctor_views.get_medical_document_context",
        return_value={"intake_summary": {"patient": {}}},
    )
    def test_detail_returns_404_when_intake_patient_id_missing(
        self,
        _mock_ctx: MagicMock,
    ) -> None:
        self.client.force_login(self.doctor)
        resp = self.client.get(f"/doctor/{self.doc.id}/")
        self.assertEqual(resp.status_code, 404)


class DoctorListScopeAndPreviewTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.doctor = StaffUser.objects.create_user(
            username="scope-doc",
            email="scope-doc@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.doctor, "Doctor")
        self.other_doctor = StaffUser.objects.create_user(
            username="scope-doc-other",
            email="scope-doc-other@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.other_doctor, "Doctor")
        self.reception = StaffUser.objects.create_user(
            username="scope-rec",
            email="scope-rec@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.reception, "Reception")
        self.clinic = ClinicSite.objects.create(code="SC", name="Scope Clinic")
        self.room = ConsultingRoom.objects.create(
            clinic_site=self.clinic,
            code="R1",
            name="Room 1",
        )

    def _create_published_document(
        self,
        *,
        patient_last_name: str,
        published_by: StaffUser,
        queue_assigned_doctor: StaffUser | None = None,
    ) -> MedicalDocument:
        patient = Patient.objects.create(
            first_name="Jan",
            last_name=patient_last_name,
            date_of_birth=date(1985, 6, 15),
            phone=f"+48500{uuid4().int % 1000000:06d}",
            email=f"{patient_last_name.lower()}@example.com",
        )
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date()
            + timedelta(days=DailyQueue.objects.count()),
            clinic_site=self.clinic,
            consulting_room=self.room,
            status=QueueStatus.OPEN,
            assigned_doctor=queue_assigned_doctor,
            created_by_user=self.reception,
        )
        entry = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
            position_no=1,
            created_by_user=self.reception,
        )
        session = PatientFormSession.objects.create(
            queue_entry=entry,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=self.reception,
        )
        intake = PatientIntakeForm.objects.create(
            queue_entry=entry,
            session=session,
            form_status=IntakeStatus.SUBMITTED,
            submitted_at=timezone.now(),
            signature_sha256="a" * 64,
            body_map_data=[],
        )
        doc = MedicalDocument.objects.create(
            queue_entry=entry,
            intake_form=intake,
            status=MedicalDocStatus.PUBLISHED,
            current_version_no=1,
            created_by_user=self.reception,
            updated_by_user=published_by,
        )
        MedicalDocumentVersion.objects.create(
            medical_document=doc,
            version_no=1,
            version_status=DocVersionStatus.PUBLISHED,
            pdf_generation_status=PdfStatus.COMPLETED,
            medical_payload_schema_version=1,
            medical_payload={"schema_version": 1},
            pdf_local_path="/media/befund/test.pdf",
            publish_request_id=uuid4(),
            published_at=timezone.now(),
            publish_locale="de-DE",
            published_by_user=published_by,
        )
        return doc

    def test_default_list_keeps_published_document_visible_for_publishing_doctor(self):
        published_doc = self._create_published_document(
            patient_last_name="HistoryVisible",
            published_by=self.doctor,
            queue_assigned_doctor=self.other_doctor,
        )
        self.client.force_login(self.doctor)

        response = self.client.get("/doctor/")

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("HistoryVisible", html)
        self.assertIn(
            f"/api/v1/medical-documents/{published_doc.id}/preview-pdf",
            html,
        )

    def test_scope_published_by_me_filters_list_and_keeps_preview_link(self):
        matching_doc = self._create_published_document(
            patient_last_name="PublishedByMe",
            published_by=self.doctor,
            queue_assigned_doctor=self.other_doctor,
        )
        self._create_published_document(
            patient_last_name="PublishedByOther",
            published_by=self.other_doctor,
            queue_assigned_doctor=self.other_doctor,
        )
        self.client.force_login(self.doctor)

        response = self.client.get("/doctor/?scope=published_by_me")

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("PublishedByMe", html)
        self.assertNotIn("PublishedByOther", html)
        self.assertIn('option value="published_by_me" selected', html)
        self.assertIn(
            f"/api/v1/medical-documents/{matching_doc.id}/preview-pdf",
            html,
        )

    def test_scope_in_revision_filters_pending_revision_rows(self) -> None:
        rev_doc = self._create_published_document(
            patient_last_name="InRevisionOnly",
            published_by=self.doctor,
            queue_assigned_doctor=self.doctor,
        )
        MedicalDocument.objects.filter(pk=rev_doc.pk).update(has_pending_revision=True)
        self._create_published_document(
            patient_last_name="PublishedStable",
            published_by=self.doctor,
            queue_assigned_doctor=self.doctor,
        )
        self.client.force_login(self.doctor)

        response = self.client.get("/doctor/?scope=in_revision")

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("InRevisionOnly", html)
        self.assertNotIn("PublishedStable", html)
        self.assertIn('option value="in_revision" selected', html)
