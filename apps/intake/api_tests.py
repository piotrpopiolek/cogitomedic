from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.test import Client, TestCase
from django.utils import timezone

from apps.intake.models import (
    AnamnesisQuestionDefinition,
    ConsentDefinition,
    IntakeDocumentVersion,
    IntakeOutboxEvent,
    IntakeOutboxEventType,
    IntakeStatus,
    PatientIntakeConsent,
    PatientIntakeForm,
)
from apps.intake.services import _effective_consent_filter, _effective_question_filter
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
from apps.users.models import StaffRole, StaffUser


class IntakeApiTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.reception_user = StaffUser.objects.create_user(
            username="api-reception",
            email="api.reception@example.com",
            password="safe-password",
            role=StaffRole.RECEPTION,
            is_staff=True,
        )
        clinic = ClinicSite.objects.create(code="API", name="API Clinic")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="A1", name="A1")
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            created_by_user=self.reception_user,
        )
        patient = Patient.objects.create(
            first_name="Api",
            last_name="Patient",
            date_of_birth=date(1990, 1, 1),
            phone="+48123456789",
            email="api.patient@example.com",
            doctolib_patient_id="DOC-API-1",
        )
        self.queue_entry = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.IN_PROGRESS,
            position_no=1,
            created_by_user=self.reception_user,
        )
        self.session = PatientFormSession.objects.create(
            queue_entry=self.queue_entry,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(minutes=30),
            created_by_user=self.reception_user,
        )
        self.queue_entry.active_session = self.session
        self.queue_entry.save(update_fields=["active_session", "updated_at"])
        signature_dir = Path(settings.MEDIA_ROOT) / "signatures" / "tests"
        signature_dir.mkdir(parents=True, exist_ok=True)
        signature_path = signature_dir / f"{self.queue_entry.id}.png"
        signature_bytes = b"fake-png-signature-api"
        signature_path.write_bytes(signature_bytes)
        self.intake_form = PatientIntakeForm.objects.create(
            queue_entry=self.queue_entry,
            session=self.session,
            form_status=IntakeStatus.IN_PROGRESS,
            signature_file_path=str(signature_path),
            signature_sha256=hashlib.sha256(signature_bytes).hexdigest(),
            anamnesis_payload={"schema_version": 1, "answers": []},
        )

        self.required_consent = ConsentDefinition.objects.create(
            code="CONSENT_REQUIRED",
            version=1,
            title_de="Einwilligung",
            title_en="Consent",
            content_de="Treść",
            content_en="Content",
            is_required=True,
            is_active=True,
        )
        AnamnesisQuestionDefinition.objects.create(
            code="Q1_REQUIRED",
            version=1,
            question_text_de="Frage",
            question_text_en="Question",
            is_required=True,
            is_active=True,
        )
        self.client.force_login(self.reception_user)

    def _accept_all_required_consents_effective_today(self, intake_form: PatientIntakeForm) -> None:
        today = timezone.now().date()
        for cdef in ConsentDefinition.objects.filter(
            _effective_consent_filter(today), is_required=True
        ):
            PatientIntakeConsent.objects.get_or_create(
                intake_form=intake_form,
                consent_definition=cdef,
                defaults={"accepted": True, "accepted_at": timezone.now()},
            )

    def _build_answers_for_all_required_questions_today(self) -> list[dict]:
        today = timezone.now().date()
        required = AnamnesisQuestionDefinition.objects.filter(
            _effective_question_filter(today), is_required=True
        ).prefetch_related("options")
        answers = []
        for q in required:
            first_option = next(iter(q.options.order_by("display_order")), None)
            if first_option:
                answers.append({
                    "question_code": q.code,
                    "selected_option_codes": [first_option.code],
                    "free_text": None,
                })
            else:
                answers.append({
                    "question_code": q.code,
                    "selected_option_codes": [],
                    "free_text": "–",
                })
        return answers

    def test_create_queue_entry_session_endpoint(self) -> None:
        response = self.client.post(
            f"/api/v1/queue-entries/{self.queue_entry.id}/sessions",
            data=json.dumps(
                {
                    "form_locale": "en-GB",
                    "expires_in_minutes": 10,
                }
            ),
            content_type="application/json",
        )
        payload = response.json()
        self.assertEqual(response.status_code, 201)
        self.assertIn("session_id", payload)
        self.assertIn("intake_form_id", payload)
        intake_form = PatientIntakeForm.objects.get(id=payload["intake_form_id"])
        self.assertEqual(str(intake_form.session_id), payload["session_id"])
        self.assertEqual(intake_form.queue_entry_id, self.queue_entry.id)

    def test_create_queue_entry_session_returns_404_for_missing_queue_entry(self) -> None:
        response = self.client.post(
            f"/api/v1/queue-entries/{uuid4()}/sessions",
            data=json.dumps(
                {
                    "form_locale": "en-GB",
                    "expires_in_minutes": 10,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)

    def test_update_anamnesis_validation_error_without_schema_version(self) -> None:
        response = self.client.put(
            f"/api/v1/intake-forms/{self.intake_form.id}/anamnesis",
            data=json.dumps({"answers": []}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_update_anamnesis_success(self) -> None:
        response = self.client.put(
            f"/api/v1/intake-forms/{self.intake_form.id}/anamnesis",
            data=json.dumps(
                {
                    "anamnesis_schema_version": 1,
                    "answers": [{"question_code": "Q1_REQUIRED", "selected_option_codes": ["YES"]}],
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.intake_form.refresh_from_db()
        self.assertEqual(self.intake_form.anamnesis_schema_version, 1)
        self.assertEqual(self.intake_form.anamnesis_payload.get("schema_version"), 1)

    def test_submit_intake_success(self) -> None:
        self._accept_all_required_consents_effective_today(self.intake_form)
        self.intake_form.anamnesis_payload = {
            "schema_version": 1,
            "answers": self._build_answers_for_all_required_questions_today(),
        }
        self.intake_form.save(update_fields=["anamnesis_payload", "updated_at"])

        response = self.client.post(
            f"/api/v1/intake-forms/{self.intake_form.id}/submit",
            data=json.dumps({"submitted_by_user_id": str(self.reception_user.id)}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.intake_form.refresh_from_db()
        self.queue_entry.refresh_from_db()
        self.assertEqual(self.intake_form.form_status, IntakeStatus.SUBMITTED)
        self.assertEqual(self.queue_entry.entry_status, QueueEntryStatus.PATIENT_COMPLETED)
        self.assertEqual(IntakeDocumentVersion.objects.filter(intake_form=self.intake_form).count(), 1)
        version = IntakeDocumentVersion.objects.get(intake_form=self.intake_form)
        self.assertIn("signature", version.snapshot_payload)
        self.assertTrue(
            IntakeOutboxEvent.objects.filter(
                intake_document_version=version,
                event_type=IntakeOutboxEventType.GENERATE_INTAKE_PDF,
            ).exists()
        )

    def test_submit_intake_is_idempotent(self) -> None:
        self._accept_all_required_consents_effective_today(self.intake_form)
        self.intake_form.anamnesis_payload = {
            "schema_version": 1,
            "answers": self._build_answers_for_all_required_questions_today(),
        }
        self.intake_form.save(update_fields=["anamnesis_payload", "updated_at"])

        first = self.client.post(
            f"/api/v1/intake-forms/{self.intake_form.id}/submit",
            data=json.dumps({}),
            content_type="application/json",
        )
        second = self.client.post(
            f"/api/v1/intake-forms/{self.intake_form.id}/submit",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(IntakeDocumentVersion.objects.filter(intake_form=self.intake_form).count(), 1)

    def test_submit_returns_400_when_signature_missing(self) -> None:
        self.intake_form.signature_file_path = None
        self.intake_form.signature_sha256 = None
        self.intake_form.save(update_fields=["signature_file_path", "signature_sha256"])
        self._accept_all_required_consents_effective_today(self.intake_form)
        self.intake_form.anamnesis_payload = {
            "schema_version": 1,
            "answers": self._build_answers_for_all_required_questions_today(),
        }
        self.intake_form.save(update_fields=["anamnesis_payload", "updated_at"])

        response = self.client.post(
            f"/api/v1/intake-forms/{self.intake_form.id}/submit",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Signature", response.json().get("error", ""))

    def test_e2e_waiting_room_issue_session_then_anamnesis_and_submit(self) -> None:
        """E2E: queue → entry → POST sessions (get intake_form_id) → anamnesis → submit."""
        response = self.client.post(
            f"/api/v1/queue-entries/{self.queue_entry.id}/sessions",
            data=json.dumps(
                {
                    "form_locale": "de-DE",
                    "expires_in_minutes": 20,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        payload = response.json()
        intake_form_id = payload["intake_form_id"]
        e2e_intake_form = PatientIntakeForm.objects.get(id=intake_form_id)

        self._accept_all_required_consents_effective_today(e2e_intake_form)
        e2e_signature = Path(settings.MEDIA_ROOT) / "signatures" / "tests" / f"{intake_form_id}-e2e.png"
        e2e_bytes = b"fake-png-signature-e2e"
        e2e_signature.write_bytes(e2e_bytes)
        PatientIntakeForm.objects.filter(id=intake_form_id).update(
            signature_file_path=str(e2e_signature),
            signature_sha256=hashlib.sha256(e2e_bytes).hexdigest(),
        )

        anamnesis_response = self.client.put(
            f"/api/v1/intake-forms/{intake_form_id}/anamnesis",
            data=json.dumps(
                {
                    "anamnesis_schema_version": 1,
                    "answers": self._build_answers_for_all_required_questions_today(),
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(anamnesis_response.status_code, 200)

        submit_response = self.client.post(
            f"/api/v1/intake-forms/{intake_form_id}/submit",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(submit_response.status_code, 200)
        self.queue_entry.refresh_from_db()
        self.assertEqual(self.queue_entry.entry_status, QueueEntryStatus.PATIENT_COMPLETED)
        form = PatientIntakeForm.objects.get(id=intake_form_id)
        self.assertEqual(form.form_status, IntakeStatus.SUBMITTED)

    def test_intake_endpoints_return_404_for_missing_intake_form(self) -> None:
        missing_intake_id = uuid4()
        anamnesis_response = self.client.put(
            f"/api/v1/intake-forms/{missing_intake_id}/anamnesis",
            data=json.dumps(
                {
                    "anamnesis_schema_version": 1,
                    "answers": [],
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(anamnesis_response.status_code, 404)

        submit_response = self.client.post(
            f"/api/v1/intake-forms/{missing_intake_id}/submit",
            data=json.dumps({"submitted_by_user_id": str(self.reception_user.id)}),
            content_type="application/json",
        )
        self.assertEqual(submit_response.status_code, 404)

    def test_get_intake_form_context_returns_patient_and_consents(self) -> None:
        response = self.client.get(f"/api/v1/intake-forms/{self.intake_form.id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["intake_form_id"], str(self.intake_form.id))
        self.assertEqual(data["queue_entry_id"], str(self.queue_entry.id))
        self.assertEqual(data["form_status"], "IN_PROGRESS")
        self.assertIn("patient", data)
        self.assertEqual(data["patient"]["first_name"], "Api")
        self.assertIn("consents", data)
        self.assertIn("anamnesis_questions", data)
        self.assertIn("has_signature", data)
        self.assertTrue(data["has_signature"])

    def test_put_consents_updates_acceptance(self) -> None:
        response = self.client.put(
            f"/api/v1/intake-forms/{self.intake_form.id}/consents",
            data=json.dumps({
                "consents": [
                    {"consent_definition_id": str(self.required_consent.id), "accepted": True},
                ],
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["consents"]), 1)
        self.assertTrue(data["consents"][0]["accepted"])
        self.assertIsNotNone(data["consents"][0]["accepted_at"])

    def test_post_signature_saves_and_returns_path(self) -> None:
        self.intake_form.signature_file_path = None
        self.intake_form.signature_sha256 = None
        self.intake_form.save(update_fields=["signature_file_path", "signature_sha256"])
        # Minimal PNG 1x1 base64
        tiny_png_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        response = self.client.post(
            f"/api/v1/intake-forms/{self.intake_form.id}/signature",
            data=json.dumps({"signature_base64": f"data:image/png;base64,{tiny_png_b64}"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("signatures/", data["signature_file_path"])
        self.assertEqual(len(data["signature_sha256"]), 64)
        self.intake_form.refresh_from_db()
        self.assertIsNotNone(self.intake_form.signature_file_path)
        self.assertIsNotNone(self.intake_form.signature_sha256)
