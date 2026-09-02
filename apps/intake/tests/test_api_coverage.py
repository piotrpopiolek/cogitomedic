"""HTTP-contract tests for untested intake API endpoints.

Covers: signature, anamnesis, submit, outbox-events access,
outbox-process access. Focuses on status codes and auth/role
enforcement — business logic is covered in service tests.

Also targets selected ``api_views`` branches for submit (body parsing,
domain/state errors) and GET form context (clinic scope, patient payload).
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import Client, TestCase, override_settings
from django.utils import timezone

from apps.core.api_utils import assign_group_to_test_user
from apps.core.domain_messages import domain_message
from apps.core.exceptions import (
    DomainError,
    InvalidRequestBodyEncoding,
    StateTransitionError,
)
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
from apps.reception.process_types import PROCESS_TYPE_TELEDERM
from apps.users.models import StaffUser

_PW = "safe-password"


def _create_intake_form(
    *,
    created_by: StaffUser,
    clinic_site: ClinicSite | None = None,
    process_type: str | None = None,
) -> PatientIntakeForm:
    """Minimal fixture: clinic → queue → patient → entry → form.

    When ``clinic_site`` is provided, the queue is created for that site
    (reuse an existing clinic for scope tests).
    """
    sfx = uuid4().hex[:6]
    clinic = clinic_site or ClinicSite.objects.create(
        code=f"C{sfx[:3].upper()}", name=f"Clinic {sfx}"
    )
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
    entry_kwargs: dict = {
        "daily_queue": queue,
        "patient": patient,
        "entry_status": QueueEntryStatus.IN_PROGRESS,
        "position_no": 1,
        "created_by_user": created_by,
    }
    if process_type is not None:
        entry_kwargs["process_type"] = process_type
    entry = QueueEntry.objects.create(**entry_kwargs)
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


@override_settings(RATELIMIT_ENABLE=False)
class IntakeFormSubmitViewTests(TestCase):
    """Submit is rate-limited to 5/min per IP; many POSTs in one class hit 429 without disabling ratelimit here."""

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

    def test_unauthenticated_returns_401(self) -> None:
        resp = self.client.post(
            self._url(),
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 401)

    def test_invalid_json_returns_400(self) -> None:
        self.client.login(username="submit-rec", password=_PW)
        resp = self.client.post(
            self._url(),
            data="NOT_JSON{{{",
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_validation_error_on_unknown_field_returns_400(self) -> None:
        self.client.login(username="submit-rec", password=_PW)
        resp = self.client.post(
            self._url(),
            data=json.dumps({"unexpected": True}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["error_key"], "other.api.invalid_request_body")
        self.assertIn("details", resp.json())

    @patch("apps.intake.api_views.read_json_body")
    def test_invalid_body_encoding_returns_domain_error(
        self, mock_read: MagicMock
    ) -> None:
        mock_read.side_effect = InvalidRequestBodyEncoding(
            "bad utf-8",
            api_message_key="other.api.request_body_too_large",
            api_message_params={"max_bytes": 42},
            http_status=413,
        )
        self.client.login(username="submit-rec", password=_PW)
        resp = self.client.post(
            self._url(),
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 413)
        self.assertIn("error", resp.json())

    @patch("apps.intake.api_views.submit_patient_intake_form")
    def test_submit_state_transition_returns_400(self, mock_submit: MagicMock) -> None:
        mock_submit.side_effect = StateTransitionError(
            domain_message("other.domain.intake_submit_in_progress_only"),
            api_message_key="other.domain.intake_submit_in_progress_only",
        )
        self.client.login(username="submit-rec", password=_PW)
        resp = self.client.post(
            self._url(),
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.json())

    @patch("apps.intake.api_views.submit_patient_intake_form")
    def test_submit_domain_error_returns_400(self, mock_submit: MagicMock) -> None:
        mock_submit.side_effect = DomainError(
            domain_message("other.domain.intake_session_expired"),
            api_message_key="other.domain.intake_session_expired",
        )
        self.client.login(username="submit-rec", password=_PW)
        resp = self.client.post(
            self._url(),
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.json())

    def test_submit_cancelled_queue_entry_returns_400(self) -> None:
        clinic_id = self.intake_form.queue_entry.daily_queue.clinic_site_id
        self.rec_user.clinic_sites.add(clinic_id)
        self.intake_form.queue_entry.entry_status = QueueEntryStatus.CANCELLED
        self.intake_form.queue_entry.save(update_fields=["entry_status", "updated_at"])
        self.client.login(username="submit-rec", password=_PW)
        resp = self.client.post(
            self._url(),
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["error_key"], "other.domain.queue_entry_cancelled")


# ---------------------------------------------------------------
# 3b. intake_form_detail_view — GET context scope & patient (read-only)
# ---------------------------------------------------------------


class IntakeFormGetContextScopeTests(TestCase):
    """GET ``/intake-forms/<id>`` without mocking service: clinic scope + patient block."""

    def setUp(self) -> None:
        self.client = Client()
        self.admin = StaffUser.objects.create_user(
            username="ctx-admin",
            email="ctx-admin@ex.com",
            password=_PW,
            is_staff=True,
        )
        assign_group_to_test_user(self.admin, "Admin")
        self.rec_user = StaffUser.objects.create_user(
            username="ctx-rec",
            email="ctx-rec@ex.com",
            password=_PW,
            is_staff=True,
        )
        assign_group_to_test_user(self.rec_user, "Reception")
        self.clinic_own = ClinicSite.objects.create(code="CTX", name="Ctx Clinic")
        self.clinic_other = ClinicSite.objects.create(code="CTO", name="Other Ctx")
        self.rec_user.clinic_sites.add(self.clinic_own)

    def test_admin_get_includes_patient_identity_and_form_status(self) -> None:
        intake = _create_intake_form(created_by=self.admin)
        patient = intake.queue_entry.patient
        self.client.login(username="ctx-admin", password=_PW)
        resp = self.client.get(
            f"/api/v1/intake-forms/{intake.id}?form_locale=de-DE",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["form_status"], IntakeStatus.IN_PROGRESS)
        self.assertEqual(data["intake_form_id"], str(intake.id))
        self.assertIn("patient", data)
        self.assertEqual(data["patient"]["first_name"], patient.first_name)
        self.assertEqual(data["patient"]["last_name"], patient.last_name)
        self.assertEqual(data["patient"]["phone"], patient.phone)

    def test_reception_get_outside_assigned_clinic_returns_404(self) -> None:
        intake = _create_intake_form(
            created_by=self.admin, clinic_site=self.clinic_other
        )
        self.client.login(username="ctx-rec", password=_PW)
        resp = self.client.get(
            f"/api/v1/intake-forms/{intake.id}?form_locale=de-DE",
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


# ---------------------------------------------------------------
# intake_form_telederm_view  PUT .../telederm-payload
# ---------------------------------------------------------------


@override_settings(RATELIMIT_ENABLE=False)
class IntakeFormTeledermViewTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.rec_user = StaffUser.objects.create_user(
            username="td-rec",
            email="td-rec@ex.com",
            password=_PW,
            is_staff=True,
        )
        assign_group_to_test_user(self.rec_user, "Reception")
        self.doc_user = StaffUser.objects.create_user(
            username="td-doc",
            email="td-doc@ex.com",
            password=_PW,
            is_staff=True,
        )
        assign_group_to_test_user(self.doc_user, "Doctor")
        self.intake_form = _create_intake_form(
            created_by=self.rec_user,
            process_type=PROCESS_TYPE_TELEDERM,
        )

    def _url(self, form_id=None, *, locale: str = "de-DE") -> str:
        fid = form_id or self.intake_form.id
        return f"/api/v1/intake-forms/{fid}/telederm-payload?form_locale={locale}"

    def test_doctor_returns_403(self) -> None:
        self.client.login(username="td-doc", password=_PW)
        resp = self.client.put(
            self._url(),
            data=json.dumps({"schema_version": 1, "answers": {}}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_invalid_json_returns_400(self) -> None:
        self.client.login(username="td-rec", password=_PW)
        resp = self.client.put(
            self._url(),
            data="BAD_JSON{",
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_pydantic_validation_returns_400(self) -> None:
        self.client.login(username="td-rec", password=_PW)
        resp = self.client.put(
            self._url(),
            data=json.dumps({"schema_version": 0, "answers": {}}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["error_key"], "other.api.invalid_request_body")

    @patch("apps.intake.api_views.read_json_body")
    def test_invalid_body_encoding_returns_domain_error(
        self, mock_read: MagicMock
    ) -> None:
        mock_read.side_effect = InvalidRequestBodyEncoding(
            "bad utf-8",
            api_message_key="other.api.request_body_too_large",
            api_message_params={"max_bytes": 42},
            http_status=413,
        )
        self.client.login(username="td-rec", password=_PW)
        resp = self.client.put(
            self._url(),
            data=json.dumps({"schema_version": 1, "answers": {}}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 413)

    def test_invalid_locale_returns_400(self) -> None:
        self.client.login(username="td-rec", password=_PW)
        resp = self.client.put(
            self._url(locale="!!!"),
            data=json.dumps({"schema_version": 1, "answers": {}}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_nonexistent_form_returns_404(self) -> None:
        self.client.login(username="td-rec", password=_PW)
        resp = self.client.put(
            self._url(uuid4()),
            data=json.dumps(
                {
                    "schema_version": 1,
                    "answers": {"T001": {"selected": ["NONE"]}},
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 404)

    @patch("apps.telederm.services.save_telederm_payload")
    def test_state_transition_returns_409(self, mock_save: MagicMock) -> None:
        mock_save.side_effect = StateTransitionError(
            domain_message("other.domain.intake_telederm_in_progress_only"),
            api_message_key="other.domain.intake_telederm_in_progress_only",
        )
        self.client.login(username="td-rec", password=_PW)
        resp = self.client.put(
            self._url(),
            data=json.dumps({"schema_version": 1, "answers": {}}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 409)

    @patch("apps.telederm.services.save_telederm_payload")
    def test_domain_error_returns_409(self, mock_save: MagicMock) -> None:
        mock_save.side_effect = DomainError(
            domain_message("other.domain.not_telederm_intake"),
            api_message_key="other.domain.not_telederm_intake",
        )
        self.client.login(username="td-rec", password=_PW)
        resp = self.client.put(
            self._url(),
            data=json.dumps({"schema_version": 1, "answers": {}}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 409)

    def test_happy_path_persists_answers(self) -> None:
        self.client.login(username="td-rec", password=_PW)
        resp = self.client.put(
            self._url(),
            data=json.dumps(
                {
                    "schema_version": 1,
                    "answers": {
                        "T001": {"selected": ["NONE"]},
                        "CC001": {"selected": ["NEW_SKIN_LESION"]},
                    },
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.intake_form.refresh_from_db()
        self.assertEqual(self.intake_form.telederm_schema_version, 1)
        self.assertEqual(
            self.intake_form.telederm_payload["chief_complaint_path"], "CCE-001"
        )
        self.assertIn("telederm", resp.json())
