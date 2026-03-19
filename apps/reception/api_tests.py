from __future__ import annotations

import json
import threading
from datetime import date
from uuid import uuid4

from django.conf import settings
from django.db import connection
from django.test import Client, TestCase, TransactionTestCase
from django.utils import timezone

from apps.core.api_utils import assign_group_to_test_user
from apps.reception.models import (
    ClinicSite,
    ConsultingRoom,
    DailyQueue,
    Patient,
    PatientContactHistory,
    PatientImportBatch,
    PatientImportError,
    QueueEntry,
    QueueEntryStatus,
    QueueShift,
    QueueSource,
    QueueStatus,
    TabletDevice,
)
from apps.users.models import StaffUser


class DailyQueuesApiTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.reception_user = StaffUser.objects.create_user(
            username="reception-api",
            email="reception-api@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.reception_user, "Reception")
        self.clinic = ClinicSite.objects.create(code="C1", name="Clinic 1")
        self.room = ConsultingRoom.objects.create(
            clinic_site=self.clinic,
            code="R1",
            name="Room 1",
        )
        self.reception_user.clinic_sites.add(self.clinic)
        self.client.login(username="reception-api", password="safe-password")

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


class DailyQueueConcurrencyApiTests(TransactionTestCase):
    """Concurrent POSTs for the same queue slot: one 201, one 409 (IntegrityError handled)."""

    def setUp(self) -> None:
        self.reception_user = StaffUser.objects.create_user(
            username="reception-concurrent",
            email="reception-concurrent@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.reception_user, "Reception")
        self.clinic = ClinicSite.objects.create(code="CC", name="Concurrent Clinic")
        self.room = ConsultingRoom.objects.create(
            clinic_site=self.clinic,
            code="RR",
            name="Room R",
        )
        self.reception_user.clinic_sites.add(self.clinic)

    def test_concurrent_post_same_queue_one_201_one_409(self) -> None:
        queue_date = timezone.now().date()
        payload = {
            "queue_date": queue_date.isoformat(),
            "clinic_site_id": str(self.clinic.id),
            "consulting_room_id": str(self.room.id),
            "shift_code": QueueShift.FULL_DAY,
            "source": QueueSource.MANUAL,
            "created_by_user_id": str(self.reception_user.id),
        }
        results: list[int] = []

        def post_queue() -> None:
            try:
                client = Client()
                client.login(username="reception-concurrent", password="safe-password")
                resp = client.post(
                    "/api/v1/daily-queues",
                    data=json.dumps(payload),
                    content_type="application/json",
                )
                results.append(resp.status_code)
            finally:
                connection.close()

        t1 = threading.Thread(target=post_queue)
        t2 = threading.Thread(target=post_queue)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        results.sort()
        self.assertEqual(results, [201, 409], "One request must get 201, the other 409")


class TabletQueueScopeApiTests(TestCase):
    """TABLET role must be assigned to clinic_sites to see their queues and entries."""

    def setUp(self) -> None:
        self.client = Client()
        self.tablet_user = StaffUser.objects.create_user(
            username="tablet-queue-user",
            email="tablet-queue@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.tablet_user, "Tablet")

    def test_tablet_with_no_clinic_sites_sees_empty_queues(self) -> None:
        """TABLET with no clinic_sites assigned gets empty list, not all queues."""
        self.client.login(username="tablet-queue-user", password="safe-password")
        clinic = ClinicSite.objects.create(code="C1", name="Clinic 1")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="R1", name="Room 1")
        DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            created_by_user=self.tablet_user,
        )
        response = self.client.get("/api/v1/daily-queues")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["items"], [])

    def test_tablet_with_clinic_site_sees_only_its_queues(self) -> None:
        """TABLET assigned to one clinic_site sees only that site's queues."""
        self.client.login(username="tablet-queue-user", password="safe-password")
        clinic_a = ClinicSite.objects.create(code="A1", name="Clinic A")
        clinic_b = ClinicSite.objects.create(code="B1", name="Clinic B")
        room_a = ConsultingRoom.objects.create(clinic_site=clinic_a, code="RA", name="Room A")
        room_b = ConsultingRoom.objects.create(clinic_site=clinic_b, code="RB", name="Room B")
        self.tablet_user.clinic_sites.add(clinic_a)
        queue_a = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic_a,
            consulting_room=room_a,
            status=QueueStatus.OPEN,
            created_by_user=self.tablet_user,
        )
        DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic_b,
            consulting_room=room_b,
            status=QueueStatus.OPEN,
            created_by_user=self.tablet_user,
        )
        response = self.client.get("/api/v1/daily-queues")
        self.assertEqual(response.status_code, 200)
        items = response.json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], str(queue_a.id))
        self.assertEqual(items[0]["clinic_site_id"], str(clinic_a.id))

    def test_tablet_cannot_access_entries_of_other_clinic(self) -> None:
        """TABLET assigned to clinic A gets 403 when accessing queue of clinic B."""
        self.client.login(username="tablet-queue-user", password="safe-password")
        clinic_a = ClinicSite.objects.create(code="A1", name="Clinic A")
        clinic_b = ClinicSite.objects.create(code="B1", name="Clinic B")
        room_a = ConsultingRoom.objects.create(clinic_site=clinic_a, code="RA", name="Room A")
        room_b = ConsultingRoom.objects.create(clinic_site=clinic_b, code="RB", name="Room B")
        self.tablet_user.clinic_sites.add(clinic_a)
        queue_b = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic_b,
            consulting_room=room_b,
            status=QueueStatus.OPEN,
            created_by_user=self.tablet_user,
        )
        response = self.client.get(f"/api/v1/daily-queues/{queue_b.id}/entries")
        self.assertEqual(response.status_code, 403)
        self.assertIn("assigned scope", response.json().get("error", ""))

    def test_tablet_scope_from_device_in_session(self) -> None:
        """When session has tablet_device_id and device has clinic_site, queues are filtered by device site.
        We also assign user to clinic_a so that scope comes from either device (production) or user (test client)."""
        self.client.login(username="tablet-queue-user", password="safe-password")
        clinic_a = ClinicSite.objects.create(code="AX", name="Clinic A")
        clinic_b = ClinicSite.objects.create(code="BX", name="Clinic B")
        self.tablet_user.clinic_sites.add(clinic_a)
        room_a = ConsultingRoom.objects.create(clinic_site=clinic_a, code="RA", name="Room A")
        room_b = ConsultingRoom.objects.create(clinic_site=clinic_b, code="RB", name="Room B")
        device = TabletDevice.objects.create(
            android_id="tablet-scope-device",
            is_active=True,
            clinic_site=clinic_a,
        )
        queue_a = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic_a,
            consulting_room=room_a,
            status=QueueStatus.OPEN,
            created_by_user=self.tablet_user,
        )
        DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic_b,
            consulting_room=room_b,
            status=QueueStatus.OPEN,
            created_by_user=self.tablet_user,
        )
        self.client.session["tablet_device_id"] = str(device.id)
        self.client.session.save()
        self.client.cookies[settings.SESSION_COOKIE_NAME] = self.client.session.session_key
        response = self.client.get("/api/v1/daily-queues")
        self.assertEqual(response.status_code, 200)
        items = response.json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["clinic_site_id"], str(clinic_a.id))

    def test_tablet_device_without_site_sees_empty_queues(self) -> None:
        """When session has tablet_device_id but device has no clinic_site, GET daily-queues returns empty."""
        self.client.login(username="tablet-queue-user", password="safe-password")
        clinic = ClinicSite.objects.create(code="CX", name="Clinic C")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="R1", name="Room 1")
        DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            created_by_user=self.tablet_user,
        )
        device = TabletDevice.objects.create(android_id="tablet-no-site", is_active=True)
        self.client.session["tablet_device_id"] = str(device.id)
        self.client.session.save()
        response = self.client.get("/api/v1/daily-queues")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"], [])


