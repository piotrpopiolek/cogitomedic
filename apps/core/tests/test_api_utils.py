"""Tests for apps.core.api_utils — parsing, auth, scoping."""

from __future__ import annotations

import json
from unittest.mock import Mock
from uuid import uuid4

from django.http import HttpRequest
from django.test import SimpleTestCase, TestCase, RequestFactory

from apps.core.api_utils import (
    get_scoped_clinic_site_ids,
    json_domain_error,
    json_error,
    parse_bool_query,
    parse_list_limit,
    parse_positive_int,
    read_json_body,
    require_actor_match,
    require_user_role,
    safe_parse_positive_int,
)
from apps.core.exceptions import (
    DomainError,
    InvalidRequestBodyEncoding,
)

# =================================================================
# Pure-function tests — no DB
# =================================================================


class ParseBoolQueryTests(SimpleTestCase):
    def test_true_variants(self):
        for val in ("1", "true", "yes", "y", "TRUE", " Yes "):
            self.assertTrue(
                parse_bool_query(val),
                msg=f"Expected True for {val!r}",
            )

    def test_false_variants(self):
        for val in ("0", "false", "no", "n", "FALSE", " No "):
            self.assertFalse(
                parse_bool_query(val),
                msg=f"Expected False for {val!r}",
            )

    def test_none_returns_none(self):
        self.assertIsNone(parse_bool_query(None))

    def test_garbage_returns_none(self):
        self.assertIsNone(parse_bool_query("maybe"))


class ParsePositiveIntTests(SimpleTestCase):
    def test_valid_value(self):
        self.assertEqual(parse_positive_int("50", default=10), 50)

    def test_empty_returns_default(self):
        self.assertEqual(parse_positive_int("", default=10), 10)

    def test_below_minimum(self):
        self.assertEqual(parse_positive_int("0", default=10, minimum=1), 1)

    def test_above_maximum(self):
        self.assertEqual(
            parse_positive_int("200", default=10, maximum=100),
            100,
        )

    def test_invalid_raises(self):
        with self.assertRaises(ValueError):
            parse_positive_int("abc", default=10)


class SafeParsePositiveIntTests(SimpleTestCase):
    def test_valid_value(self):
        self.assertEqual(safe_parse_positive_int("50", default=10), 50)

    def test_none_returns_default(self):
        self.assertEqual(safe_parse_positive_int(None, default=20), 20)

    def test_empty_returns_default(self):
        self.assertEqual(safe_parse_positive_int("  ", default=20), 20)

    def test_invalid_returns_default(self):
        self.assertEqual(safe_parse_positive_int("abc", default=20), 20)

    def test_below_minimum_clamped(self):
        self.assertEqual(
            safe_parse_positive_int("-5", default=10, minimum=1),
            1,
        )

    def test_above_maximum_clamped(self):
        self.assertEqual(
            safe_parse_positive_int("999", default=10, maximum=100),
            100,
        )


class ParseListLimitTests(SimpleTestCase):
    def test_default(self):
        self.assertEqual(parse_list_limit(None), 20)

    def test_custom_value(self):
        self.assertEqual(parse_list_limit("50"), 50)

    def test_capped_at_100(self):
        self.assertEqual(parse_list_limit("999"), 100)


class ReadJsonBodyTests(SimpleTestCase):
    def _make_request(self, body: bytes) -> HttpRequest:
        factory = RequestFactory()
        request = factory.post(
            "/api/test",
            data=body,
            content_type="application/json",
        )
        return request

    def test_valid_json(self):
        body = json.dumps({"key": "val"}).encode()
        result = read_json_body(self._make_request(body))
        self.assertEqual(result, {"key": "val"})

    def test_empty_body_returns_empty_dict(self):
        result = read_json_body(self._make_request(b""))
        self.assertEqual(result, {})

    def test_too_large_raises(self):
        big = b"x" * (1024 * 1024 + 1)
        with self.assertRaises(InvalidRequestBodyEncoding):
            read_json_body(self._make_request(big))


class JsonErrorTests(SimpleTestCase):
    def test_plain_message(self):
        resp = json_error("Something went wrong", status=400)
        self.assertEqual(resp.status_code, 400)
        data = json.loads(resp.content)
        self.assertEqual(data["error"], "Something went wrong")


