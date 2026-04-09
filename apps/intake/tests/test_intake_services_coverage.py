"""Tests covering uncovered lines in apps.intake.services."""

from __future__ import annotations

import base64
import tempfile
import uuid
from datetime import date, timedelta

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from freezegun import freeze_time

from apps.core.exceptions import DomainError, StateTransitionError
from apps.intake.models import (
    ConsentDefinition,
    IntakeStatus,
    PatientIntakeConsent,
    PatientIntakeForm,
)
from apps.intake.services import (
    CONTACT_METHOD_CONSENT_CODE,
    ConsentNotActiveError,
    IntakeSessionValidationError,
    InvalidSignatureError,
    _extract_answered_question_codes,
    _humanize_code,
    _localized_text,
    save_intake_anamnesis_payload,
    save_intake_body_map,
    save_intake_consents,
    save_intake_signature,
    submit_patient_intake_form,
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

# ---------------------------------------------------------
# 1. Pure-function tests (no DB needed)
# ---------------------------------------------------------


class HumanizeCodeTests(SimpleTestCase):
    def test_custom_code_titlecased_with_spaces(self):
        self.assertEqual(
            _humanize_code("SOME_CUSTOM_CODE"),
            "Some Custom Code",
        )

    def test_single_word_custom_code(self):
        self.assertEqual(_humanize_code("HELLO"), "Hello")


class LocalizedTextTests(SimpleTestCase):
    def test_pl_locale_returns_value_pl(self):
        result = _localized_text(
            value_de="DE",
            value_en="EN",
            value_pl="PL",
            locale="pl-PL",
        )
        self.assertEqual(result, "PL")

    def test_pl_locale_falls_back_to_de(self):
        result = _localized_text(
            value_de="DE",
            value_en="EN",
            value_pl="",
            locale="pl-PL",
        )
        self.assertEqual(result, "DE")

    def test_en_locale_returns_value_en(self):
        result = _localized_text(
            value_de="DE",
            value_en="EN",
            value_pl="PL",
            locale="en-US",
        )
        self.assertEqual(result, "EN")

    def test_en_locale_falls_back_to_de(self):
        result = _localized_text(
            value_de="DE",
            value_en="",
            value_pl="PL",
            locale="en-US",
        )
        self.assertEqual(result, "DE")


class ExtractAnsweredQuestionCodesTests(SimpleTestCase):
    def test_answers_not_a_list_returns_empty(self):
        result = _extract_answered_question_codes(
            {"answers": "not-a-list"},
        )
        self.assertEqual(result, set())

    def test_non_dict_entry_skipped(self):
        result = _extract_answered_question_codes(
            {"answers": ["string-entry"]},
        )
        self.assertEqual(result, set())

    def test_invalid_question_code_type_skipped(self):
        result = _extract_answered_question_codes(
            {"answers": [{"question_code": 42}]},
        )
        self.assertEqual(result, set())

    def test_empty_question_code_skipped(self):
        result = _extract_answered_question_codes(
            {"answers": [{"question_code": ""}]},
        )
        self.assertEqual(result, set())

    def test_no_options_no_text_not_answered(self):
        payload = {
            "answers": [
                {
                    "question_code": "Q1",
                    "selected_option_codes": [],
                    "free_text": "",
                },
            ],
        }
        self.assertEqual(
            _extract_answered_question_codes(payload),
            set(),
        )

    def test_with_selected_options_answered(self):
        payload = {
            "answers": [
                {
                    "question_code": "Q1",
                    "selected_option_codes": ["YES"],
                },
            ],
        }
        self.assertEqual(
            _extract_answered_question_codes(payload),
            {"Q1"},
        )

    def test_with_free_text_answered(self):
        payload = {
            "answers": [
                {
                    "question_code": "Q2",
                    "free_text": "Some text",
                },
            ],
        }
        self.assertEqual(
            _extract_answered_question_codes(payload),
            {"Q2"},
        )


# ---------------------------------------------------------
# 2. Integration tests (require DB)
# ---------------------------------------------------------

VALID_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100


class IntakeServiceBaseTestCase(TestCase):
    """Shared DB fixtures for intake service coverage."""

    @classmethod
    def setUpTestData(cls):
        cls.actor = StaffUser.objects.create_user(
            username="cov-actor",
            email="cov-actor@example.com",
            password="x",
            is_staff=True,
        )
        cls.clinic = ClinicSite.objects.create(
            code="CV",
            name="Coverage Clinic",
        )
        cls.room = ConsultingRoom.objects.create(
            clinic_site=cls.clinic,
            code="C1",
            name="C1",
        )
        cls.patient = Patient.objects.create(
            first_name="Test",
            last_name="Cover",
            date_of_birth=date(1985, 5, 15),
            phone="+48500100200",
            email="cover@example.com",
        )

    def _make_form(
        self,
        *,
        form_status=IntakeStatus.IN_PROGRESS,
        **form_kw,
    ):
        dq = DailyQueue.objects.create(
            queue_date=date(2026, 3, 10),
            clinic_site=self.clinic,
            consulting_room=self.room,
            status=QueueStatus.OPEN,
            created_by_user=self.actor,
        )
        qe = QueueEntry.objects.create(
            daily_queue=dq,
            patient=self.patient,
            entry_status=QueueEntryStatus.IN_PROGRESS,
            position_no=1,
            created_by_user=self.actor,
        )
        sess = PatientFormSession.objects.create(
            queue_entry=qe,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=self.actor,
        )
        qe.active_session = sess
        qe.save(
            update_fields=["active_session", "updated_at"],
        )
        defaults = {
            "queue_entry": qe,
            "session": sess,
            "form_status": form_status,
        }
        if form_status == IntakeStatus.SUBMITTED:
            defaults.setdefault(
                "submitted_at",
                timezone.now(),
            )
            defaults.setdefault(
                "signature_sha256",
                "a" * 64,
            )
        defaults.update(form_kw)
        form = PatientIntakeForm.objects.create(**defaults)
        return form, qe, sess


# -- save_intake_body_map ----------------------------------


@freeze_time("2026-03-10T12:00:00Z")
class SaveIntakeBodyMapTests(IntakeServiceBaseTestCase):
    def test_happy_path_persists_body_map(self):
        form, _qe, _s = self._make_form()
        body_data = [
            {
                "x": 0.5,
                "y": 0.3,
                "side": "front",
                "label": "L",
            },
        ]
        result = save_intake_body_map(
            intake_form_id=form.id,
            body_map_schema_version=2,
            body_map_data=body_data,
        )
        result.refresh_from_db()
        self.assertEqual(result.body_map_schema_version, 2)
        self.assertEqual(len(result.body_map_data), 1)
        pt = result.body_map_data[0]
        self.assertAlmostEqual(pt["x"], 0.5)
        self.assertAlmostEqual(pt["y"], 0.3)
        self.assertEqual(pt["side"], "front")
        self.assertEqual(pt["label"], "L")

    def test_submitted_form_raises_state_error(self):
        form, _qe, _s = self._make_form(
            form_status=IntakeStatus.SUBMITTED,
        )
        with self.assertRaises(StateTransitionError):
            save_intake_body_map(
                intake_form_id=form.id,
                body_map_schema_version=1,
                body_map_data=[],
            )


# -- save_intake_consents ----------------------------------


@freeze_time("2026-03-10T12:00:00Z")
class SaveIntakeConsentsTests(IntakeServiceBaseTestCase):
    def _create_consent_def(self, **overrides):
        defaults = {
            "code": "TEST_CONSENT",
            "version": 1,
            "title_de": "Titel",
            "content_de": "Inhalt",
            "is_required": False,
            "is_active": True,
        }
        defaults.update(overrides)
        code = defaults.pop("code")
        version = defaults.pop("version")
        obj, _ = ConsentDefinition.objects.get_or_create(
            code=code,
            version=version,
            defaults=defaults,
        )
        return obj

    def test_happy_path_creates_consent(self):
        form, _qe, _s = self._make_form()
        cdef = self._create_consent_def()
        save_intake_consents(
            intake_form_id=form.id,
            consents_payload=[
                {
                    "consent_definition_id": cdef.id,
                    "accepted": True,
                },
            ],
        )
        pic = PatientIntakeConsent.objects.get(
            intake_form=form,
            consent_definition=cdef,
        )
        self.assertTrue(pic.accepted)
        self.assertIsNotNone(pic.accepted_at)

    def test_nonexistent_consent_raises(self):
        form, _qe, _s = self._make_form()
        with self.assertRaises(ConsentNotActiveError):
            save_intake_consents(
                intake_form_id=form.id,
                consents_payload=[
                    {
                        "consent_definition_id": (uuid.uuid4()),
                        "accepted": True,
                    },
                ],
            )

    def test_submitted_form_raises_state_error(self):
        form, _qe, _s = self._make_form(
            form_status=IntakeStatus.SUBMITTED,
        )
        with self.assertRaises(StateTransitionError):
            save_intake_consents(
                intake_form_id=form.id,
                consents_payload=[],
            )

    def test_contact_method_no_options_raises(self):
        form, _qe, _s = self._make_form()
        cdef = self._create_consent_def(
            code=CONTACT_METHOD_CONSENT_CODE,
        )
        with self.assertRaises(DomainError):
            save_intake_consents(
                intake_form_id=form.id,
                consents_payload=[
                    {
                        "consent_definition_id": cdef.id,
                        "accepted": True,
                    },
                ],
            )

    def test_contact_method_invalid_options_raises(self):
        form, _qe, _s = self._make_form()
        cdef = self._create_consent_def(
            code=CONTACT_METHOD_CONSENT_CODE,
        )
        with self.assertRaises(DomainError):
            save_intake_consents(
                intake_form_id=form.id,
                consents_payload=[
                    {
                        "consent_definition_id": cdef.id,
                        "accepted": True,
                        "selected_option_codes": [
                            "PIGEON",
                        ],
                    },
                ],
            )


# -- save_intake_signature ---------------------------------


@freeze_time("2026-03-10T12:00:00Z")
class SaveIntakeSignatureTests(IntakeServiceBaseTestCase):
    def setUp(self):
        super().setUp()
        self.tmp_dir = tempfile.mkdtemp()

    def test_happy_path_png(self):
        with self.settings(MEDIA_ROOT=self.tmp_dir):
            form, _qe, _s = self._make_form()
            b64 = base64.b64encode(VALID_PNG).decode()
            result = save_intake_signature(
                intake_form_id=form.id,
                signature_base64=b64,
            )
            result.refresh_from_db()
            self.assertTrue(result.signature_file_path)
            self.assertTrue(result.signature_sha256)

    def test_data_url_prefix_stripped(self):
        with self.settings(MEDIA_ROOT=self.tmp_dir):
            form, _qe, _s = self._make_form()
            raw_b64 = base64.b64encode(VALID_PNG).decode()
            data_url = f"data:image/png;base64,{raw_b64}"
            result = save_intake_signature(
                intake_form_id=form.id,
                signature_base64=data_url,
            )
            result.refresh_from_db()
            self.assertTrue(result.signature_file_path)

    def test_invalid_base64_raises(self):
        with self.settings(MEDIA_ROOT=self.tmp_dir):
            form, _qe, _s = self._make_form()
            with self.assertRaises(InvalidSignatureError):
                save_intake_signature(
                    intake_form_id=form.id,
                    signature_base64="!!!not-b64!!!",
                )

    def test_empty_decoded_bytes_raises(self):
        with self.settings(MEDIA_ROOT=self.tmp_dir):
            form, _qe, _s = self._make_form()
            b64 = base64.b64encode(b"").decode()
            with self.assertRaises(InvalidSignatureError):
                save_intake_signature(
                    intake_form_id=form.id,
                    signature_base64=b64,
                )

    def test_invalid_image_format_raises(self):
        with self.settings(MEDIA_ROOT=self.tmp_dir):
            form, _qe, _s = self._make_form()
            gif = b"GIF89a" + b"\x00" * 50
            b64 = base64.b64encode(gif).decode()
            with self.assertRaises(InvalidSignatureError):
                save_intake_signature(
                    intake_form_id=form.id,
                    signature_base64=b64,
                )

    def test_submitted_form_raises_state_error(self):
        form, _qe, _s = self._make_form(
            form_status=IntakeStatus.SUBMITTED,
        )
        with self.assertRaises(StateTransitionError):
            save_intake_signature(
                intake_form_id=form.id,
                signature_base64="irrelevant",
            )


# -- save_intake_anamnesis_payload -------------------------


@freeze_time("2026-03-10T12:00:00Z")
class SaveIntakeAnamnesisTests(IntakeServiceBaseTestCase):
    def test_happy_path_persists_anamnesis(self):
        form, _qe, _s = self._make_form()
        answers = [
            {
                "question_code": "Q_ALLERGY",
                "selected_option_codes": ["YES"],
                "free_text": None,
            },
        ]
        result = save_intake_anamnesis_payload(
            intake_form_id=form.id,
            anamnesis_schema_version=3,
            answers_payload=answers,
        )
        result.refresh_from_db()
        self.assertEqual(
            result.anamnesis_schema_version,
            3,
        )
        self.assertEqual(
            result.anamnesis_payload["answers"],
            answers,
        )

    def test_submitted_form_raises_state_error(self):
        form, _qe, _s = self._make_form(
            form_status=IntakeStatus.SUBMITTED,
        )
        with self.assertRaises(StateTransitionError):
            save_intake_anamnesis_payload(
                intake_form_id=form.id,
                anamnesis_schema_version=1,
                answers_payload=[],
            )


# -- submit_patient_intake_form error paths ----------------


@freeze_time("2026-03-10T12:00:00Z")
class SubmitIntakeFormErrorTests(IntakeServiceBaseTestCase):
    def test_no_signature_raises_state_error(self):
        form, _qe, _s = self._make_form()
        with self.assertRaises(StateTransitionError):
            submit_patient_intake_form(
                intake_form_id=form.id,
            )

    def test_consumed_session_raises(self):
        form, _qe, sess = self._make_form(
            signature_file_path="signatures/fake.png",
        )
        sess.consumed_at = timezone.now()
        sess.save(update_fields=["consumed_at"])
        with self.assertRaises(
            IntakeSessionValidationError,
        ):
            submit_patient_intake_form(
                intake_form_id=form.id,
            )

    def test_expired_session_raises(self):
        form, _qe, _s = self._make_form(
            signature_file_path="signatures/fake.png",
        )
        with freeze_time("2026-03-10T14:00:00Z"):
            with self.assertRaises(
                IntakeSessionValidationError,
            ):
                submit_patient_intake_form(
                    intake_form_id=form.id,
                )
