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
    TabletDevice,
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


class TabletDevicesApiTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()

    def test_get_tablet_devices_empty(self) -> None:
        response = self.client.get("/api/v1/tablet-devices")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"], [])

    def test_post_tablet_device_creates(self) -> None:
        response = self.client.post(
            "/api/v1/tablet-devices",
            data=json.dumps({"name": "Tablet 1", "device_code": "TAB-001", "is_active": True}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["name"], "Tablet 1")
        self.assertEqual(payload["device_code"], "TAB-001")
        self.assertTrue(payload["is_active"])

    def test_post_tablet_device_duplicate_returns_409(self) -> None:
        TabletDevice.objects.create(name="Tablet 1", device_code="TAB-001", is_active=True)
        response = self.client.post(
            "/api/v1/tablet-devices",
            data=json.dumps({"name": "Tablet 1", "device_code": "TAB-001", "is_active": True}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 409)

    def test_get_tablet_devices_filter_and_search(self) -> None:
        TabletDevice.objects.create(name="Tablet Active", device_code="TAB-ACT", is_active=True)
        TabletDevice.objects.create(name="Tablet Offline", device_code="TAB-OFF", is_active=False)
        response = self.client.get("/api/v1/tablet-devices?is_active=true&search=act")
        self.assertEqual(response.status_code, 200)
        items = response.json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["device_code"], "TAB-ACT")

    def test_get_tablet_devices_invalid_is_active_returns_400(self) -> None:
        response = self.client.get("/api/v1/tablet-devices?is_active=maybe")
        self.assertEqual(response.status_code, 400)

    def test_get_tablet_device_detail(self) -> None:
        device = TabletDevice.objects.create(name="Tablet 1", device_code="TAB-001", is_active=True)
        response = self.client.get(f"/api/v1/tablet-devices/{device.id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], str(device.id))

    def test_patch_tablet_device(self) -> None:
        device = TabletDevice.objects.create(name="Tablet 1", device_code="TAB-001", is_active=True)
        response = self.client.patch(
            f"/api/v1/tablet-devices/{device.id}",
            data=json.dumps({"name": "Tablet 1A", "is_active": False}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["name"], "Tablet 1A")
        self.assertFalse(payload["is_active"])

    def test_delete_tablet_device_soft_deactivates(self) -> None:
        device = TabletDevice.objects.create(name="Tablet 1", device_code="TAB-001", is_active=True)
        response = self.client.delete(f"/api/v1/tablet-devices/{device.id}")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["is_active"])
        device.refresh_from_db()
        self.assertFalse(device.is_active)

    def test_post_tablet_heartbeat_updates_last_seen_at(self) -> None:
        device = TabletDevice.objects.create(name="Tablet 1", device_code="TAB-001", is_active=True)
        self.assertIsNone(device.last_seen_at)
        response = self.client.post(
            f"/api/v1/tablet-devices/{device.id}/heartbeat",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("last_seen_at", payload)
        device.refresh_from_db()
        self.assertIsNotNone(device.last_seen_at)

    def test_tablet_device_not_found_returns_404(self) -> None:
        response = self.client.get(f"/api/v1/tablet-devices/{uuid4()}")
        self.assertEqual(response.status_code, 404)


class ClinicSitesAndRoomsApiTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()

    def test_clinic_sites_create_list_patch_delete(self) -> None:
        create_response = self.client.post(
            "/api/v1/clinic-sites",
            data=json.dumps({"code": "BERLIN-1", "name": "Berlin Central", "is_active": True}),
            content_type="application/json",
        )
        self.assertEqual(create_response.status_code, 201)
        site_id = create_response.json()["id"]

        list_response = self.client.get("/api/v1/clinic-sites?search=Berlin")
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.json()["items"]), 1)

        patch_response = self.client.patch(
            f"/api/v1/clinic-sites/{site_id}",
            data=json.dumps({"name": "Berlin Mitte"}),
            content_type="application/json",
        )
        self.assertEqual(patch_response.status_code, 200)
        self.assertEqual(patch_response.json()["name"], "Berlin Mitte")

        delete_response = self.client.delete(f"/api/v1/clinic-sites/{site_id}")
        self.assertEqual(delete_response.status_code, 200)
        self.assertFalse(delete_response.json()["is_active"])

    def test_clinic_site_duplicate_code_returns_409(self) -> None:
        ClinicSite.objects.create(code="BERLIN-1", name="Berlin Central", is_active=True)
        response = self.client.post(
            "/api/v1/clinic-sites",
            data=json.dumps({"code": "BERLIN-1", "name": "Berlin Duplicate", "is_active": True}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 409)

    def test_consulting_rooms_create_list_patch_delete(self) -> None:
        site = ClinicSite.objects.create(code="BERLIN-1", name="Berlin Central", is_active=True)
        create_response = self.client.post(
            "/api/v1/consulting-rooms",
            data=json.dumps(
                {
                    "clinic_site_id": str(site.id),
                    "code": "R01",
                    "name": "Room 1",
                    "is_active": True,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(create_response.status_code, 201)
        room_id = create_response.json()["id"]

        list_response = self.client.get(f"/api/v1/consulting-rooms?clinic_site_id={site.id}&search=Room")
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.json()["items"]), 1)

        patch_response = self.client.patch(
            f"/api/v1/consulting-rooms/{room_id}",
            data=json.dumps({"name": "Room A", "is_active": False}),
            content_type="application/json",
        )
        self.assertEqual(patch_response.status_code, 200)
        self.assertEqual(patch_response.json()["name"], "Room A")
        self.assertFalse(patch_response.json()["is_active"])

        delete_response = self.client.delete(f"/api/v1/consulting-rooms/{room_id}")
        self.assertEqual(delete_response.status_code, 200)
        self.assertFalse(delete_response.json()["is_active"])

    def test_consulting_room_duplicate_code_per_site_returns_409(self) -> None:
        site = ClinicSite.objects.create(code="BERLIN-1", name="Berlin Central", is_active=True)
        ConsultingRoom.objects.create(clinic_site=site, code="R01", name="Room 1", is_active=True)
        response = self.client.post(
            "/api/v1/consulting-rooms",
            data=json.dumps(
                {
                    "clinic_site_id": str(site.id),
                    "code": "R01",
                    "name": "Room 1 Duplicate",
                    "is_active": True,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 409)

    def test_consulting_room_create_missing_site_returns_404(self) -> None:
        response = self.client.post(
            "/api/v1/consulting-rooms",
            data=json.dumps(
                {
                    "clinic_site_id": str(uuid4()),
                    "code": "R01",
                    "name": "Room 1",
                    "is_active": True,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)
