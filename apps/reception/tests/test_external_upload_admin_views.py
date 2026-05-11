from __future__ import annotations

import re
import uuid
from datetime import date, timedelta
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models import Q
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfWriter

from apps.core.api_utils import assign_group_to_test_user
from apps.intake.models import IntakeStatus, PatientIntakeForm
from apps.reception import external_upload_admin_views as ext_hub_views
from apps.medical.models import MedicalDocument, MedicalDocumentVersion
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


def _minimal_pdf_bytes() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


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

    def test_hub_legacy_queue_entry_id_redirects(self) -> None:
        self.client.force_login(self.reception)
        r = self.client.get(
            reverse("admin_external_upload_hub"),
            {"queue_entry_id": str(self.entry.id)},
        )
        self.assertEqual(r.status_code, 302)
        self.assertIn(str(self.entry.id), r["Location"])

    def test_hub_legacy_unknown_queue_entry_returns_404(self) -> None:
        self.client.force_login(self.reception)
        r = self.client.get(
            reverse("admin_external_upload_hub"),
            {"queue_entry_id": str(uuid.uuid4())},
        )
        self.assertEqual(r.status_code, 404)

    def test_hub_legacy_out_of_scope_returns_403(self) -> None:
        other_clinic = ClinicSite.objects.create(code="EUX2", name="Other Clinic 2")
        room2 = ConsultingRoom.objects.create(
            clinic_site=other_clinic, code="X2", name="X2"
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
            reverse("admin_external_upload_hub"),
            {"queue_entry_id": str(entry2.id)},
        )
        self.assertEqual(r.status_code, 403)

    def test_preview_pdf_url_uses_setting_when_set(self) -> None:
        req = self.factory.get("/admin/external-upload/")
        mid = uuid.uuid4()
        with override_settings(
            EXTERNAL_UPLOAD_PREVIEW_API_BASE_URL="https://api.example.test"
        ):
            url = ext_hub_views._external_upload_preview_pdf_url(
                req, medical_document_id=mid
            )
        self.assertTrue(
            url.startswith("https://api.example.test/api/v1/medical-documents/")
        )
        self.assertIn(str(mid), url)
        self.assertIn("external-upload/preview-pdf", url)

    def test_entry_ok_for_reception(self) -> None:
        self.client.force_login(self.reception)
        r = self.client.get(
            reverse(
                "admin_external_upload_entry",
                kwargs={"queue_entry_id": self.entry.id},
            )
        )
        self.assertEqual(r.status_code, 200)

    @patch("apps.medical.services.get_hidrive_adapter")
    def test_entry_get_contains_publish_locale_after_upload(
        self, adapter_factory
    ) -> None:
        adapter_factory.return_value.upload.return_value = None
        self.client.force_login(self.reception)
        self.client.post(
            reverse(
                "admin_external_upload_entry",
                kwargs={"queue_entry_id": self.entry.id},
            ),
            {
                "action": "upload",
                "file": SimpleUploadedFile(
                    "lab.pdf",
                    _minimal_pdf_bytes(),
                    content_type="application/pdf",
                ),
            },
            follow=True,
        )
        r = self.client.get(
            reverse(
                "admin_external_upload_entry",
                kwargs={"queue_entry_id": self.entry.id},
            )
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn('id="id_publish_locale"', r.content.decode())

    def test_queue_entry_external_upload_url_none_for_doctor(self) -> None:
        request = self.factory.get("/")
        request.user = self.doctor
        self.assertIsNone(
            ext_hub_views.queue_entry_external_upload_entry_url(request, self.entry)
        )

    def test_queue_entry_external_upload_url_for_reception_when_eligible(
        self,
    ) -> None:
        request = self.factory.get("/")
        request.user = self.reception
        url = ext_hub_views.queue_entry_external_upload_entry_url(request, self.entry)
        self.assertIsNotNone(url)
        assert url is not None
        self.assertIn(str(self.entry.id), url)

    def test_queue_entry_change_includes_external_upload_link(self) -> None:
        # Use Admin: full modeladmin stack (raw_id / related) may require extra perms
        # beyond Reception's role group; Admin matches real "can open change form" for CI.
        self.client.force_login(self.admin)
        r = self.client.get(
            reverse("admin:reception_queueentry_change", args=[self.entry.pk])
        )
        self.assertEqual(r.status_code, 200)
        expected = reverse(
            "admin_external_upload_entry",
            kwargs={"queue_entry_id": self.entry.id},
        )
        self.assertIn(expected, r.content.decode())

    def test_queue_entry_change_hides_external_upload_link_for_doctor(self) -> None:
        """Doctor must not see external-upload shortcut even if they can open this change form.

        The Doctor role group does not include ``change_queueentry`` or raw-id targets; grant
        only those extras here so we always assert on HTML (no skip).
        """
        ct_qe = ContentType.objects.get_for_model(QueueEntry)
        ct_staff = ContentType.objects.get_for_model(StaffUser)
        ct_pfs = ContentType.objects.get_for_model(PatientFormSession)
        extra = Permission.objects.filter(
            Q(content_type=ct_qe, codename="change_queueentry")
            | Q(content_type=ct_staff, codename="view_staffuser")
            | Q(content_type=ct_pfs, codename="view_patientformsession")
        )
        self.doctor.user_permissions.add(*list(extra))
        self.client.force_login(self.doctor)
        r = self.client.get(
            reverse("admin:reception_queueentry_change", args=[self.entry.pk])
        )
        self.assertEqual(
            r.status_code,
            200,
            msg=(
                "Doctor should reach QueueEntry change with extra perms; "
                f"got {r.status_code}. Extend this test's permission list if admin requires more."
            ),
        )
        expected = reverse(
            "admin_external_upload_entry",
            kwargs={"queue_entry_id": self.entry.id},
        )
        self.assertNotIn(expected, r.content.decode())

    def test_entry_403_when_queue_entry_out_of_scope(self) -> None:
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
        self.assertEqual(r.status_code, 403)

    @patch("apps.medical.services.get_hidrive_adapter")
    def test_entry_publish_form_includes_publish_request_id(
        self, adapter_factory
    ) -> None:
        adapter_factory.return_value.upload.return_value = None
        self.client.force_login(self.reception)
        pdf = SimpleUploadedFile(
            "lab.pdf",
            _minimal_pdf_bytes(),
            content_type="application/pdf",
        )
        r = self.client.post(
            reverse(
                "admin_external_upload_entry",
                kwargs={"queue_entry_id": self.entry.id},
            ),
            {"action": "upload", "file": pdf},
            follow=True,
        )
        self.assertEqual(r.status_code, 200)
        self.assertRegex(
            r.content.decode(),
            r'name="publish_request_id"\s+value="[0-9a-f-]{36}"',
        )

    @patch("apps.medical.services.get_hidrive_adapter")
    def test_entry_double_publish_same_request_id_is_idempotent(
        self, adapter_factory
    ) -> None:
        adapter_factory.return_value.upload.return_value = None
        self.client.force_login(self.reception)
        self.client.post(
            reverse(
                "admin_external_upload_entry",
                kwargs={"queue_entry_id": self.entry.id},
            ),
            {
                "action": "upload",
                "file": SimpleUploadedFile(
                    "lab.pdf",
                    _minimal_pdf_bytes(),
                    content_type="application/pdf",
                ),
            },
            follow=True,
        )
        doc = MedicalDocument.objects.get(queue_entry_id=self.entry.id)
        g = self.client.get(
            reverse(
                "admin_external_upload_entry",
                kwargs={"queue_entry_id": self.entry.id},
            )
        )
        self.assertEqual(g.status_code, 200)
        html = g.content.decode()
        m = re.search(
            r'name="publish_request_id"\s+value="([0-9a-f-]{36})"',
            html,
        )
        self.assertIsNotNone(m)
        assert m is not None  # narrow for mypy (assertIsNotNone does not)
        publish_request_id = m.group(1)
        rid = uuid.UUID(publish_request_id)
        pub = {
            "action": "publish",
            "publish_request_id": publish_request_id,
            "publish_locale": "de-DE",
            "verification_ack": "1",
        }
        r1 = self.client.post(
            reverse(
                "admin_external_upload_entry",
                kwargs={"queue_entry_id": self.entry.id},
            ),
            pub,
            follow=True,
        )
        self.assertEqual(r1.status_code, 200)
        r2 = self.client.post(
            reverse(
                "admin_external_upload_entry",
                kwargs={"queue_entry_id": self.entry.id},
            ),
            pub,
            follow=True,
        )
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(
            MedicalDocumentVersion.objects.filter(
                medical_document_id=doc.id,
                publish_request_id=rid,
            ).count(),
            1,
        )
