from __future__ import annotations

import json
from datetime import date
from unittest.mock import patch

from django.contrib import messages
from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.admin_list_page_size import CogitomedicaModelAdmin
from apps.core.api_utils import assign_group_to_test_user
from apps.core.exceptions import DomainError
from apps.operations.models import AuditEvent
from apps.reception.admin import QueueEntryAdmin
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


def _request_with_messages(user: StaffUser, *, path: str = "/admin/reception/queueentry/"):
    request = RequestFactory().post(path)
    request.user = user
    SessionMiddleware(lambda r: None).process_request(request)
    request.session.save()
    request._messages = FallbackStorage(request)
    return request


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

    def _model_admin(self) -> QueueEntryAdmin:
        return QueueEntryAdmin(QueueEntry, AdminSite())

    def _admin_save(
        self,
        *,
        obj: QueueEntry,
        user: StaffUser,
        changed_data: list[str],
        cleaned_data: dict,
        change: bool = True,
    ) -> None:
        request = _request_with_messages(user)
        form = type(
            "BoundQueueEntryForm",
            (),
            {"changed_data": changed_data, "cleaned_data": cleaned_data},
        )()
        self._model_admin().save_model(request, obj, form, change)

    def _extra_entry(self, *, position_no: int, suffix: str) -> QueueEntry:
        patient = Patient.objects.create(
            first_name="Bulk",
            last_name=suffix,
            date_of_birth=date(1982, 2, 2),
            phone=f"+48500111{position_no:03d}",
            email=f"bulk.{suffix.lower()}@example.com",
        )
        return QueueEntry.objects.create(
            daily_queue=self.queue,
            patient=patient,
            position_no=position_no,
            entry_status=QueueEntryStatus.WAITING,
            created_by_user=self.reception,
        )

    def _ausfall_audit_count(self) -> int:
        return AuditEvent.objects.filter(
            event_type="QUEUE_ENTRY_AUSFALLHONORAR_CHANGED"
        ).count()

    def test_admin_notes_save_does_not_clear_concurrent_flag(self) -> None:
        """Stale unchecked checkbox is not intent; concurrent mark must survive."""
        update_queue_entry(
            self.entry.id,
            ausfallhonorar=True,
            actor_user_id=self.manager.id,
        )
        obj = QueueEntry.objects.get(pk=self.entry.id)
        obj.ausfallhonorar = False
        obj.notes = "only notes"
        self._admin_save(
            obj=obj,
            user=self.reception,
            changed_data=["notes"],
            cleaned_data={"notes": "only notes", "ausfallhonorar": False},
        )
        self.entry.refresh_from_db()
        self.assertTrue(self.entry.ausfallhonorar)
        self.assertEqual(self.entry.ausfallhonorar_set_by_id, self.manager.id)
        self.assertEqual(
            AuditEvent.objects.filter(
                event_type="QUEUE_ENTRY_AUSFALLHONORAR_CHANGED"
            ).count(),
            1,
        )

    def test_admin_changed_checkbox_sets_flag_through_service(self) -> None:
        obj = QueueEntry.objects.get(pk=self.entry.id)
        obj.ausfallhonorar = True
        self._admin_save(
            obj=obj,
            user=self.reception,
            changed_data=["ausfallhonorar"],
            cleaned_data={"ausfallhonorar": True},
        )
        self.entry.refresh_from_db()
        self.assertTrue(self.entry.ausfallhonorar)
        self.assertEqual(self.entry.ausfallhonorar_set_by_id, self.reception.id)
        self.assertEqual(self._ausfall_audit_count(), 1)

    def test_admin_changed_checkbox_clears_flag_through_service(self) -> None:
        update_queue_entry(
            self.entry.id,
            ausfallhonorar=True,
            actor_user_id=self.manager.id,
        )
        obj = QueueEntry.objects.get(pk=self.entry.id)
        obj.ausfallhonorar = False
        self._admin_save(
            obj=obj,
            user=self.reception,
            changed_data=["ausfallhonorar"],
            cleaned_data={"ausfallhonorar": False},
        )
        self.entry.refresh_from_db()
        self.assertFalse(self.entry.ausfallhonorar)
        self.assertEqual(self.entry.ausfallhonorar_set_by_id, self.reception.id)
        self.assertEqual(self._ausfall_audit_count(), 2)

    def test_admin_create_with_checkbox_sets_flag_through_service(self) -> None:
        patient = Patient.objects.create(
            first_name="New",
            last_name="Flagged",
            date_of_birth=date(1982, 2, 2),
            phone="+48500111222",
            email="new.flagged@example.com",
        )
        obj = QueueEntry(
            daily_queue=self.queue,
            patient=patient,
            position_no=2,
            entry_status=QueueEntryStatus.WAITING,
            created_by_user=self.reception,
            ausfallhonorar=True,
        )
        self._admin_save(
            obj=obj,
            user=self.reception,
            changed_data=["ausfallhonorar"],
            cleaned_data={"ausfallhonorar": True},
            change=False,
        )
        obj.refresh_from_db()
        self.assertTrue(obj.ausfallhonorar)
        self.assertEqual(obj.ausfallhonorar_set_by_id, self.reception.id)
        self.assertEqual(self._ausfall_audit_count(), 1)

    def test_admin_create_without_checkbox_stays_unflagged(self) -> None:
        patient = Patient.objects.create(
            first_name="New",
            last_name="Plain",
            date_of_birth=date(1983, 3, 3),
            phone="+48500111333",
            email="new.plain@example.com",
        )
        obj = QueueEntry(
            daily_queue=self.queue,
            patient=patient,
            position_no=2,
            entry_status=QueueEntryStatus.WAITING,
            created_by_user=self.reception,
            ausfallhonorar=True,
        )
        self._admin_save(
            obj=obj,
            user=self.reception,
            changed_data=["notes"],
            cleaned_data={"notes": "new", "ausfallhonorar": True},
            change=False,
        )
        obj.refresh_from_db()
        self.assertFalse(obj.ausfallhonorar)
        self.assertIsNone(obj.ausfallhonorar_set_by_id)
        self.assertEqual(self._ausfall_audit_count(), 0)

    def test_admin_bound_form_notes_only_does_not_treat_checkbox_as_changed(
        self,
    ) -> None:
        """Real ModelForm: GET snapshot False + omitted checkbox → not in changed_data."""
        update_queue_entry(
            self.entry.id,
            ausfallhonorar=True,
            actor_user_id=self.manager.id,
        )
        request = _request_with_messages(self.reception)
        admin_inst = self._model_admin()
        Form = admin_inst.get_form(request, obj=self.entry)
        stale = QueueEntry.objects.get(pk=self.entry.id)
        stale.ausfallhonorar = False
        stale.notes = "only notes"
        form = Form(
            data={
                "daily_queue": str(self.queue.id),
                "patient": str(self.patient.id),
                "entry_status": QueueEntryStatus.WAITING,
                "position_no": 1,
                "created_by_user": str(self.reception.id),
                "notes": "only notes",
            },
            instance=stale,
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertNotIn("ausfallhonorar", form.changed_data)
        obj = form.save(commit=False)
        admin_inst.save_model(request, obj, form, True)
        self.entry.refresh_from_db()
        self.assertTrue(self.entry.ausfallhonorar)
        self.assertEqual(self.entry.ausfallhonorar_set_by_id, self.manager.id)
        self.assertEqual(self._ausfall_audit_count(), 1)

    def test_admin_reception_sees_bulk_actions_doctor_and_accounting_do_not(
        self,
    ) -> None:
        admin_inst = self._model_admin()
        reception_actions = admin_inst.get_actions(
            _request_with_messages(self.reception)
        )
        self.assertIn("mark_ausfallhonorar", reception_actions)
        self.assertIn("clear_ausfallhonorar", reception_actions)
        for user in (self.doctor, self.accounting):
            actions = admin_inst.get_actions(_request_with_messages(user))
            self.assertNotIn("mark_ausfallhonorar", actions)
            self.assertNotIn("clear_ausfallhonorar", actions)

    def test_admin_ausfallhonorar_readonly_for_accounting_not_reception(self) -> None:
        admin_inst = self._model_admin()
        accounting_ro = admin_inst.get_readonly_fields(
            _request_with_messages(self.accounting), obj=self.entry
        )
        reception_ro = admin_inst.get_readonly_fields(
            _request_with_messages(self.reception), obj=self.entry
        )
        self.assertIn("ausfallhonorar", accounting_ro)
        self.assertNotIn("ausfallhonorar", reception_ro)

    def test_admin_bulk_mark_and_clear_via_changelist(self) -> None:
        other = self._extra_entry(position_no=2, suffix="Other")
        self.client.login(username="af-reception", password="safe-password")
        url = reverse("admin:reception_queueentry_changelist")
        mark = self.client.post(
            url,
            {
                "action": "mark_ausfallhonorar",
                "_selected_action": [str(self.entry.pk), str(other.pk)],
                "index": "0",
            },
        )
        self.assertEqual(mark.status_code, 302)
        self.entry.refresh_from_db()
        other.refresh_from_db()
        self.assertTrue(self.entry.ausfallhonorar)
        self.assertTrue(other.ausfallhonorar)
        self.assertEqual(self.entry.ausfallhonorar_set_by_id, self.reception.id)
        self.assertEqual(other.ausfallhonorar_set_by_id, self.reception.id)
        self.assertEqual(self._ausfall_audit_count(), 2)

        clear = self.client.post(
            url,
            {
                "action": "clear_ausfallhonorar",
                "_selected_action": [str(self.entry.pk), str(other.pk)],
                "index": "0",
            },
        )
        self.assertEqual(clear.status_code, 302)
        self.entry.refresh_from_db()
        other.refresh_from_db()
        self.assertFalse(self.entry.ausfallhonorar)
        self.assertFalse(other.ausfallhonorar)
        self.assertEqual(self.entry.ausfallhonorar_set_by_id, self.reception.id)
        self.assertEqual(self._ausfall_audit_count(), 4)

    def test_admin_bulk_mark_denied_for_doctor(self) -> None:
        request = _request_with_messages(self.doctor)
        self._model_admin().mark_ausfallhonorar(
            request, QueueEntry.objects.filter(pk=self.entry.pk)
        )
        stored = list(request._messages)
        self.assertTrue(stored)
        self.assertEqual(stored[0].level, messages.ERROR)
        self.entry.refresh_from_db()
        self.assertFalse(self.entry.ausfallhonorar)
        self.assertEqual(self._ausfall_audit_count(), 0)

    def test_admin_flag_denied_rolls_back_notes_and_skips_success(self) -> None:
        obj = QueueEntry.objects.get(pk=self.entry.id)
        obj.notes = "should not persist"
        obj.ausfallhonorar = True
        request = _request_with_messages(self.doctor)
        form = type(
            "BoundQueueEntryForm",
            (),
            {
                "changed_data": ["ausfallhonorar", "notes"],
                "cleaned_data": {
                    "ausfallhonorar": True,
                    "notes": "should not persist",
                },
            },
        )()
        with self.assertRaises(DomainError) as ctx:
            self._model_admin().save_model(request, obj, form, True)
        self.assertEqual(
            ctx.exception.api_message_key,
            "other.domain.ausfallhonorar_role_required",
        )
        stored = list(request._messages)
        self.assertTrue(stored)
        self.assertEqual(stored[0].level, messages.ERROR)
        self.assertFalse(any(m.level == messages.SUCCESS for m in stored))
        self.entry.refresh_from_db()
        self.assertFalse(self.entry.ausfallhonorar)
        self.assertNotEqual(self.entry.notes, "should not persist")
        self.assertEqual(self._ausfall_audit_count(), 0)

    def test_admin_create_flag_denied_does_not_insert(self) -> None:
        patient = Patient.objects.create(
            first_name="New",
            last_name="Denied",
            date_of_birth=date(1984, 4, 4),
            phone="+48500111444",
            email="new.denied@example.com",
        )
        obj = QueueEntry(
            daily_queue=self.queue,
            patient=patient,
            position_no=2,
            entry_status=QueueEntryStatus.WAITING,
            created_by_user=self.reception,
            ausfallhonorar=True,
        )
        with self.assertRaises(DomainError):
            self._admin_save(
                obj=obj,
                user=self.doctor,
                changed_data=["ausfallhonorar"],
                cleaned_data={"ausfallhonorar": True},
                change=False,
            )
        self.assertFalse(QueueEntry.objects.filter(patient=patient).exists())
        self.assertEqual(self._ausfall_audit_count(), 0)

    def test_admin_changeform_view_redirects_on_domain_error(self) -> None:
        request = _request_with_messages(self.reception)
        with patch.object(
            CogitomedicaModelAdmin,
            "changeform_view",
            side_effect=DomainError(
                "denied",
                api_message_key="other.domain.ausfallhonorar_role_required",
            ),
        ):
            response = self._model_admin().changeform_view(request)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            any(m.level == messages.SUCCESS for m in request._messages)
        )
