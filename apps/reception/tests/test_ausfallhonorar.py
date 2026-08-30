from __future__ import annotations

import json
from datetime import date

from django.test import Client, TestCase
from django.utils import timezone

from apps.core.api_utils import assign_group_to_test_user
from apps.core.exceptions import DomainError
from apps.operations.models import AuditEvent
from apps.reception.models import (
    ClinicSite,
    ConsultingRoom,
    DailyQueue,
    Patient,
    QueueEntry,
    QueueEntryStatus,
    QueueStatus,
)
from apps.reception.services import update_queue_entry
from apps.users.models import StaffUser


class AusfallhonorarFlagTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.clinic = ClinicSite.objects.create(code="AF1", name="Ausfall Clinic")
        self.room = ConsultingRoom.objects.create(
            clinic_site=self.clinic,
            code="AFR1",
            name="Ausfall Room",
        )
        self.reception = self._user("af-reception", "Reception")
        self.manager = self._user("af-manager", "Manager")
        self.admin = self._user("af-admin", "Admin")
        self.doctor = self._user("af-doctor", "Doctor")
        self.accounting = self._user("af-accounting", "Accounting")
        self.tablet = self._user("af-tablet", "Tablet")
        for user in (
            self.reception,
            self.manager,
            self.admin,
            self.doctor,
            self.accounting,
            self.tablet,
        ):
            user.clinic_sites.add(self.clinic)
        self.queue = DailyQueue.objects.create(
            queue_date=date(2026, 3, 10),
            clinic_site=self.clinic,
            consulting_room=self.room,
            status=QueueStatus.OPEN,
            assigned_doctor=self.doctor,
            created_by_user=self.reception,
        )
        self.patient = Patient.objects.create(
            first_name="Ada",
            last_name="NoShow",
            date_of_birth=date(1980, 1, 1),
            phone="+48500111000",
            email="ada.noshow@example.com",
        )
        self.entry = QueueEntry.objects.create(
            daily_queue=self.queue,
            patient=self.patient,
            position_no=1,
            entry_status=QueueEntryStatus.WAITING,
            created_by_user=self.reception,
        )

    def _user(self, username: str, group: str) -> StaffUser:
        user = StaffUser.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(user, group)
        return user

    def test_reception_sets_flag_with_audit_and_actor(self) -> None:
        before = timezone.now()
        updated = update_queue_entry(
            self.entry.id,
            ausfallhonorar=True,
            actor_user_id=self.reception.id,
        )
        self.assertTrue(updated.ausfallhonorar)
        self.assertEqual(updated.ausfallhonorar_set_by_id, self.reception.id)
        self.assertIsNotNone(updated.ausfallhonorar_set_at)
        assert updated.ausfallhonorar_set_at is not None
        self.assertGreaterEqual(updated.ausfallhonorar_set_at, before)
        ev = AuditEvent.objects.get(event_type="QUEUE_ENTRY_AUSFALLHONORAR_CHANGED")
        self.assertEqual(ev.actor_user_id, self.reception.id)
        self.assertEqual(ev.patient_id, self.patient.id)
        self.assertEqual(ev.context_clinic_site_id, self.clinic.id)
        self.assertEqual(ev.metadata.get("queue_entry_id"), str(self.entry.id))
        self.assertTrue(ev.metadata.get("ausfallhonorar"))

    def test_unsetting_updates_actor_and_audits(self) -> None:
        update_queue_entry(
            self.entry.id,
            ausfallhonorar=True,
            actor_user_id=self.reception.id,
        )
        updated = update_queue_entry(
            self.entry.id,
            ausfallhonorar=False,
            actor_user_id=self.manager.id,
        )
        self.assertFalse(updated.ausfallhonorar)
        self.assertEqual(updated.ausfallhonorar_set_by_id, self.manager.id)
        self.assertEqual(
            AuditEvent.objects.filter(
                event_type="QUEUE_ENTRY_AUSFALLHONORAR_CHANGED"
            ).count(),
            2,
        )
        last = (
            AuditEvent.objects.filter(event_type="QUEUE_ENTRY_AUSFALLHONORAR_CHANGED")
            .order_by("-event_time")
            .first()
        )
        assert last is not None
        self.assertFalse(last.metadata.get("ausfallhonorar"))
        self.assertEqual(last.actor_user_id, self.manager.id)

    def test_same_value_does_not_emit_audit(self) -> None:
        update_queue_entry(
            self.entry.id,
            ausfallhonorar=True,
            actor_user_id=self.admin.id,
        )
        update_queue_entry(
            self.entry.id,
            ausfallhonorar=True,
            actor_user_id=self.admin.id,
        )
        self.assertEqual(
            AuditEvent.objects.filter(
                event_type="QUEUE_ENTRY_AUSFALLHONORAR_CHANGED"
            ).count(),
            1,
        )

    def test_manager_and_admin_may_set_flag(self) -> None:
        for actor in (self.manager, self.admin):
            update_queue_entry(
                self.entry.id,
                ausfallhonorar=False,
                actor_user_id=self.reception.id,
            )
            updated = update_queue_entry(
                self.entry.id,
                ausfallhonorar=True,
                actor_user_id=actor.id,
            )
            self.assertTrue(updated.ausfallhonorar)
            self.assertEqual(updated.ausfallhonorar_set_by_id, actor.id)
            update_queue_entry(
                self.entry.id,
                ausfallhonorar=False,
                actor_user_id=actor.id,
            )

    def test_doctor_accounting_tablet_cannot_set_flag(self) -> None:
        for actor in (self.doctor, self.accounting, self.tablet):
            with self.assertRaises(DomainError) as ctx:
                update_queue_entry(
                    self.entry.id,
                    ausfallhonorar=True,
                    actor_user_id=actor.id,
                )
            self.assertEqual(
                ctx.exception.api_message_key,
                "other.domain.ausfallhonorar_role_required",
            )
        self.entry.refresh_from_db()
        self.assertFalse(self.entry.ausfallhonorar)

    def test_patch_reception_sets_ausfallhonorar(self) -> None:
        self.client.login(username="af-reception", password="safe-password")
        response = self.client.patch(
            f"/api/v1/queue-entries/{self.entry.id}",
            data=json.dumps({"ausfallhonorar": True}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ausfallhonorar"])
        self.entry.refresh_from_db()
        self.assertTrue(self.entry.ausfallhonorar)
        self.assertEqual(self.entry.ausfallhonorar_set_by_id, self.reception.id)

    def test_patch_manager_sets_ausfallhonorar(self) -> None:
        self.client.login(username="af-manager", password="safe-password")
        response = self.client.patch(
            f"/api/v1/queue-entries/{self.entry.id}",
            data=json.dumps({"ausfallhonorar": True}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ausfallhonorar"])

    def test_patch_doctor_forbidden(self) -> None:
        self.client.login(username="af-doctor", password="safe-password")
        response = self.client.patch(
            f"/api/v1/queue-entries/{self.entry.id}",
            data=json.dumps({"ausfallhonorar": True}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        self.entry.refresh_from_db()
        self.assertFalse(self.entry.ausfallhonorar)

    def test_patch_accounting_forbidden(self) -> None:
        self.client.login(username="af-accounting", password="safe-password")
        response = self.client.patch(
            f"/api/v1/queue-entries/{self.entry.id}",
            data=json.dumps({"ausfallhonorar": True}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        self.entry.refresh_from_db()
        self.assertFalse(self.entry.ausfallhonorar)
