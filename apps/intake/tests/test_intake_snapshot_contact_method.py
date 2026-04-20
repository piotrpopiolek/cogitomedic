"""Intake PDF snapshot: Präventions Kontaktweg (no WeasyPrint import chain)."""

from __future__ import annotations

import hashlib
from typing import cast
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

from django.conf import settings
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.intake.models import (
    ConsentDefinition,
    IntakeStatus,
    PatientIntakeConsent,
    PatientIntakeForm,
)
from apps.intake.services import (
    CONTACT_METHOD_CONSENT_CODE,
    NEW_SKIN_CHANGES_AFFIRMATIVE_CODES,
    NEW_SKIN_CHANGES_LOCATION,
    _anamnesis_selected_affirmative,
    _build_intake_snapshot_payload,
)
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


class IntakeSnapshotPreventionContactTests(TestCase):
    def setUp(self) -> None:
        user = StaffUser.objects.create_user(
            username="snap-intake-contact",
            email="snap.contact@example.com",
            password="safe-password",
            is_staff=True,
        )
        clinic = ClinicSite.objects.create(code="SNP", name="Snapshot clinic")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="R1", name="R1")
        daily_queue = DailyQueue.objects.create(
            queue_date=timezone.localdate(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            created_by_user=user,
        )
        patient = Patient.objects.create(
            first_name="Snap",
            last_name="Patient",
            date_of_birth=date(1991, 3, 3),
            phone="+48111222333",
        )
        self.queue_entry = QueueEntry.objects.create(
            daily_queue=daily_queue,
            patient=patient,
            entry_status=QueueEntryStatus.IN_PROGRESS,
            position_no=1,
            created_by_user=user,
        )
        self.session = PatientFormSession.objects.create(
            queue_entry=self.queue_entry,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(minutes=30),
            created_by_user=user,
        )
        signature_dir = Path(settings.MEDIA_ROOT) / "signatures" / "tests"
        signature_dir.mkdir(parents=True, exist_ok=True)
        signature_path = signature_dir / f"{self.queue_entry.id}.png"
        signature_bytes = b"\x89PNG\r\n\x1a\n" + b"valid-test-signature"
        signature_path.write_bytes(signature_bytes)
        self.intake_form = PatientIntakeForm.objects.create(
            queue_entry=self.queue_entry,
            session=self.session,
            form_status=IntakeStatus.IN_PROGRESS,
            anamnesis_payload={"answers": []},
            signature_file_path=str(signature_path),
            signature_sha256=hashlib.sha256(signature_bytes).hexdigest(),
        )

    def test_build_snapshot_includes_contact_method_selection(self) -> None:
        definition = (
            ConsentDefinition.objects.filter(
                code=CONTACT_METHOD_CONSENT_CODE, is_active=True
            )
            .order_by("-version")
            .first()
        )
        if definition is None:
            self.skipTest("Contact method consent definition not seeded")
        PatientIntakeConsent.objects.create(
            intake_form=self.intake_form,
            consent_definition=definition,
            accepted=True,
            accepted_at=timezone.now(),
            selected_option_codes=["email", "PHONE"],
        )
        payload = _build_intake_snapshot_payload(
            intake_form=self.intake_form, now=timezone.now()
        )
        row = next(
            (
                c
                for c in payload["consents"]
                if c["code"] == CONTACT_METHOD_CONSENT_CODE
            ),
            None,
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["selected_option_codes"], ["EMAIL", "PHONE"])
        opts = row.get("contact_method_all_options") or []
        self.assertEqual(len(opts), 3)
        by_code = {o["option_code"]: o for o in opts}
        self.assertTrue(by_code["EMAIL"]["selected"])
        self.assertFalse(by_code["SMS"]["selected"])
        self.assertTrue(by_code["PHONE"]["selected"])

    def test_snapshot_includes_body_map_when_q4_new_skin_changes_yes(self) -> None:
        self.intake_form.anamnesis_payload = {
            "answers": [
                {
                    "question_code": NEW_SKIN_CHANGES_LOCATION,
                    "selected_option_codes": ["YES"],
                },
            ],
        }
        self.intake_form.body_map_data = [
            {"x": 0.22, "y": 0.35, "side": "front"},
        ]
        self.intake_form.save(
            update_fields=["anamnesis_payload", "body_map_data", "updated_at"]
        )
        payload = _build_intake_snapshot_payload(
            intake_form=self.intake_form, now=timezone.now()
        )
        bm = payload.get("body_map")
        self.assertIsNotNone(bm)
        assert isinstance(bm, dict)
        self.assertEqual(bm.get("image_rel_path"), "static/tablet/body.jpg")
        self.assertEqual(len(bm.get("points") or []), 1)
        pt = bm["points"][0]
        self.assertEqual(pt["left_pct"], "22.0000")
        self.assertEqual(pt["top_pct"], "35.0000")
        self.assertEqual(pt["side"], "front")
        answers = (payload.get("anamnesis") or {}).get("answers") or []
        self.assertTrue(answers)
        skin_row = next(
            (a for a in answers if a.get("question_code") == NEW_SKIN_CHANGES_LOCATION),
            None,
        )
        self.assertIsNotNone(skin_row)
        assert skin_row is not None
        self.assertEqual(skin_row.get("body_map"), bm)

    def test_snapshot_includes_body_map_when_question_code_has_whitespace(self) -> None:
        """Strip question_code like _build_intake_snapshot_payload so PDF body map is not dropped."""
        self.intake_form.anamnesis_payload = {
            "answers": [
                {
                    "question_code": f"  {NEW_SKIN_CHANGES_LOCATION}  ",
                    "selected_option_codes": ["YES"],
                },
            ],
        }
        self.intake_form.body_map_data = [
            {"x": 0.22, "y": 0.35, "side": "front"},
        ]
        self.intake_form.save(
            update_fields=["anamnesis_payload", "body_map_data", "updated_at"]
        )
        payload = _build_intake_snapshot_payload(
            intake_form=self.intake_form, now=timezone.now()
        )
        self.assertIsNotNone(payload.get("body_map"))
        answers = (payload.get("anamnesis") or {}).get("answers") or []
        skin_row = next(
            (a for a in answers if a.get("question_code") == NEW_SKIN_CHANGES_LOCATION),
            None,
        )
        self.assertIsNotNone(skin_row)
        assert skin_row is not None
        self.assertIsNotNone(skin_row.get("body_map"))

    def test_snapshot_omits_body_map_when_q4_no(self) -> None:
        self.intake_form.anamnesis_payload = {
            "answers": [
                {
                    "question_code": NEW_SKIN_CHANGES_LOCATION,
                    "selected_option_codes": ["NO"],
                },
            ],
        }
        self.intake_form.body_map_data = [
            {"x": 0.1, "y": 0.2, "side": "back"},
        ]
        self.intake_form.save(
            update_fields=["anamnesis_payload", "body_map_data", "updated_at"]
        )
        payload = _build_intake_snapshot_payload(
            intake_form=self.intake_form, now=timezone.now()
        )
        self.assertIsNone(payload.get("body_map"))


class AnamnesisSelectedAffirmativeStripTests(SimpleTestCase):
    """No DB: _anamnesis_selected_affirmative must strip question_code like the snapshot builder."""

    def test_true_when_stored_question_code_has_surrounding_whitespace(self) -> None:
        form = SimpleNamespace(
            anamnesis_payload={
                "answers": [
                    {
                        "question_code": f"  {NEW_SKIN_CHANGES_LOCATION}  ",
                        "selected_option_codes": ["YES"],
                    },
                ],
            },
        )
        self.assertTrue(
            _anamnesis_selected_affirmative(
                cast(PatientIntakeForm, form),
                question_code=NEW_SKIN_CHANGES_LOCATION,
                affirmative=NEW_SKIN_CHANGES_AFFIRMATIVE_CODES,
            )
        )
