from __future__ import annotations

import json
from datetime import date
from uuid import uuid4

from django.test import Client, TestCase
from django.utils import timezone

from apps.reception.models import (
    ClinicSite,
    ConsultingRoom,
    DailyQueue,
    Patient,
    QueueEntry,
    QueueEntryStatus,
    QueueShift,
    QueueSource,
    QueueStatus,
)
from apps.users.models import StaffRole, StaffUser


class DailyQueuesApiTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.reception_user = StaffUser.objects.create_user(
            username="reception-api",
            email="reception-api@example.com",
            password="safe-password",
            role=StaffRole.RECEPTION,
            is_staff=True,
        )
        self.clinic = ClinicSite.objects.create(code="C1", name="Clinic 1")
        self.room = ConsultingRoom.objects.create(
            clinic_site=self.clinic,
            code="R1",
            name="Room 1",
        )

    def test_get_daily_queues_empty(self) -> None:
        response = self.client.get("/api/v1/daily-queues")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("items", data)
        self.assertEqual(data["items"], [])

    def test_post_daily_queue_creates_and_returns_201(self) -> None:
        queue_date = timezone.now().date()
        payload = {
            "queue_date": queue_date.isoformat(),
            "clinic_site_id": str(self.clinic.id),
            "consulting_room_id": str(self.room.id),
            "shift_code": QueueShift.FULL_DAY,
            "source": QueueSource.MANUAL,
            "created_by_user_id": str(self.reception_user.id),
        }
        response = self.client.post(
            "/api/v1/daily-queues",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["queue_date"], queue_date.isoformat())
        self.assertEqual(data["clinic_site_id"], str(self.clinic.id))
        self.assertEqual(data["consulting_room_id"], str(self.room.id))
        self.assertEqual(data["shift_code"], QueueShift.FULL_DAY)
        self.assertEqual(data["status"], QueueStatus.OPEN)

    def test_post_daily_queue_duplicate_returns_409(self) -> None:
        queue_date = timezone.now().date()
        payload = {
            "queue_date": queue_date.isoformat(),
            "clinic_site_id": str(self.clinic.id),
            "consulting_room_id": str(self.room.id),
            "shift_code": QueueShift.FULL_DAY,
            "source": QueueSource.MANUAL,
            "created_by_user_id": str(self.reception_user.id),
        }
        self.client.post("/api/v1/daily-queues", data=json.dumps(payload), content_type="application/json")
        response = self.client.post(
            "/api/v1/daily-queues",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 409)

    def test_get_daily_queue_detail_returns_200(self) -> None:
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=self.clinic,
            consulting_room=self.room,
            status=QueueStatus.OPEN,
            created_by_user=self.reception_user,
        )
        response = self.client.get(f"/api/v1/daily-queues/{queue.id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], str(queue.id))
        self.assertEqual(data["status"], QueueStatus.OPEN)

    def test_patch_daily_queue_status_to_closed(self) -> None:
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=self.clinic,
            consulting_room=self.room,
            status=QueueStatus.OPEN,
            created_by_user=self.reception_user,
        )
        response = self.client.patch(
            f"/api/v1/daily-queues/{queue.id}",
            data=json.dumps({"status": "CLOSED"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], QueueStatus.CLOSED)
        queue.refresh_from_db()
        self.assertEqual(queue.status, QueueStatus.CLOSED)

    def test_get_daily_queue_entries_empty(self) -> None:
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=self.clinic,
            consulting_room=self.room,
            status=QueueStatus.OPEN,
            created_by_user=self.reception_user,
        )
        response = self.client.get(f"/api/v1/daily-queues/{queue.id}/entries")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["items"], [])

    def test_post_queue_entry_to_closed_queue_returns_409(self) -> None:
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=self.clinic,
            consulting_room=self.room,
            status=QueueStatus.CLOSED,
            created_by_user=self.reception_user,
        )
        patient = Patient.objects.create(
            first_name="Api",
            last_name="Patient",
            date_of_birth=date(1990, 1, 1),
            phone="+48123456789",
            email="api@example.com",
            doctolib_patient_id="DOC-1",
        )
        payload = {
            "patient_id": str(patient.id),
            "created_by_user_id": str(self.reception_user.id),
        }
        response = self.client.post(
            f"/api/v1/daily-queues/{queue.id}/entries",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 409)

    def test_post_queue_entry_creates_and_returns_201(self) -> None:
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=self.clinic,
            consulting_room=self.room,
            status=QueueStatus.OPEN,
            created_by_user=self.reception_user,
        )
        patient = Patient.objects.create(
            first_name="Api",
            last_name="Patient",
            date_of_birth=date(1990, 1, 1),
            phone="+48123456789",
            email="api@example.com",
            doctolib_patient_id="DOC-1",
        )
        payload = {
            "patient_id": str(patient.id),
            "created_by_user_id": str(self.reception_user.id),
            "notes": "First visit",
        }
        response = self.client.post(
            f"/api/v1/daily-queues/{queue.id}/entries",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["patient_id"], str(patient.id))
        self.assertEqual(data["position_no"], 1)
        self.assertEqual(data["entry_status"], QueueEntryStatus.WAITING)
        self.assertEqual(data["notes"], "First visit")

    def test_get_queue_entry_detail_returns_200(self) -> None:
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=self.clinic,
            consulting_room=self.room,
            status=QueueStatus.OPEN,
            created_by_user=self.reception_user,
        )
        patient = Patient.objects.create(
            first_name="P",
            last_name="T",
            date_of_birth=date(1985, 1, 1),
            phone="+48999999999",
            email="p@example.com",
            doctolib_patient_id="DOC-P",
        )
        entry = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            position_no=1,
            entry_status=QueueEntryStatus.WAITING,
            created_by_user=self.reception_user,
        )
        response = self.client.get(f"/api/v1/queue-entries/{entry.id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], str(entry.id))
        self.assertEqual(data["position_no"], 1)

    def test_patch_queue_entry_updates_status_and_notes(self) -> None:
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=self.clinic,
            consulting_room=self.room,
            status=QueueStatus.OPEN,
            created_by_user=self.reception_user,
        )
        patient = Patient.objects.create(
            first_name="P",
            last_name="T",
            date_of_birth=date(1985, 1, 1),
            phone="+48999999999",
            email="p@example.com",
            doctolib_patient_id="DOC-P",
        )
        entry = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            position_no=1,
            entry_status=QueueEntryStatus.WAITING,
            created_by_user=self.reception_user,
        )
        response = self.client.patch(
            f"/api/v1/queue-entries/{entry.id}",
            data=json.dumps({"entry_status": "IN_PROGRESS", "notes": "In room"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["entry_status"], QueueEntryStatus.IN_PROGRESS)
        self.assertEqual(data["notes"], "In room")

    def test_delete_queue_entry_sets_cancelled(self) -> None:
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=self.clinic,
            consulting_room=self.room,
            status=QueueStatus.OPEN,
            created_by_user=self.reception_user,
        )
        patient = Patient.objects.create(
            first_name="P",
            last_name="T",
            date_of_birth=date(1985, 1, 1),
            phone="+48999999999",
            email="p@example.com",
            doctolib_patient_id="DOC-P",
        )
        entry = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            position_no=1,
            entry_status=QueueEntryStatus.WAITING,
            created_by_user=self.reception_user,
        )
        response = self.client.delete(f"/api/v1/queue-entries/{entry.id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["entry_status"], QueueEntryStatus.CANCELLED)
        entry.refresh_from_db()
        self.assertEqual(entry.entry_status, QueueEntryStatus.CANCELLED)

    def test_daily_queue_not_found_returns_404(self) -> None:
        response = self.client.get(f"/api/v1/daily-queues/{uuid4()}")
        self.assertEqual(response.status_code, 404)

    def test_queue_entry_not_found_returns_404(self) -> None:
        response = self.client.get(f"/api/v1/queue-entries/{uuid4()}")
        self.assertEqual(response.status_code, 404)