class JsonDomainErrorTests(TestCase):
    def test_domain_error_with_key(self):
        exc = DomainError("fallback msg")
        exc.api_message_key = "other.domain.test_key"
        exc.api_message_params = {}
        resp = json_domain_error(exc)
        self.assertEqual(resp.status_code, 400)

    def test_domain_error_without_key(self):
        exc = DomainError("plain message")
        resp = json_domain_error(exc)
        self.assertEqual(resp.status_code, 400)
        data = json.loads(resp.content)
        self.assertEqual(data["error"], "plain message")

    def test_invalid_encoding_error(self):
        exc = InvalidRequestBodyEncoding(
            "bad encoding",
            api_message_key="other.api.invalid_request_encoding",
            http_status=400,
        )
        resp = json_domain_error(exc)
        self.assertEqual(resp.status_code, 400)


class RequireUserRoleTests(TestCase):
    def _make_request(self, user):
        factory = RequestFactory()
        req = factory.get("/api/test")
        req.user = user
        return req

    def test_unauthenticated_returns_401(self):
        user = Mock(is_authenticated=False)
        req = self._make_request(user)
        resp = require_user_role(req, allowed_roles={"DOCTOR"})
        self.assertIsNotNone(resp)
        self.assertEqual(resp.status_code, 401)

    def test_wrong_role_returns_403(self):
        user = Mock(
            is_authenticated=True,
            is_doctor=False,
            is_admin_role=False,
            is_reception=False,
            is_tablet=False,
        )
        req = self._make_request(user)
        resp = require_user_role(req, allowed_roles={"DOCTOR"})
        self.assertIsNotNone(resp)
        self.assertEqual(resp.status_code, 403)

    def test_doctor_allowed(self):
        user = Mock(
            is_authenticated=True,
            is_doctor=True,
            is_admin_role=False,
            is_reception=False,
            is_tablet=False,
        )
        req = self._make_request(user)
        resp = require_user_role(req, allowed_roles={"DOCTOR"})
        self.assertIsNone(resp)

    def test_admin_allowed(self):
        user = Mock(
            is_authenticated=True,
            is_doctor=False,
            is_admin_role=True,
            is_reception=False,
            is_tablet=False,
        )
        req = self._make_request(user)
        resp = require_user_role(req, allowed_roles={"ADMIN"})
        self.assertIsNone(resp)

    def test_reception_allowed(self):
        user = Mock(
            is_authenticated=True,
            is_doctor=False,
            is_admin_role=False,
            is_reception=True,
            is_tablet=False,
        )
        req = self._make_request(user)
        resp = require_user_role(req, allowed_roles={"RECEPTION"})
        self.assertIsNone(resp)

    def test_tablet_allowed(self):
        user = Mock(
            is_authenticated=True,
            is_doctor=False,
            is_admin_role=False,
            is_reception=False,
            is_tablet=True,
        )
        req = self._make_request(user)
        resp = require_user_role(req, allowed_roles={"TABLET"})
        self.assertIsNone(resp)


class RequireActorMatchTests(TestCase):
    def _make_request(self, user_id):
        factory = RequestFactory()
        req = factory.get("/api/test")
        req.user = Mock(id=user_id)
        return req

    def test_matching_actor(self):
        uid = uuid4()
        req = self._make_request(uid)
        self.assertIsNone(require_actor_match(req, uid))

    def test_none_actor_passes(self):
        req = self._make_request(uuid4())
        self.assertIsNone(require_actor_match(req, None))

    def test_mismatched_actor_returns_403(self):
        req = self._make_request(uuid4())
        resp = require_actor_match(req, uuid4())
        self.assertIsNotNone(resp)
        self.assertEqual(resp.status_code, 403)


class GetScopedClinicSiteIdsTests(SimpleTestCase):
    def test_admin_returns_none(self):
        user = Mock(is_admin_role=True)
        self.assertIsNone(get_scoped_clinic_site_ids(user))

    def test_reception_returns_ids(self):
        user = Mock(
            is_admin_role=False,
            is_reception=True,
        )
        user.clinic_sites.values_list.return_value = [uuid4()]
        result = get_scoped_clinic_site_ids(user)
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 1)

    def test_doctor_returns_ids(self):
        user = Mock(
            is_admin_role=False,
            is_reception=False,
            is_doctor=True,
        )
        user.clinic_sites.values_list.return_value = []
        result = get_scoped_clinic_site_ids(user)
        self.assertEqual(result, [])

    def test_tablet_returns_ids(self):
        user = Mock(
            is_admin_role=False,
            is_reception=False,
            is_doctor=False,
            is_tablet=True,
        )
        user.clinic_sites.values_list.return_value = [
            uuid4(),
            uuid4(),
        ]
        result = get_scoped_clinic_site_ids(user)
        self.assertEqual(len(result), 2)

    def test_unknown_role_returns_empty(self):
        user = Mock(
            is_admin_role=False,
            is_reception=False,
            is_doctor=False,
            is_tablet=False,
        )
        result = get_scoped_clinic_site_ids(user)
        self.assertEqual(result, [])
