from __future__ import annotations

from datetime import date, timedelta

from django.test import Client, RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.api_utils import assign_group_to_test_user
from apps.intake.models import IntakeStatus, PatientIntakeForm
from apps.reception import external_upload_admin_views as ext_hub_views
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


class ExternalUploadAdminHubViewsTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.factory = RequestFactory()
        self.reception = StaffUser.objects.create_user(
            username="rec-ext-ui",
            email="rec.ext.ui@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.reception, "Reception")
        self.admin = StaffUser.objects.create_user(
            username="adm-ext-ui",
            email="adm.ext.ui@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.admin, "Admin")
        self.doctor = StaffUser.objects.create_user(
            username="doc-ext-ui",
            email="doc.ext.ui@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.doctor, "Doctor")

        self.clinic = ClinicSite.objects.create(code="EUI", name="External UI Clinic")
        self.reception.clinic_sites.add(self.clinic)
        room = ConsultingRoom.objects.create(
            clinic_site=self.clinic, code="E1", name="E1"
        )
        self.queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=self.clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            created_by_user=self.reception,
            assigned_doctor=self.doctor,
        )
        self.patient = Patient.objects.create(
            first_name="Ext",
            last_name="UiPatient",
            date_of_birth=date(1992, 2, 2),
            phone="+48111222334",
            email="ext.ui@example.com",
        )
        self.entry = QueueEntry.objects.create(
            daily_queue=self.queue,
            patient=self.patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=1,
            appointment_time=timezone.now() - timedelta(hours=2),
            created_by_user=self.reception,
        )
        session = PatientFormSession.create_session(
            self.entry,
            created_by_user_id=self.reception.id,
            minutes=120,
        )
        PatientIntakeForm.objects.create(
            queue_entry=self.entry,
            session=session,
            form_status=IntakeStatus.SUBMITTED,
            submitted_at=timezone.now(),
            signature_sha256="b" * 64,
        )

    def test_hub_forbidden_for_doctor(self) -> None:
        self.client.force_login(self.doctor)
        r = self.client.get(reverse("admin_external_upload_hub"))
        self.assertEqual(r.status_code, 403)

    def test_hub_ok_for_reception(self) -> None:
        self.client.force_login(self.reception)
        r = self.client.get(reverse("admin_external_upload_hub"))
        self.assertEqual(r.status_code, 200)

    def test_hub_ok_for_admin(self) -> None:
        self.client.force_login(self.admin)
        r = self.client.get(reverse("admin_external_upload_hub"))
        self.assertEqual(r.status_code, 200)

    def test_hub_queryset_includes_submitted_intake_entry(self) -> None:
        request = self.factory.get("/admin/external-upload/")
        request.user = self.admin
        qs = ext_hub_views._external_upload_hub_queryset(request, form_status="all")
        self.assertIn(self.entry.id, set(qs.values_list("id", flat=True)))

    def test_hub_pick_redirects(self) -> None:
        self.client.force_login(self.reception)
        r = self.client.get(
            reverse("admin_external_upload_hub"),
            {"queue_entry": str(self.entry.id)},
        )
        self.assertEqual(r.status_code, 302)
        self.assertIn(str(self.entry.id), r["Location"])

    def test_entry_ok_for_reception(self) -> None:
        self.client.force_login(self.reception)
        r = self.client.get(
            reverse(
                "admin_external_upload_entry",
                kwargs={"queue_entry_id": self.entry.id},
            )
        )
        self.assertEqual(r.status_code, 200)

    def test_entry_404_when_queue_entry_out_of_scope(self) -> None:
        other_clinic = ClinicSite.objects.create(code="EUX", name="Other Clinic")
        room2 = ConsultingRoom.objects.create(
            clinic_site=other_clinic, code="X1", name="X1"
        )
        dq2 = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=other_clinic,
            consulting_room=room2,
            status=QueueStatus.OPEN,
            created_by_user=self.admin,
            assigned_doctor=self.doctor,
        )
        entry2 = QueueEntry.objects.create(
            daily_queue=dq2,
            patient=self.patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=1,
            appointment_time=timezone.now() - timedelta(hours=1),
            created_by_user=self.admin,
        )
        s2 = PatientFormSession.create_session(
            entry2,
            created_by_user_id=self.admin.id,
            minutes=120,
        )
        PatientIntakeForm.objects.create(
            queue_entry=entry2,
            session=s2,
            form_status=IntakeStatus.SUBMITTED,
            submitted_at=timezone.now(),
            signature_sha256="c" * 64,
        )
        self.client.force_login(self.reception)
        r = self.client.get(
            reverse(
                "admin_external_upload_entry",
                kwargs={"queue_entry_id": entry2.id},
            )
        )
        self.assertEqual(r.status_code, 404)