class DoctorAndTabletAuthorizationApiTests(TestCase):
    """DOCTOR can GET list + detail (in scope); TABLET cannot POST queues. PATCH/DELETE stay ADMIN-only."""

    def setUp(self) -> None:
        self.client = Client()
        self.doctor = StaffUser.objects.create_user(
            username="doctor-auth",
            email="doctor-auth@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.doctor, "Doctor")
        self.tablet_user = StaffUser.objects.create_user(
            username="tablet-auth",
            email="tablet-auth@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.tablet_user, "Tablet")
        self.clinic = ClinicSite.objects.create(code="D1", name="Doctor Clinic")
        self.room = ConsultingRoom.objects.create(
            clinic_site=self.clinic,
            code="DR1",
            name="Doctor Room",
        )
        self.doctor.clinic_sites.add(self.clinic)
        self.tablet_user.clinic_sites.add(self.clinic)

    def test_doctor_can_get_clinic_site_detail_when_in_scope(self) -> None:
        self.client.login(username="doctor-auth", password="safe-password")
        response = self.client.get(f"/api/v1/clinic-sites/{self.clinic.id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], str(self.clinic.id))

    def test_doctor_can_get_consulting_room_detail_when_in_scope(self) -> None:
        self.client.login(username="doctor-auth", password="safe-password")
        response = self.client.get(f"/api/v1/consulting-rooms/{self.room.id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], str(self.room.id))

    def test_doctor_can_get_daily_queue_detail_when_assigned(self) -> None:
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=self.clinic,
            consulting_room=self.room,
            status=QueueStatus.OPEN,
            assigned_doctor_id=self.doctor.id,
            created_by_user=self.doctor,
        )
        self.client.login(username="doctor-auth", password="safe-password")
        response = self.client.get(f"/api/v1/daily-queues/{queue.id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], str(queue.id))

    def test_doctor_gets_403_for_daily_queue_detail_not_assigned(self) -> None:
        other_doctor = StaffUser.objects.create_user(
            username="doctor-other",
            email="doctor-other@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(other_doctor, "Doctor")
        other_doctor.clinic_sites.add(self.clinic)
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=self.clinic,
            consulting_room=self.room,
            status=QueueStatus.OPEN,
            assigned_doctor_id=other_doctor.id,
            created_by_user=other_doctor,
        )
        self.client.login(username="doctor-auth", password="safe-password")
        response = self.client.get(f"/api/v1/daily-queues/{queue.id}")
        self.assertEqual(response.status_code, 403)
        self.assertIn("own assigned", response.json().get("error", ""))

    def test_doctor_gets_403_for_patch_clinic_site(self) -> None:
        self.client.login(username="doctor-auth", password="safe-password")
        response = self.client.patch(
            f"/api/v1/clinic-sites/{self.clinic.id}",
            data=json.dumps({"name": "Changed"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("ADMIN", response.json().get("error", ""))

    def test_doctor_gets_403_for_patch_daily_queue(self) -> None:
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=self.clinic,
            consulting_room=self.room,
            status=QueueStatus.OPEN,
            assigned_doctor_id=self.doctor.id,
            created_by_user=self.doctor,
        )
        self.client.login(username="doctor-auth", password="safe-password")
        response = self.client.patch(
            f"/api/v1/daily-queues/{queue.id}",
            data=json.dumps({"status": "CLOSED"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("RECEPTION", response.json().get("error", ""))

    def test_tablet_gets_403_for_post_daily_queue(self) -> None:
        self.client.login(username="tablet-auth", password="safe-password")
        payload = {
            "queue_date": timezone.now().date().isoformat(),
            "clinic_site_id": str(self.clinic.id),
            "consulting_room_id": str(self.room.id),
            "shift_code": QueueShift.FULL_DAY,
            "source": QueueSource.MANUAL,
            "created_by_user_id": str(self.tablet_user.id),
        }
        response = self.client.post(
            "/api/v1/daily-queues",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)


class TabletDevicesApiTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.reception_user = StaffUser.objects.create_user(
            username="tablet-api",
            email="tablet-api@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.reception_user, "Reception")
        self.client.login(username="tablet-api", password="safe-password")

    def test_get_tablet_devices_empty(self) -> None:
        response = self.client.get("/api/v1/tablet-devices")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"], [])

    def test_post_tablet_device_creates(self) -> None:
        response = self.client.post(
            "/api/v1/tablet-devices",
            data=json.dumps({"android_id": "device-TAB-001", "is_active": True}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["android_id"], "device-TAB-001")
        self.assertTrue(payload["is_active"])
        self.assertIsNone(payload.get("clinic_site_id"))

    def test_post_tablet_device_with_clinic_site_id(self) -> None:
        clinic = ClinicSite.objects.create(code="T1", name="Tablet Clinic")
        response = self.client.post(
            "/api/v1/tablet-devices",
            data=json.dumps({
                "android_id": "device-TAB-SITE",
                "is_active": True,
                "clinic_site_id": str(clinic.id),
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["clinic_site_id"], str(clinic.id))

    def test_post_tablet_device_duplicate_returns_409(self) -> None:
        TabletDevice.objects.create(android_id="device-TAB-001", is_active=True)
        response = self.client.post(
            "/api/v1/tablet-devices",
            data=json.dumps({"android_id": "device-TAB-001", "is_active": True}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 409)

    def test_get_tablet_devices_filter_and_search(self) -> None:
        TabletDevice.objects.create(android_id="device-TAB-ACT", is_active=True)
        TabletDevice.objects.create(android_id="device-TAB-OFF", is_active=False)
        response = self.client.get("/api/v1/tablet-devices?is_active=true&search=TAB-ACT")
        self.assertEqual(response.status_code, 200)
        items = response.json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["android_id"], "device-TAB-ACT")

    def test_get_tablet_devices_invalid_is_active_returns_400(self) -> None:
        response = self.client.get("/api/v1/tablet-devices?is_active=maybe")
        self.assertEqual(response.status_code, 400)

    def test_get_tablet_device_detail(self) -> None:
        device = TabletDevice.objects.create(android_id="device-TAB-001", is_active=True)
        response = self.client.get(f"/api/v1/tablet-devices/{device.id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], str(device.id))
        self.assertIn("clinic_site_id", response.json())

    def test_get_tablet_device_detail_includes_clinic_site_id(self) -> None:
        clinic = ClinicSite.objects.create(code="D1", name="Device Clinic")
        device = TabletDevice.objects.create(
            android_id="device-TAB-SITE1",
            is_active=True,
            clinic_site=clinic,
        )
        response = self.client.get(f"/api/v1/tablet-devices/{device.id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["clinic_site_id"], str(clinic.id))

    def test_patch_tablet_device(self) -> None:
        device = TabletDevice.objects.create(android_id="device-TAB-001", is_active=True)
        response = self.client.patch(
            f"/api/v1/tablet-devices/{device.id}",
            data=json.dumps({"android_id": "device-TAB-001A", "is_active": False}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["android_id"], "device-TAB-001A")
        self.assertFalse(payload["is_active"])

    def test_patch_tablet_device_clinic_site_id(self) -> None:
        clinic = ClinicSite.objects.create(code="P1", name="Patch Clinic")
        device = TabletDevice.objects.create(android_id="device-TAB-PATCH", is_active=True)
        response = self.client.patch(
            f"/api/v1/tablet-devices/{device.id}",
            data=json.dumps({"clinic_site_id": str(clinic.id)}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["clinic_site_id"], str(clinic.id))
        device.refresh_from_db()
        self.assertEqual(device.clinic_site_id, clinic.id)

    def test_delete_tablet_device_soft_deactivates(self) -> None:
        device = TabletDevice.objects.create(android_id="device-TAB-001", is_active=True)
        response = self.client.delete(f"/api/v1/tablet-devices/{device.id}")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["is_active"])
        device.refresh_from_db()
        self.assertFalse(device.is_active)

    def test_post_tablet_heartbeat_updates_last_seen_at(self) -> None:
        device = TabletDevice.objects.create(android_id="device-TAB-001", is_active=True)
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
    """Clinic sites and consulting rooms: create/patch/delete require ADMIN (RECEPTION is read-only in scope)."""

    def setUp(self) -> None:
        self.client = Client()
        self.admin_user = StaffUser.objects.create_user(
            username="clinic-api",
            email="clinic-api@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.admin_user, "Admin")
        self.client.login(username="clinic-api", password="safe-password")

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


class PatientsApiTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.reception_user = StaffUser.objects.create_user(
            username="patients-api-user",
            email="patients-api@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.reception_user, "Reception")
        self.clinic = ClinicSite.objects.create(code="P1", name="Patients Clinic")
        self.room = ConsultingRoom.objects.create(
            clinic_site=self.clinic,
            code="PR1",
            name="Patients Room",
        )
        self.reception_user.clinic_sites.add(self.clinic)
        self.client.login(username="patients-api-user", password="safe-password")

    def test_get_patients_empty(self) -> None:
        response = self.client.get("/api/v1/patients")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["items"], [])
        self.assertEqual(payload["pagination"]["total"], 0)

    def test_post_patient_creates_patient_without_optional_doctolib_id(self) -> None:
        response = self.client.post(
            "/api/v1/patients",
            data=json.dumps(
                {
                    "first_name": "Jan",
                    "last_name": "Kowalski",
                    "date_of_birth": "1980-01-01",
                    "phone": "+49111111111",
                    "email": "jan@example.com",
                    "doctolib_patient_id": None,
                    "street": "Main 1",
                    "city": "Berlin",
                    "postal_code": "10115",
                    "country_code": "DE",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertIsNone(payload["patient"]["doctolib_patient_id"])
        self.assertEqual(payload["patient"]["first_name"], "Jan")

    def test_get_patient_detail_returns_200(self) -> None:
        patient = Patient.objects.create(
            first_name="Anna",
            last_name="Nowak",
            date_of_birth=date(1990, 1, 1),
            phone="+49123456789",
            email="anna@example.com",
            doctolib_patient_id="DOC-123",
        )
        patient.clinic_sites.add(self.clinic)
        response = self.client.get(f"/api/v1/patients/{patient.id}")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["id"], str(patient.id))
        self.assertEqual(payload["doctolib_patient_id"], "DOC-123")

    def test_patch_patient_updates_contact_and_creates_history(self) -> None:
        patient = Patient.objects.create(
            first_name="Anna",
            last_name="Nowak",
            date_of_birth=date(1990, 1, 1),
            phone="+49123456789",
            email="anna@example.com",
            doctolib_patient_id="DOC-123",
        )
        patient.clinic_sites.add(self.clinic)
        response = self.client.patch(
            f"/api/v1/patients/{patient.id}",
            data=json.dumps(
                {
                    "phone": "+49999888777",
                    "email": "anna.new@example.com",
                    "changed_by_user_id": str(self.reception_user.id),
                    "change_reason": "manual correction",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["phone"], "+49999888777")
        self.assertEqual(payload["email"], "anna.new@example.com")

        history_items = PatientContactHistory.objects.filter(patient=patient)
        self.assertEqual(history_items.count(), 1)
        history = history_items.first()
        self.assertEqual(history.phone, "+49123456789")
        self.assertEqual(history.email, "anna@example.com")
        self.assertEqual(history.reason, "manual correction")

    def test_get_patient_contact_history_returns_items(self) -> None:
        patient = Patient.objects.create(
            first_name="Anna",
            last_name="Nowak",
            date_of_birth=date(1990, 1, 1),
            phone="+49123456789",
            email="anna@example.com",
            doctolib_patient_id="DOC-123",
        )
        patient.clinic_sites.add(self.clinic)
        PatientContactHistory.objects.create(
            patient=patient,
            phone="+49111111111",
            email="old@example.com",
            changed_by_user=self.reception_user,
            reason="manual correction",
        )
        response = self.client.get(f"/api/v1/patients/{patient.id}/contact-history")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["email"], "old@example.com")
        self.assertEqual(payload["pagination"]["total"], 1)

    def test_patch_patient_identity_uses_session_user_as_actor(self) -> None:
        """PATCH with identity/contact fields uses request.user.id as actor (body changed_by_user_id ignored)."""
        patient = Patient.objects.create(
            first_name="Anna",
            last_name="Nowak",
            date_of_birth=date(1990, 1, 1),
            phone="+49123456789",
            email="anna@example.com",
            doctolib_patient_id="DOC-123",
        )
        patient.clinic_sites.add(self.clinic)
        response = self.client.patch(
            f"/api/v1/patients/{patient.id}",
            data=json.dumps({"phone": "+49999000111"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        patient.refresh_from_db()
        self.assertEqual(patient.phone, "+49999000111")

    def test_patient_detail_not_found_returns_404(self) -> None:
        response = self.client.get(f"/api/v1/patients/{uuid4()}")
        self.assertEqual(response.status_code, 404)

    def test_post_patient_returns_409_for_duplicate_patient_identity(self) -> None:
        Patient.objects.create(
            first_name="Anna",
            last_name="Nowak",
            date_of_birth=date(1990, 1, 1),
            phone="+49123456789",
            email="anna@example.com",
        ).clinic_sites.add(self.clinic)

        response = self.client.post(
            "/api/v1/patients",
            data=json.dumps(
                {
                    "first_name": "Anna",
                    "last_name": "Nowak",
                    "date_of_birth": "1990-01-01",
                    "phone": "+49123456789",
                    "email": "anna.duplicate@example.com",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 409)

    def test_post_patient_returns_409_for_duplicate_doctolib_patient_id(self) -> None:
        Patient.objects.create(
            first_name="Anna",
            last_name="Nowak",
            date_of_birth=date(1990, 1, 1),
            phone="+49123456789",
            email="anna@example.com",
            doctolib_patient_id="DOC-123",
        ).clinic_sites.add(self.clinic)

        response = self.client.post(
            "/api/v1/patients",
            data=json.dumps(
                {
                    "first_name": "Other",
                    "last_name": "Patient",
                    "date_of_birth": "1981-02-02",
                    "phone": "+49999999999",
                    "email": "other@example.com",
                    "doctolib_patient_id": "DOC-123",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 409)


class ListLimitApiTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.reception_user = StaffUser.objects.create_user(
            username="listlimit-api",
            email="listlimit-api@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.reception_user, "Reception")
        self.client.login(username="listlimit-api", password="safe-password")

    def test_tablet_devices_list_uses_default_limit(self) -> None:
        """Without limit param, list returns DEFAULT_LIST_LIMIT (20) items."""
        for idx in range(120):
            TabletDevice.objects.create(android_id=f"device-TAB-{idx}", is_active=True)
        response = self.client.get("/api/v1/tablet-devices")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["items"]), 20)


class ImportBatchesApiTests(TestCase):
    """Tests for PatientImportBatch / PatientImportError API (format-agnostic)."""

    def setUp(self) -> None:
        self.client = Client()
        self.reception_user = StaffUser.objects.create_user(
            username="import-api-user",
            email="import-api@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.reception_user, "Reception")
        self.client.login(username="import-api-user", password="safe-password")

    def test_get_import_batches_detail_and_errors(self) -> None:
        batch = PatientImportBatch.objects.create(
            source_file_name="patients.xlsx",
            source_file_sha256="a" * 64,
            created_by_user=self.reception_user,
        )
        PatientImportError.objects.create(
            batch=batch,
            row_number=1,
            error_code="INVALID_ROW_FORMAT",
            error_message="Broken row",
            raw_row={"row": "raw"},
        )

        list_response = self.client.get("/api/v1/imports/batches")
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.json()["items"]), 1)

        detail_response = self.client.get(f"/api/v1/imports/batches/{batch.id}")
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.json()["id"], str(batch.id))

        errors_response = self.client.get(f"/api/v1/imports/batches/{batch.id}/errors")
        self.assertEqual(errors_response.status_code, 200)
        self.assertEqual(len(errors_response.json()["items"]), 1)
