from __future__ import annotations

from django.test import Client, TestCase

from apps.core.api_utils import assign_group_to_test_user
from apps.operations.models import AuditEvent
from apps.users.models import StaffUser

URL = "/api/v1/audit-events"


class AuditEventsApiTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()

        self.admin = StaffUser.objects.create_user(
            username="audit-admin",
            email="audit-admin@ex.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.admin, "Admin")

        self.doctor = StaffUser.objects.create_user(
            username="audit-doctor",
            email="audit-doc@ex.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.doctor, "Doctor")

        self.reception = StaffUser.objects.create_user(
            username="audit-rec",
            email="audit-rec@ex.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.reception, "Reception")

        self.evt_admin = AuditEvent.objects.create(
            event_type="TEST_EVENT",
            actor_user=self.admin,
        )
        self.evt_doctor = AuditEvent.objects.create(
            event_type="DOCTOR_EVENT",
            actor_user=self.doctor,
            metadata={
                "assigned_doctor_id": str(self.doctor.id),
            },
        )

    # -- auth / role -------------------------------------------------

    def test_unauthenticated_is_rejected(self) -> None:
        anon = Client()
        resp = anon.get(URL)
        self.assertIn(resp.status_code, (302, 401))

    def test_wrong_role_returns_403(self) -> None:
        self.client.login(username="audit-rec", password="x")
        resp = self.client.get(URL)
        self.assertEqual(resp.status_code, 403)

    def test_post_returns_405(self) -> None:
        self.client.login(username="audit-admin", password="x")
        resp = self.client.post(URL, data="{}", content_type="application/json")
        self.assertEqual(resp.status_code, 405)

    # -- admin functional --------------------------------------------

    def test_admin_get_returns_items_and_pagination(self) -> None:
        self.client.login(username="audit-admin", password="x")
        resp = self.client.get(URL)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("items", body)
        self.assertIn("pagination", body)
        self.assertGreaterEqual(body["pagination"]["total"], 2)

    def test_admin_sees_all_events(self) -> None:
        self.client.login(username="audit-admin", password="x")
        resp = self.client.get(URL)
        ids = {i["id"] for i in resp.json()["items"]}
        self.assertIn(str(self.evt_admin.id), ids)
        self.assertIn(str(self.evt_doctor.id), ids)

    # -- doctor functional -------------------------------------------

    def test_doctor_get_returns_200(self) -> None:
        self.client.login(username="audit-doctor", password="x")
        resp = self.client.get(URL)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("items", body)
        self.assertIn("pagination", body)

    def test_doctor_sees_only_own_events(self) -> None:
        self.client.login(username="audit-doctor", password="x")
        resp = self.client.get(URL)
        ids = {i["id"] for i in resp.json()["items"]}
        self.assertIn(str(self.evt_doctor.id), ids)
        self.assertNotIn(str(self.evt_admin.id), ids)

    # -- query-param edge cases --------------------------------------

    def test_invalid_patient_id_is_ignored(self) -> None:
        self.client.login(username="audit-admin", password="x")
        resp = self.client.get(URL, {"patient_id": "not-a-uuid"})
        self.assertEqual(resp.status_code, 200)
