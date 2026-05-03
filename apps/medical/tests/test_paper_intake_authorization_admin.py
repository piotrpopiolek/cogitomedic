"""Coverage for ``PaperIntakeAuthorizationAdmin`` (readonly + revoke admin action)."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.core.api_utils import assign_group_to_test_user
from apps.medical.admin import PaperIntakeAuthorizationAdmin
from apps.medical.models import MedicalDocStatus, PaperIntakeAuthorization
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

_REASON = "Paper intake authorization reason long enough for validation in tests."


def _request_with_messages(user: StaffUser):
    rf = RequestFactory()
    request = rf.post("/admin/")
    request.user = user
    middleware = SessionMiddleware(lambda r: None)
    middleware.process_request(request)
    request.session.save()
    request._messages = FallbackStorage(request)  # type: ignore[attr-defined]
    return request


class PaperIntakeAuthorizationAdminTests(TestCase):
    def setUp(self) -> None:
        self.site = AdminSite()
        self.model_admin = PaperIntakeAuthorizationAdmin(
            PaperIntakeAuthorization, self.site
        )
        self.admin = StaffUser.objects.create_user(
            username="pia-admin",
            email="pia.admin@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.admin, "Admin")
        self.doctor = StaffUser.objects.create_user(
            username="pia-doc",
            email="pia.doc@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.doctor, "Doctor")
        self.rec = StaffUser.objects.create_user(
            username="pia-rec",
            email="pia.rec@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.rec, "Reception")
        clinic = ClinicSite.objects.create(code="PIA", name="Paper Intake Admin Clinic")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="R1", name="R1")
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            created_by_user=self.rec,
            assigned_doctor=self.doctor,
        )
        patient = Patient.objects.create(
            first_name="A",
            last_name="AdminPatient",
            date_of_birth=date(1990, 1, 1),
            phone="+48111222333",
            email="pia.patient@example.com",
        )
        self.entry = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=1,
            appointment_time=timezone.now() - timedelta(hours=4),
            created_by_user=self.rec,
        )
        self.auth = PaperIntakeAuthorization.objects.create(
            queue_entry=self.entry,
            authorized_at=timezone.now(),
            authorized_by=self.admin,
            reason=_REASON,
        )

    def test_list_display_helpers(self) -> None:
        long_reason = "x" * 120
        self.auth.reason = long_reason
        self.auth.save(update_fields=["reason"])
        qs = self.model_admin.get_queryset(_request_with_messages(self.admin))
        obj = qs.get(pk=self.auth.pk)
        self.assertIn("AdminPatient", self.model_admin._patient_repr(obj))
        self.assertTrue(self.model_admin._short_reason(obj).endswith("…"))
        self.assertFalse(self.model_admin._has_document(obj))

    def test_has_document_true_when_medical_document_exists(self) -> None:
        from apps.medical.models import MedicalDocument, MedicalDocumentSourceType

        MedicalDocument.objects.create(
            queue_entry=self.entry,
            intake_form=None,
            source_type=MedicalDocumentSourceType.PAPER_INTAKE,
            status=MedicalDocStatus.DRAFT,
            current_version_no=0,
            created_by_user=self.doctor,
        )
        qs = self.model_admin.get_queryset(_request_with_messages(self.admin))
        obj = qs.get(pk=self.auth.pk)
        self.assertTrue(self.model_admin._has_document(obj))

    def test_permissions_disabled(self) -> None:
        req = _request_with_messages(self.admin)
        self.assertFalse(self.model_admin.has_add_permission(req))
        self.assertFalse(self.model_admin.has_change_permission(req))
        self.assertFalse(self.model_admin.has_delete_permission(req))

    def test_revoke_action_permission_denied_for_doctor(self) -> None:
        request = _request_with_messages(self.doctor)
        self.model_admin.admin_revoke_paper_intake_authorization(
            request, PaperIntakeAuthorization.objects.filter(pk=self.auth.pk)
        )
        msgs = [m.message for m in request._messages]  # type: ignore[attr-defined]
        self.assertTrue(msgs)
        self.assertTrue(
            PaperIntakeAuthorization.objects.filter(pk=self.auth.pk).exists()
        )

    def test_authorization_str_contains_queue_entry_id(self) -> None:
        self.assertIn(str(self.entry.id), str(self.auth))

    def test_revoke_action_success_for_admin(self) -> None:
        request = _request_with_messages(self.admin)
        self.model_admin.admin_revoke_paper_intake_authorization(
            request, PaperIntakeAuthorization.objects.filter(pk=self.auth.pk)
        )
        self.assertFalse(
            PaperIntakeAuthorization.objects.filter(pk=self.auth.pk).exists()
        )

    @patch("apps.medical.admin.revoke_paper_intake_authorization")
    def test_revoke_action_counts_domain_errors(self, mock_revoke: MagicMock) -> None:
        from apps.core.exceptions import DomainError

        def _raise(*_a, **_kw):
            raise DomainError("revoke failed", api_message_key="other.domain.error")

        mock_revoke.side_effect = _raise
        request = _request_with_messages(self.admin)
        # Second authorization on another queue entry (separate daily queue avoids any
        # position/constraint overlap with setUp data in large test runs).
        clinic2 = ClinicSite.objects.create(
            code="PIB", name="Paper Intake Admin Clinic B"
        )
        room2 = ConsultingRoom.objects.create(clinic_site=clinic2, code="R2", name="R2")
        queue2 = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic2,
            consulting_room=room2,
            status=QueueStatus.OPEN,
            created_by_user=self.rec,
            assigned_doctor=self.doctor,
        )
        patient2 = Patient.objects.create(
            first_name="B",
            last_name="Second",
            date_of_birth=date(1991, 2, 2),
            phone="+48222333444",
            email="second@example.com",
        )
        entry2 = QueueEntry.objects.create(
            daily_queue=queue2,
            patient=patient2,
            entry_status=QueueEntryStatus.WAITING,
            position_no=1,
            appointment_time=timezone.now() - timedelta(hours=4),
            created_by_user=self.rec,
        )
        auth2 = PaperIntakeAuthorization.objects.create(
            queue_entry=entry2,
            authorized_at=timezone.now(),
            authorized_by=self.admin,
            reason=_REASON + " c",
        )
        self.model_admin.admin_revoke_paper_intake_authorization(
            request,
            PaperIntakeAuthorization.objects.filter(pk__in=[self.auth.pk, auth2.pk]),
        )
        self.assertEqual(mock_revoke.call_count, 2)
