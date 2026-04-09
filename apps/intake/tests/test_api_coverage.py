"""HTTP-contract tests for untested intake API endpoints.

Covers: signature, anamnesis, submit, outbox-events access,
outbox-process access. Focuses on status codes and auth/role
enforcement — business logic is covered in service tests.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from uuid import uuid4

from django.test import Client, TestCase
from django.utils import timezone

from apps.core.api_utils import assign_group_to_test_user
from apps.intake.models import IntakeStatus, PatientIntakeForm
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

_PW = "safe-password"


def _create_intake_form(*, created_by: StaffUser) -> PatientIntakeForm:
    """Minimal fixture: clinic → queue → patient → entry → form."""
    sfx = uuid4().hex[:6]
    clinic = ClinicSite.objects.create(code=f"C{sfx[:3].upper()}", name=f"Clinic {sfx}")
    room = ConsultingRoom.objects.create(
        clinic_site=clinic, code=f"R{sfx[:2]}", name=f"R{sfx[:2]}"
    )
    queue = DailyQueue.objects.create(
        queue_date=timezone.now().date(),
        clinic_site=clinic,
        consulting_room=room,
        status=QueueStatus.OPEN,
        created_by_user=created_by,
    )
    digit_sfx = "".join(str(ord(c) % 10) for c in sfx[:4])
    patient = Patient.objects.create(
        first_name="Test",
        last_name="Patient",
        date_of_birth=date(1990, 1, 1),
        phone=f"+48500{digit_sfx}00",
        email=f"t-{sfx}@example.com",
    )
    entry = QueueEntry.objects.create(
        daily_queue=queue,
        patient=patient,
        entry_status=QueueEntryStatus.IN_PROGRESS,
        position_no=1,
        created_by_user=created_by,
    )
    sess = PatientFormSession.objects.create(
        queue_entry=entry,
        form_locale="de-DE",
        expires_at=timezone.now() + timedelta(hours=1),
        created_by_user=created_by,
    )
    return PatientIntakeForm.objects.create(
        queue_entry=entry,
        session=sess,
        form_status=IntakeStatus.IN_PROGRESS,
    )


# ---------------------------------------------------------------
# 1. intake_form_signature_view  POST .../signature
# ---------------------------------------------------------------


class IntakeFormSignatureViewTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.rec_user = StaffUser.objects.create_user(
            username="sig-rec",
            email="sig-rec@ex.com",
            password=_PW,
            is_staff=True,
        )
        assign_group_to_test_user(self.rec_user, "Reception")
        self.doc_user = StaffUser.objects.create_user(
            username="sig-doc",
            email="sig-doc@ex.com",
            password=_PW,
            is_staff=True,
        )
        assign_group_to_test_user(self.doc_user, "Doctor")
        self.intake_form = _create_intake_form(created_by=self.rec_user)

    def _url(self, form_id=None) -> str:
        fid = form_id or self.intake_form.id
        return f"/api/v1/intake-forms/{fid}/signature"

    def test_unauthenticated_returns_401(self) -> None:
        resp = self.client.post(
            self._url(),
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 401)

    def test_doctor_returns_403(self) -> None:
        self.client.login(username="sig-doc", password=_PW)
        resp = self.client.post(
            self._url(),
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_get_returns_405(self) -> None:
        self.client.login(username="sig-rec", password=_PW)
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, 405)

    def test_nonexistent_form_returns_404(self) -> None:
        self.client.login(username="sig-rec", password=_PW)
        resp = self.client.post(
            self._url(uuid4()),
            data=json.dumps({"signature_base64": "data:,"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 404)

    def test_invalid_json_returns_400(self) -> None:
        self.client.login(username="sig-rec", password=_PW)
        resp = self.client.post(
            self._url(),
            data="NOT_JSON{{{",
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_missing_required_field_returns_400(self) -> None:
        self.client.login(username="sig-rec", password=_PW)
        resp = self.client.post(
            self._url(),
            data=json.dumps({"wrong_key": "x"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)


# ---------------------------------------------------------------
# 2. intake_form_anamnesis_view  PUT .../anamnesis
# ---------------------------------------------------------------


class IntakeFormAnamnesisViewTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.rec_user = StaffUser.objects.create_user(
            username="anam-rec",
            email="anam-rec@ex.com",
            password=_PW,
            is_staff=True,
        )
        assign_group_to_test_user(self.rec_user, "Reception")
        self.doc_user = StaffUser.objects.create_user(
            username="anam-doc",
            email="anam-doc@ex.com",
            password=_PW,
            is_staff=True,
        )
        assign_group_to_test_user(self.doc_user, "Doctor")
        self.intake_form = _create_intake_form(created_by=self.rec_user)

    def _url(self, form_id=None) -> str:
        fid = form_id or self.intake_form.id
        return f"/api/v1/intake-forms/{fid}/anamnesis"

    def test_post_returns_405(self) -> None:
        self.client.login(username="anam-rec", password=_PW)
        resp = self.client.post(
            self._url(),
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 405)

    def test_doctor_returns_403(self) -> None:
        self.client.login(username="anam-doc", password=_PW)
        resp = self.client.put(
            self._url(),
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_nonexistent_form_returns_404(self) -> None:
        self.client.login(username="anam-rec", password=_PW)
        resp = self.client.put(
            self._url(uuid4()),
            data=json.dumps({"anamnesis_schema_version": 1, "answers": []}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 404)

    def test_invalid_json_returns_400(self) -> None:
        self.client.login(username="anam-rec", password=_PW)
        resp = self.client.put(
            self._url(),
            data="BAD_JSON{",
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_missing_required_field_returns_400(self) -> None:
        self.client.login(username="anam-rec", password=_PW)
        resp = self.client.put(
            self._url(),
            data=json.dumps({"wrong_field": 1}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)


# ---------------------------------------------------------------
# 3. intake_form_submit_view  POST .../submit
# ---------------------------------------------------------------


class IntakeFormSubmitViewTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.rec_user = StaffUser.objects.create_user(
            username="submit-rec",
            email="submit-rec@ex.com",
            password=_PW,
            is_staff=True,
        )
        assign_group_to_test_user(self.rec_user, "Reception")
        self.doc_user = StaffUser.objects.create_user(
            username="submit-doc",
            email="submit-doc@ex.com",
            password=_PW,
            is_staff=True,
        )
        assign_group_to_test_user(self.doc_user, "Doctor")
        self.intake_form = _create_intake_form(created_by=self.rec_user)

    def _url(self, form_id=None) -> str:
        fid = form_id or self.intake_form.id
        return f"/api/v1/intake-forms/{fid}/submit"

    def test_get_returns_405(self) -> None:
        self.client.login(username="submit-rec", password=_PW)
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, 405)

    def test_doctor_returns_403(self) -> None:
        self.client.login(username="submit-doc", password=_PW)
        resp = self.client.post(
            self._url(),
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_nonexistent_form_returns_404(self) -> None:
        self.client.login(username="submit-rec", password=_PW)
        resp = self.client.post(
            self._url(uuid4()),
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 404)


# ---------------------------------------------------------------
# 4. intake_outbox_events_view  GET /intake-outbox-events
# ---------------------------------------------------------------


class IntakeOutboxEventsAccessTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.rec_user = StaffUser.objects.create_user(
            username="outbox-evt-rec",
            email="outbox-evt-rec@ex.com",
            password=_PW,
            is_staff=True,
        )
        assign_group_to_test_user(self.rec_user, "Reception")
        self.doc_user = StaffUser.objects.create_user(
            username="outbox-evt-doc",
            email="outbox-evt-doc@ex.com",
            password=_PW,
            is_staff=True,
        )
        assign_group_to_test_user(self.doc_user, "Doctor")

    def _url(self) -> str:
        return "/api/v1/intake-outbox-events"

    def test_post_returns_405(self) -> None:
        self.client.login(username="outbox-evt-rec", password=_PW)
        resp = self.client.post(
            self._url(),
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 405)

    def test_doctor_returns_403(self) -> None:
        self.client.login(username="outbox-evt-doc", password=_PW)
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, 403)

    def test_valid_get_returns_200_with_list(self) -> None:
        self.client.login(username="outbox-evt-rec", password=_PW)
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("results", data)
        self.assertIsInstance(data["results"], list)
        self.assertIn("count", data)


# ---------------------------------------------------------------
# 5. intake_outbox_process_view  POST .../process
# ---------------------------------------------------------------


class IntakeOutboxProcessAccessTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.admin_user = StaffUser.objects.create_user(
            username="outbox-proc-admin",
            email="outbox-proc-admin@ex.com",
            password=_PW,
            is_staff=True,
        )
        assign_group_to_test_user(self.admin_user, "Admin")
        self.rec_user = StaffUser.objects.create_user(
            username="outbox-proc-rec",
            email="outbox-proc-rec@ex.com",
            password=_PW,
            is_staff=True,
        )
        assign_group_to_test_user(self.rec_user, "Reception")

    def _url(self) -> str:
        return "/api/v1/operations/intake-outbox/process"

    def test_get_returns_405(self) -> None:
        self.client.login(username="outbox-proc-admin", password=_PW)
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, 405)

    def test_reception_returns_403(self) -> None:
        self.client.login(username="outbox-proc-rec", password=_PW)
        resp = self.client.post(
            self._url(),
            data=json.dumps({"limit": 5}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_admin_post_returns_202(self) -> None:
        self.client.login(username="outbox-proc-admin", password=_PW)
        resp = self.client.post(
            self._url(),
            data=json.dumps({"limit": 5}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 202)
        data = resp.json()
        self.assertIn("processed", data)
        self.assertIn("failed", data)
