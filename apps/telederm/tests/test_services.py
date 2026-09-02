"""Integration tests for telederm payload services."""

from __future__ import annotations

import hashlib
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from apps.core.api_utils import assign_group_to_test_user
from apps.intake.models import IntakeStatus, PatientIntakeForm
from apps.reception.models import (
    ClinicSite,
    ConsultingRoom,
    DailyQueue,
    Patient,
    PatientFormSession,
    QueueStatus,
)
from apps.reception.process_types import PROCESS_TYPE_TELEDERM
from apps.reception.services import create_queue_entry
from apps.telederm.services import (
    RequiredTeledermMissingError,
    finalize_telederm_payload_on_submit,
    save_telederm_payload,
)
from apps.telederm.tests.smoke_answers import SMOKE_TELEDERM_ANSWERS


class TeledermServicesTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        from apps.users.models import StaffUser

        cls.user = StaffUser.objects.create_user(
            username="telederm_svc",
            email="telederm.svc@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(cls.user, "Reception")
        clinic = ClinicSite.objects.create(code="TD", name="Telederm Clinic")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="TD1", name="TD1")
        cls.queue = DailyQueue.objects.create(
            queue_date=timezone.localdate(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            created_by_user=cls.user,
        )
        cls.patient = Patient.objects.create(
            first_name="Tel",
            last_name="Derm",
            phone="+48111222333",
            date_of_birth=date(1980, 1, 1),
            email="tel.derm@example.com",
        )

    def _intake_form(self) -> PatientIntakeForm:
        entry = create_queue_entry(
            daily_queue_id=self.queue.id,
            patient_id=self.patient.id,
            created_by_user_id=self.user.id,
            process_type=PROCESS_TYPE_TELEDERM,
        )
        session = PatientFormSession.objects.create(
            queue_entry=entry,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(minutes=30),
            created_by_user=self.user,
        )
        entry.active_session = session
        entry.save(update_fields=["active_session", "updated_at"])
        signature_dir = Path(settings.MEDIA_ROOT) / "signatures" / "tests"
        signature_dir.mkdir(parents=True, exist_ok=True)
        signature_path = signature_dir / f"{entry.id}.png"
        signature_bytes = b"\x89PNG\r\n\x1a\n" + b"telederm-svc"
        signature_path.write_bytes(signature_bytes)
        return PatientIntakeForm.objects.create(
            queue_entry=entry,
            session=session,
            form_status=IntakeStatus.IN_PROGRESS,
            signature_file_path=str(signature_path),
            signature_sha256=hashlib.sha256(signature_bytes).hexdigest(),
        )

    def test_new_form_telederm_payload_includes_schema_version(self) -> None:
        intake = self._intake_form()
        self.assertEqual(intake.telederm_schema_version, 1)
        self.assertEqual(intake.telederm_payload, {"schema_version": 1})

    def test_save_opens_business_span(self) -> None:
        intake = self._intake_form()
        with patch("apps.telederm.services.cogito_business_span") as mock_span:
            save_telederm_payload(
                intake_form_id=intake.id,
                payload={"answers": {"T001": {"selected": ["NONE"]}}},
                form_locale="de-DE",
            )
        mock_span.assert_called_once()
        self.assertEqual(mock_span.call_args.args[0], "telederm.save_telederm_payload")
        self.assertEqual(
            mock_span.call_args.kwargs["queue_entry_id"], intake.queue_entry_id
        )
        self.assertEqual(
            mock_span.call_args.kwargs["extra_attributes"]["cogito.intake_form_id"],
            str(intake.id),
        )
        self.assertEqual(
            mock_span.call_args.kwargs["extra_attributes"][
                "cogito.telederm_schema_version"
            ],
            1,
        )

    def test_backfill_adds_schema_version_without_dropping_answers(self) -> None:
        import importlib

        from django.apps import apps as django_apps

        backfill = importlib.import_module(
            "apps.intake.migrations.0032_telederm_payload_schema_version"
        ).backfill_telederm_json_schema_version

        intake = self._intake_form()
        PatientIntakeForm.objects.filter(id=intake.id).update(
            telederm_schema_version=0,
            telederm_payload={"answers": {"T001": {"selected": ["NONE"]}}},
        )
        backfill(django_apps, None)
        intake.refresh_from_db()
        self.assertEqual(intake.telederm_schema_version, 1)
        self.assertEqual(intake.telederm_payload["schema_version"], 1)
        self.assertEqual(
            intake.telederm_payload["answers"]["T001"]["selected"], ["NONE"]
        )

    def test_finalize_rejects_incomplete_payload(self) -> None:
        intake = self._intake_form()
        with self.assertRaises(RequiredTeledermMissingError):
            finalize_telederm_payload_on_submit(intake, form_locale="de-DE")

    def test_save_and_finalize_smoke_answers(self) -> None:
        intake = self._intake_form()
        save_telederm_payload(
            intake_form_id=intake.id,
            payload=SMOKE_TELEDERM_ANSWERS,
            form_locale="de-DE",
        )
        intake.refresh_from_db()
        finalized = finalize_telederm_payload_on_submit(intake, form_locale="de-DE")
        self.assertFalse(finalized.get("triage_blocked"))
        self.assertIn("clinical_summary", finalized)
        self.assertEqual(finalized["chief_complaint_path"], "CCE-001")

    def test_save_derives_path_from_cc001_not_stale_field(self) -> None:
        intake = self._intake_form()
        saved = save_telederm_payload(
            intake_form_id=intake.id,
            payload={
                "chief_complaint_path": "CCE-002",
                "answers": {
                    "T001": {"selected": ["NONE"]},
                    "CC001": {"selected": ["NEW_SKIN_LESION"]},
                },
            },
            form_locale="de-DE",
        )
        self.assertEqual(saved.telederm_payload["chief_complaint_path"], "CCE-001")

    def test_serialize_uses_pl_and_en_labels(self) -> None:
        from apps.telederm.services import load_catalog, serialize_catalog_for_tablet

        catalog = load_catalog()
        payload = {
            "answers": {
                "T001": {"selected": ["NONE"]},
                "CC001": {"selected": ["NEW_SKIN_LESION"]},
            }
        }
        pl = serialize_catalog_for_tablet(
            catalog=catalog, payload=payload, locale="pl-PL"
        )
        en = serialize_catalog_for_tablet(
            catalog=catalog, payload=payload, locale="en-US"
        )
        self.assertTrue(pl["questions"])
        self.assertTrue(en["questions"])
        self.assertEqual(pl["chief_complaint_path"], "CCE-001")

    def test_normalize_rejects_non_dict_answers(self) -> None:
        from apps.telederm.services import load_catalog, normalize_telederm_payload

        catalog = load_catalog()
        normalized = normalize_telederm_payload(
            payload={"answers": "bad", "chief_complaint_path": None},
            catalog=catalog,
            locale="de-DE",
        )
        self.assertEqual(normalized["answers"], {})

    def test_normalize_skips_non_dict_answer_rows(self) -> None:
        from apps.telederm.services import load_catalog, normalize_telederm_payload

        catalog = load_catalog()
        normalized = normalize_telederm_payload(
            payload={
                "answers": {
                    "T001": "nope",
                    "CC001": {"selected": "NEW_SKIN_LESION"},
                }
            },
            catalog=catalog,
            locale="de-DE",
        )
        self.assertNotIn("T001", normalized["answers"])
        self.assertEqual(
            normalized["answers"]["CC001"]["selected"], ["NEW_SKIN_LESION"]
        )

    def test_validate_rejects_triage_blocked(self) -> None:
        from apps.telederm.services import (
            RequiredTeledermMissingError,
            load_catalog,
            validate_telederm_for_submit,
        )

        catalog = load_catalog()
        with self.assertRaises(RequiredTeledermMissingError):
            validate_telederm_for_submit(
                catalog=catalog,
                payload={"answers": {"T001": {"selected": ["SEVERE_PAIN"]}}},
            )

    def test_assert_rejects_standard_process(self) -> None:
        from apps.core.exceptions import DomainError
        from apps.reception.process_types import PROCESS_TYPE_STANDARD
        from apps.telederm.services import assert_telederm_intake_form

        entry = create_queue_entry(
            daily_queue_id=self.queue.id,
            patient_id=self.patient.id,
            created_by_user_id=self.user.id,
            process_type=PROCESS_TYPE_STANDARD,
        )
        session = PatientFormSession.objects.create(
            queue_entry=entry,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(minutes=30),
            created_by_user=self.user,
        )
        intake = PatientIntakeForm.objects.create(
            queue_entry=entry,
            session=session,
            form_status=IntakeStatus.IN_PROGRESS,
        )
        with self.assertRaises(DomainError):
            assert_telederm_intake_form(intake)

    def test_save_rejects_submitted_form(self) -> None:
        from apps.core.exceptions import StateTransitionError

        intake = self._intake_form()
        intake.form_status = IntakeStatus.SUBMITTED
        intake.submitted_at = timezone.now()
        intake.save(update_fields=["form_status", "submitted_at", "updated_at"])
        with self.assertRaises(StateTransitionError):
            save_telederm_payload(
                intake_form_id=intake.id,
                payload={"answers": {"T001": {"selected": ["NONE"]}}},
                form_locale="de-DE",
            )


class TestSaveTeledermPayloadAutocommit(TransactionTestCase):
    """TestCase wraps each method in atomic and hides FOR UPDATE outside a transaction."""

    def test_save_succeeds_without_outer_atomic(self) -> None:
        from apps.users.models import StaffUser

        user = StaffUser.objects.create_user(
            username="telederm_autocommit",
            email="telederm.autocommit@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(user, "Reception")
        clinic = ClinicSite.objects.create(code="TDA", name="Telederm Autocommit")
        room = ConsultingRoom.objects.create(
            clinic_site=clinic, code="TDA1", name="TDA1"
        )
        queue = DailyQueue.objects.create(
            queue_date=timezone.localdate(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            created_by_user=user,
        )
        patient = Patient.objects.create(
            first_name="Auto",
            last_name="Commit",
            phone="+48111222444",
            date_of_birth=date(1981, 2, 2),
            email="tel.autocommit@example.com",
        )
        entry = create_queue_entry(
            daily_queue_id=queue.id,
            patient_id=patient.id,
            created_by_user_id=user.id,
            process_type=PROCESS_TYPE_TELEDERM,
        )
        session = PatientFormSession.objects.create(
            queue_entry=entry,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(minutes=30),
            created_by_user=user,
        )
        signature_dir = Path(settings.MEDIA_ROOT) / "signatures" / "tests"
        signature_dir.mkdir(parents=True, exist_ok=True)
        signature_path = signature_dir / f"{entry.id}.png"
        signature_bytes = b"\x89PNG\r\n\x1a\n" + b"telederm-ac"
        signature_path.write_bytes(signature_bytes)
        intake = PatientIntakeForm.objects.create(
            queue_entry=entry,
            session=session,
            form_status=IntakeStatus.IN_PROGRESS,
            signature_file_path=str(signature_path),
            signature_sha256=hashlib.sha256(signature_bytes).hexdigest(),
        )
        saved = save_telederm_payload(
            intake_form_id=intake.id,
            payload={"answers": {"T001": {"selected": ["NONE"]}}},
            form_locale="de-DE",
        )
        saved.refresh_from_db()
        self.assertEqual(saved.telederm_schema_version, 1)
        self.assertIn("T001", saved.telederm_payload["answers"])
