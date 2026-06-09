"""Family portal results: shared phone, separate phones, ambiguous phone+DOB."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

from django.test import Client, TestCase, override_settings

from apps.operations.models import AuditEvent
from apps.patient_results.document_services import (
    list_patient_documents,
    resolve_patient_befund_download,
)
from apps.patient_results.models import PatientResultsOtpSession
from apps.patient_results.services import request_otp, verify_otp
from apps.medical.models import (
    DocVersionStatus,
    MedicalDocStatus,
    MedicalDocumentVersion,
    PdfStatus,
)
from apps.medical.services import publish_document_version, save_draft_document_version
from apps.outbox.services import process_outbox_events
from apps.patient_results.tests.family_results_fixtures import (
    FIXED_OTP_FAMILY,
    TEST_PEPPER_FAMILY,
    MemberBundle,
    build_family_results_fixture,
)
from apps.core.api_utils import assign_group_to_test_user
from apps.reception.patient_identity import portal_identity_is_ambiguous

_TEST_SETTINGS = dict(
    CAPTCHA_VERIFY_SKIP=True,
    PATIENT_RESULTS_OTP_PEPPER=TEST_PEPPER_FAMILY,
    SMSAPI_USE_MOCK="1",
    RATELIMIT_ENABLE=False,
)

LOGIN_URL = "/"


def _latest_audit(event_type: str) -> AuditEvent | None:
    return (
        AuditEvent.objects.filter(event_type=event_type).order_by("-event_time").first()
    )


def _api_otp_login(
    client: Client,
    member: MemberBundle,
    *,
    last_name: str | None = None,
) -> None:
    """Request + verify OTP via API; leaves authenticated session on client."""
    client.cookies.clear()
    PatientResultsOtpSession.objects.filter(patient=member.patient).delete()
    request_body: dict[str, str] = {
        "phone": member.portal_phone,
        "date_of_birth": member.date_of_birth.isoformat(),
        "captcha_token": "skip",
    }
    if last_name:
        request_body["last_name"] = last_name
    with (
        patch(
            "apps.patient_results.services.random.randint",
            return_value=FIXED_OTP_FAMILY,
        ),
        patch("apps.patient_results.services.get_sms_adapter") as mock_sms,
    ):
        mock_sms.return_value.send_sms = MagicMock()
        req = client.post(
            "/api/v1/patient-results/request-otp",
            data=request_body,
            content_type="application/json",
        )
    assert req.status_code == 200, req.content

    verify_body: dict[str, str] = {
        "phone": member.portal_phone,
        "date_of_birth": member.date_of_birth.isoformat(),
        "otp_code": str(FIXED_OTP_FAMILY),
    }
    if last_name:
        verify_body["last_name"] = last_name
    verify = client.post(
        "/api/v1/patient-results/verify-otp",
        data=verify_body,
        content_type="application/json",
    )
    assert verify.status_code == 200, verify.content
    assert "sessionid" in client.cookies


class FamilyResultsTestCase(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.fixture = build_family_results_fixture()


class SharedPhoneFamilyResultsTests(FamilyResultsTestCase):
    """Rodzina A: jeden numer, różne DOB — każdy odbiera własny wynik."""

    @override_settings(**_TEST_SETTINGS)
    def test_each_member_receives_only_own_published_result(self) -> None:
        for member in self.fixture.shared_family_a:
            with self.subTest(member=member.key):
                PatientResultsOtpSession.objects.filter(patient=member.patient).delete()
                with (
                    patch(
                        "apps.patient_results.services.random.randint",
                        return_value=FIXED_OTP_FAMILY,
                    ),
                    patch("apps.patient_results.services.get_sms_adapter") as mock_sms,
                ):
                    mock_sms.return_value.send_sms = MagicMock()
                    req = request_otp(
                        phone=member.portal_phone,
                        date_of_birth=member.date_of_birth,
                        captcha_token="skip",
                    )
                self.assertEqual(req.audit_outcome, "sms_sent")
                self.assertFalse(req.needs_last_name)

                verify = verify_otp(
                    phone=member.portal_phone,
                    date_of_birth=member.date_of_birth,
                    otp_code=str(FIXED_OTP_FAMILY),
                )
                self.assertTrue(verify.success)
                self.assertEqual(verify.patient_id, str(member.patient.id))

                docs = list_patient_documents(member.patient.id)
                self.assertEqual(len(docs), 1)
                self.assertEqual(
                    docs[0]["version_id"], str(member.published_version.id)
                )

                for sibling in self.fixture.shared_family_a:
                    if sibling.key == member.key:
                        continue
                    resolution, _ = resolve_patient_befund_download(
                        sibling.published_version.id,
                        member.patient.id,
                    )
                    self.assertEqual(resolution, "not_found")

    @override_settings(**_TEST_SETTINGS)
    @patch("apps.patient_results.services.get_sms_adapter")
    def test_sibling_cannot_download_other_members_version(
        self, mock_get_adapter: MagicMock
    ) -> None:
        mock_get_adapter.return_value.send_sms = MagicMock()
        member1, member2, _ = self.fixture.shared_family_a
        with patch(
            "apps.patient_results.services.random.randint",
            return_value=FIXED_OTP_FAMILY,
        ):
            request_otp(
                phone=member1.portal_phone,
                date_of_birth=member1.date_of_birth,
                captcha_token="skip",
            )
        verify_otp(
            phone=member1.portal_phone,
            date_of_birth=member1.date_of_birth,
            otp_code=str(FIXED_OTP_FAMILY),
        )
        resolution, version = resolve_patient_befund_download(
            member2.published_version.id,
            member1.patient.id,
        )
        self.assertEqual(resolution, "not_found")
        self.assertIsNone(version)

    @override_settings(**_TEST_SETTINGS)
    @patch("apps.patient_results.services.get_sms_adapter")
    def test_wrong_dob_on_shared_phone_gets_no_session(
        self, mock_get_adapter: MagicMock
    ) -> None:
        mock_get_adapter.return_value.send_sms = MagicMock()
        member = self.fixture.shared_family_a[0]
        result = request_otp(
            phone=member.portal_phone,
            date_of_birth=date(1999, 12, 31),
            captcha_token="skip",
        )
        self.assertEqual(result.audit_outcome, "silent_no_op")
        self.assertEqual(PatientResultsOtpSession.objects.count(), 0)
        mock_get_adapter.return_value.send_sms.assert_not_called()


class SeparatePhoneFamilyResultsTests(FamilyResultsTestCase):
    """Rodzina B: osobne numery — każdy odbiera własny wynik."""

    @override_settings(**_TEST_SETTINGS)
    def test_each_member_with_own_phone_sees_only_own_document(self) -> None:
        for member in self.fixture.separate_family_b:
            with self.subTest(member=member.key):
                PatientResultsOtpSession.objects.filter(patient=member.patient).delete()
                with (
                    patch(
                        "apps.patient_results.services.random.randint",
                        return_value=FIXED_OTP_FAMILY,
                    ),
                    patch("apps.patient_results.services.get_sms_adapter") as mock_sms,
                ):
                    mock_sms.return_value.send_sms = MagicMock()
                    req = request_otp(
                        phone=member.portal_phone,
                        date_of_birth=member.date_of_birth,
                        captcha_token="skip",
                    )
                self.assertEqual(req.audit_outcome, "sms_sent")

                verify = verify_otp(
                    phone=member.portal_phone,
                    date_of_birth=member.date_of_birth,
                    otp_code=str(FIXED_OTP_FAMILY),
                )
                self.assertTrue(verify.success)

                docs = list_patient_documents(member.patient.id)
                self.assertEqual(len(docs), 1)
                self.assertEqual(
                    docs[0]["version_id"], str(member.published_version.id)
                )

    @override_settings(**_TEST_SETTINGS)
    @patch("apps.patient_results.services.get_sms_adapter")
    def test_phone_of_one_member_with_dob_of_another_fails_verify(
        self, mock_get_adapter: MagicMock
    ) -> None:
        mock_get_adapter.return_value.send_sms = MagicMock()
        m1, m2, _ = self.fixture.separate_family_b
        with patch(
            "apps.patient_results.services.random.randint",
            return_value=FIXED_OTP_FAMILY,
        ):
            request_otp(
                phone=m1.portal_phone,
                date_of_birth=m1.date_of_birth,
                captcha_token="skip",
            )
        verify = verify_otp(
            phone=m1.portal_phone,
            date_of_birth=m2.date_of_birth,
            otp_code=str(FIXED_OTP_FAMILY),
        )
        self.assertFalse(verify.success)

    @override_settings(**_TEST_SETTINGS)
    @patch("apps.patient_results.services.get_sms_adapter")
    def test_sibling_cannot_download_other_members_version(
        self, mock_get_adapter: MagicMock
    ) -> None:
        mock_get_adapter.return_value.send_sms = MagicMock()
        m1, m2, _ = self.fixture.separate_family_b
        with patch(
            "apps.patient_results.services.random.randint",
            return_value=FIXED_OTP_FAMILY,
        ):
            request_otp(
                phone=m1.portal_phone,
                date_of_birth=m1.date_of_birth,
                captcha_token="skip",
            )
        verify_otp(
            phone=m1.portal_phone,
            date_of_birth=m1.date_of_birth,
            otp_code=str(FIXED_OTP_FAMILY),
        )
        resolution, version = resolve_patient_befund_download(
            m2.published_version.id,
            m1.patient.id,
        )
        self.assertEqual(resolution, "not_found")
        self.assertIsNone(version)


class CrossFamilyIsolationTests(FamilyResultsTestCase):
    @override_settings(**_TEST_SETTINGS)
    @patch("apps.patient_results.services.get_sms_adapter")
    def test_family_a_member_does_not_see_family_b_documents(
        self, mock_get_adapter: MagicMock
    ) -> None:
        mock_get_adapter.return_value.send_sms = MagicMock()
        member_a = self.fixture.shared_family_a[0]
        member_b = self.fixture.separate_family_b[0]
        with patch(
            "apps.patient_results.services.random.randint",
            return_value=FIXED_OTP_FAMILY,
        ):
            request_otp(
                phone=member_a.portal_phone,
                date_of_birth=member_a.date_of_birth,
                captcha_token="skip",
            )
        verify_otp(
            phone=member_a.portal_phone,
            date_of_birth=member_a.date_of_birth,
            otp_code=str(FIXED_OTP_FAMILY),
        )
        docs_a = list_patient_documents(member_a.patient.id)
        self.assertEqual(len(docs_a), 1)
        self.assertNotEqual(docs_a[0]["version_id"], str(member_b.published_version.id))
        resolution, _ = resolve_patient_befund_download(
            member_b.published_version.id,
            member_a.patient.id,
        )
        self.assertEqual(resolution, "not_found")

    @override_settings(**_TEST_SETTINGS)
    def test_api_download_family_b_version_denied_for_family_a_session(self) -> None:
        client = Client()
        member_a = self.fixture.shared_family_a[0]
        member_b = self.fixture.separate_family_b[0]
        _api_otp_login(client, member_a)
        docs = client.get("/api/v1/patient-results/documents")
        self.assertEqual(docs.status_code, 200)
        self.assertEqual(len(docs.json()["items"]), 1)
        denied = client.get(
            f"/api/v1/patient-results/documents/{member_b.published_version.id}/download"
        )
        self.assertEqual(denied.status_code, 404)


class SharedPhoneAmbiguousIdentityTests(FamilyResultsTestCase):
    """Kolizja phone+DOB: needs_last_name; po nazwisku — własny wynik."""

    @override_settings(**_TEST_SETTINGS)
    def test_portal_identity_is_ambiguous_for_collision_pair(self) -> None:
        phone = self.fixture.collision_pair[0].portal_phone
        dob = self.fixture.collision_dob
        self.assertTrue(portal_identity_is_ambiguous(phone, dob))
        self.assertFalse(
            portal_identity_is_ambiguous(
                phone, dob, self.fixture.collision_pair[0].last_name
            )
        )

    @override_settings(**_TEST_SETTINGS)
    @patch("apps.patient_results.services.get_sms_adapter")
    def test_request_without_last_name_is_ambiguous_no_sms(
        self, mock_get_adapter: MagicMock
    ) -> None:
        mock_get_adapter.return_value.send_sms = MagicMock()
        phone = self.fixture.collision_pair[0].portal_phone
        dob = self.fixture.collision_dob
        self.assertTrue(portal_identity_is_ambiguous(phone, dob))

        result = request_otp(phone=phone, date_of_birth=dob, captcha_token="skip")
        self.assertEqual(result.audit_outcome, "ambiguous_identity")
        self.assertTrue(result.needs_last_name)
        self.assertEqual(PatientResultsOtpSession.objects.count(), 0)
        mock_get_adapter.return_value.send_sms.assert_not_called()

    @override_settings(**_TEST_SETTINGS)
    @patch("apps.patient_results.services.get_sms_adapter")
    def test_verify_without_last_name_same_as_invalid(
        self, mock_get_adapter: MagicMock
    ) -> None:
        mock_get_adapter.return_value.send_sms = MagicMock()
        gina, _ = self.fixture.collision_pair
        with patch(
            "apps.patient_results.services.random.randint",
            return_value=FIXED_OTP_FAMILY,
        ):
            request_otp(
                phone=gina.portal_phone,
                date_of_birth=gina.date_of_birth,
                captcha_token="skip",
                last_name=gina.last_name,
            )
        verify = verify_otp(
            phone=gina.portal_phone,
            date_of_birth=gina.date_of_birth,
            otp_code=str(FIXED_OTP_FAMILY),
        )
        self.assertFalse(verify.success)

    @override_settings(**_TEST_SETTINGS)
    def test_each_collision_member_gets_own_document_with_last_name(self) -> None:
        for member in self.fixture.collision_pair:
            with self.subTest(member=member.key):
                PatientResultsOtpSession.objects.filter(patient=member.patient).delete()
                with (
                    patch(
                        "apps.patient_results.services.random.randint",
                        return_value=FIXED_OTP_FAMILY,
                    ),
                    patch("apps.patient_results.services.get_sms_adapter") as mock_sms,
                ):
                    mock_sms.return_value.send_sms = MagicMock()
                    req = request_otp(
                        phone=member.portal_phone,
                        date_of_birth=member.date_of_birth,
                        captcha_token="skip",
                        last_name=member.last_name,
                    )
                self.assertEqual(req.audit_outcome, "sms_sent")

                verify = verify_otp(
                    phone=member.portal_phone,
                    date_of_birth=member.date_of_birth,
                    otp_code=str(FIXED_OTP_FAMILY),
                    last_name=member.last_name,
                )
                self.assertTrue(verify.success)

                docs = list_patient_documents(member.patient.id)
                self.assertEqual(len(docs), 1)
                self.assertEqual(
                    docs[0]["version_id"], str(member.published_version.id)
                )

                other = (
                    self.fixture.collision_pair[1]
                    if member.key == "c1"
                    else self.fixture.collision_pair[0]
                )
                resolution, _ = resolve_patient_befund_download(
                    other.published_version.id,
                    member.patient.id,
                )
                self.assertEqual(resolution, "not_found")

    @override_settings(**_TEST_SETTINGS)
    @patch("apps.patient_results.services.get_sms_adapter")
    def test_wrong_last_name_still_ambiguous(self, mock_get_adapter: MagicMock) -> None:
        mock_get_adapter.return_value.send_sms = MagicMock()
        member = self.fixture.collision_pair[0]
        result = request_otp(
            phone=member.portal_phone,
            date_of_birth=member.date_of_birth,
            captcha_token="skip",
            last_name="Wrongname",
        )
        self.assertEqual(result.audit_outcome, "ambiguous_identity")
        self.assertTrue(result.needs_last_name)
        mock_get_adapter.return_value.send_sms.assert_not_called()


@override_settings(**_TEST_SETTINGS)
class SharedPhoneFamilyApiE2ETests(FamilyResultsTestCase):
    def test_api_flow_each_shared_phone_member_sees_own_documents(self) -> None:
        client = Client()
        for member in self.fixture.shared_family_a:
            with self.subTest(member=member.key):
                _api_otp_login(client, member)
                docs = client.get("/api/v1/patient-results/documents")
                self.assertEqual(docs.status_code, 200)
                items = docs.json()["items"]
                self.assertEqual(len(items), 1)
                self.assertEqual(
                    items[0]["version_id"], str(member.published_version.id)
                )
                for sibling in self.fixture.shared_family_a:
                    if sibling.key == member.key:
                        continue
                    denied = client.get(
                        f"/api/v1/patient-results/documents/{sibling.published_version.id}/download"
                    )
                    self.assertEqual(denied.status_code, 404)


@override_settings(**_TEST_SETTINGS)
class SeparatePhoneFamilyApiE2ETests(FamilyResultsTestCase):
    def test_api_flow_each_separate_phone_member_sees_own_documents(self) -> None:
        client = Client()
        for member in self.fixture.separate_family_b:
            with self.subTest(member=member.key):
                _api_otp_login(client, member)
                docs = client.get("/api/v1/patient-results/documents")
                self.assertEqual(docs.status_code, 200)
                items = docs.json()["items"]
                self.assertEqual(len(items), 1)
                self.assertEqual(
                    items[0]["version_id"], str(member.published_version.id)
                )
                for sibling in self.fixture.separate_family_b:
                    if sibling.key == member.key:
                        continue
                    denied = client.get(
                        f"/api/v1/patient-results/documents/{sibling.published_version.id}/download"
                    )
                    self.assertEqual(denied.status_code, 404)


@override_settings(**_TEST_SETTINGS)
class AmbiguousIdentityApiHtmlTests(FamilyResultsTestCase):
    def setUp(self) -> None:
        self.client = Client()

    @patch("apps.patient_results.services.get_sms_adapter")
    def test_api_request_otp_needs_last_name_when_ambiguous(
        self, mock_get_adapter: MagicMock
    ) -> None:
        mock_get_adapter.return_value.send_sms = MagicMock()
        phone = self.fixture.collision_pair[0].portal_phone
        dob = self.fixture.collision_dob
        response = self.client.post(
            "/api/v1/patient-results/request-otp",
            data={
                "phone": phone,
                "date_of_birth": dob.isoformat(),
                "captcha_token": "skip",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "needs_last_name": True})
        ev = (
            AuditEvent.objects.filter(event_type="PATIENT_RESULTS_OTP_REQUEST")
            .order_by("-event_time")
            .first()
        )
        self.assertEqual(ev.metadata.get("outcome"), "ambiguous_identity")
        self.assertIsNone(ev.patient_id)

    @patch("apps.patient_results.services.get_sms_adapter")
    def test_api_request_otp_wrong_last_name_audits_ambiguous_identity(
        self, mock_get_adapter: MagicMock
    ) -> None:
        mock_get_adapter.return_value.send_sms = MagicMock()
        phone = self.fixture.collision_pair[0].portal_phone
        dob = self.fixture.collision_dob
        response = self.client.post(
            "/api/v1/patient-results/request-otp",
            data={
                "phone": phone,
                "date_of_birth": dob.isoformat(),
                "captcha_token": "skip",
                "last_name": "Wrongname",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "needs_last_name": True})
        ev = _latest_audit("PATIENT_RESULTS_OTP_REQUEST")
        assert ev is not None
        self.assertEqual(ev.metadata.get("outcome"), "ambiguous_identity")
        self.assertIsNone(ev.patient_id)
        mock_get_adapter.return_value.send_sms.assert_not_called()

    @patch("apps.patient_results.services.get_sms_adapter")
    def test_api_verify_collision_without_last_name_audits_invalid(
        self, mock_get_adapter: MagicMock
    ) -> None:
        mock_get_adapter.return_value.send_sms = MagicMock()
        gina = self.fixture.collision_pair[0]
        with patch(
            "apps.patient_results.services.random.randint",
            return_value=FIXED_OTP_FAMILY,
        ):
            self.client.post(
                "/api/v1/patient-results/request-otp",
                data={
                    "phone": gina.portal_phone,
                    "date_of_birth": gina.date_of_birth.isoformat(),
                    "captcha_token": "skip",
                    "last_name": gina.last_name,
                },
                content_type="application/json",
            )
        verify = self.client.post(
            "/api/v1/patient-results/verify-otp",
            data={
                "phone": gina.portal_phone,
                "date_of_birth": gina.date_of_birth.isoformat(),
                "otp_code": str(FIXED_OTP_FAMILY),
            },
            content_type="application/json",
        )
        self.assertEqual(verify.status_code, 400)
        self.assertNotIn("sessionid", self.client.cookies)
        ev = _latest_audit("PATIENT_RESULTS_OTP_VERIFY")
        assert ev is not None
        self.assertEqual(ev.metadata.get("outcome"), "invalid")
        self.assertIsNone(ev.patient_id)

    @patch("apps.patient_results.services.get_sms_adapter")
    def test_api_verify_collision_with_last_name_audits_success(
        self, mock_get_adapter: MagicMock
    ) -> None:
        mock_get_adapter.return_value.send_sms = MagicMock()
        gina = self.fixture.collision_pair[0]
        with patch(
            "apps.patient_results.services.random.randint",
            return_value=FIXED_OTP_FAMILY,
        ):
            self.client.post(
                "/api/v1/patient-results/request-otp",
                data={
                    "phone": gina.portal_phone,
                    "date_of_birth": gina.date_of_birth.isoformat(),
                    "captcha_token": "skip",
                    "last_name": gina.last_name,
                },
                content_type="application/json",
            )
        verify = self.client.post(
            "/api/v1/patient-results/verify-otp",
            data={
                "phone": gina.portal_phone,
                "date_of_birth": gina.date_of_birth.isoformat(),
                "otp_code": str(FIXED_OTP_FAMILY),
                "last_name": gina.last_name,
            },
            content_type="application/json",
        )
        self.assertEqual(verify.status_code, 200)
        ev = _latest_audit("PATIENT_RESULTS_OTP_VERIFY")
        assert ev is not None
        self.assertEqual(ev.metadata.get("outcome"), "success")
        self.assertEqual(ev.patient_id, gina.patient.id)

    @patch("apps.patient_results.services.get_sms_adapter")
    def test_html_login_shows_last_name_field_when_ambiguous(
        self, mock_get_adapter: MagicMock
    ) -> None:
        mock_get_adapter.return_value.send_sms = MagicMock()
        phone = self.fixture.collision_pair[0].portal_phone
        dob = self.fixture.collision_dob
        request_audits_before = AuditEvent.objects.filter(
            event_type="PATIENT_RESULTS_OTP_REQUEST"
        ).count()
        response = self.client.post(
            LOGIN_URL,
            {
                "phone": phone,
                "date_of_birth": dob.isoformat(),
                "captcha_token": "skip",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nachnamen")
        self.assertIsNone(self.client.session.get("ergebnisse_phone"))
        request_audits_after = AuditEvent.objects.filter(
            event_type="PATIENT_RESULTS_OTP_REQUEST"
        ).count()
        self.assertEqual(request_audits_before, request_audits_after)

    @patch("apps.patient_results.services.get_sms_adapter")
    def test_html_login_wrong_last_name_still_shows_last_name_field(
        self, mock_get_adapter: MagicMock
    ) -> None:
        mock_get_adapter.return_value.send_sms = MagicMock()
        phone = self.fixture.collision_pair[0].portal_phone
        dob = self.fixture.collision_dob
        request_audits_before = AuditEvent.objects.filter(
            event_type="PATIENT_RESULTS_OTP_REQUEST"
        ).count()
        response = self.client.post(
            LOGIN_URL,
            {
                "phone": phone,
                "date_of_birth": dob.isoformat(),
                "captcha_token": "skip",
                "last_name": "Wrongname",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nachnamen")
        self.assertIsNone(self.client.session.get("ergebnisse_phone"))
        mock_get_adapter.return_value.send_sms.assert_not_called()
        request_audits_after = AuditEvent.objects.filter(
            event_type="PATIENT_RESULTS_OTP_REQUEST"
        ).count()
        self.assertEqual(request_audits_before, request_audits_after)

    def test_api_e2e_each_collision_member_with_last_name(self) -> None:
        for member in self.fixture.collision_pair:
            with self.subTest(member=member.key):
                client = Client()
                _api_otp_login(client, member, last_name=member.last_name)
                docs = client.get("/api/v1/patient-results/documents")
                self.assertEqual(docs.status_code, 200)
                self.assertEqual(len(docs.json()["items"]), 1)
                self.assertEqual(
                    docs.json()["items"][0]["version_id"],
                    str(member.published_version.id),
                )
                other = (
                    self.fixture.collision_pair[1]
                    if member.key == "c1"
                    else self.fixture.collision_pair[0]
                )
                denied = client.get(
                    f"/api/v1/patient-results/documents/{other.published_version.id}/download"
                )
                self.assertEqual(denied.status_code, 404)


@override_settings(
    CAPTCHA_VERIFY_SKIP=True,
    PATIENT_RESULTS_OTP_PEPPER=TEST_PEPPER_FAMILY,
    SMSAPI_USE_MOCK="1",
    HIDRIVE_USE_MOCK="1",
)
class FamilyOutboxPortalSmokeTests(FamilyResultsTestCase):
    """Publish → outbox chain → portal lists the new Befund (rodzina A, 1 członek)."""

    def test_publish_outbox_then_portal_lists_document(self) -> None:
        from uuid import uuid4

        member = self.fixture.shared_family_a[0]
        assign_group_to_test_user(self.fixture.actor, "Doctor")

        medical_document = member.published_version.medical_document
        MedicalDocumentVersion.objects.filter(
            medical_document=medical_document
        ).delete()
        medical_document.status = MedicalDocStatus.DRAFT
        medical_document.current_version_no = 0
        medical_document.published_version_no = None
        medical_document.save(
            update_fields=[
                "status",
                "current_version_no",
                "published_version_no",
                "updated_at",
            ]
        )

        save_draft_document_version(
            medical_document_id=medical_document.id,
            updated_by_user_id=self.fixture.actor.id,
            medical_payload={"authoring_locale": "de-DE", "family_smoke": True},
        )
        version = publish_document_version(
            medical_document_id=medical_document.id,
            publish_request_id=uuid4(),
            published_by_user_id=self.fixture.actor.id,
            publish_locale="de-DE",
        )

        for _ in range(3):
            process_outbox_events()

        version.refresh_from_db()
        self.assertEqual(version.pdf_generation_status, PdfStatus.COMPLETED)
        self.assertTrue(version.pdf_local_path)

        with (
            patch(
                "apps.patient_results.services.random.randint",
                return_value=FIXED_OTP_FAMILY,
            ),
            patch("apps.patient_results.services.get_sms_adapter") as mock_sms,
        ):
            mock_sms.return_value.send_sms = MagicMock()
            req = request_otp(
                phone=member.portal_phone,
                date_of_birth=member.date_of_birth,
                captcha_token="skip",
            )
        self.assertEqual(req.audit_outcome, "sms_sent")
        verify = verify_otp(
            phone=member.portal_phone,
            date_of_birth=member.date_of_birth,
            otp_code=str(FIXED_OTP_FAMILY),
        )
        self.assertTrue(verify.success)

        docs = list_patient_documents(member.patient.id)
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0]["version_id"], str(version.id))
        self.assertEqual(version.version_status, DocVersionStatus.PUBLISHED)
