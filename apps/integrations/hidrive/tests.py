from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, TestCase, override_settings

from apps.integrations.hidrive.auth import (
    HiDriveOAuthClient,
    get_hidrive_refresh_metrics,
)
from apps.integrations.hidrive.client import get_hidrive_adapter


class HiDriveAuthTests(SimpleTestCase):
    @override_settings(
        HIDRIVE_CLIENT_ID="cid",
        HIDRIVE_CLIENT_SECRET="sec",
        HIDRIVE_REFRESH_TOKEN="rtok",
        HIDRIVE_TOKEN_URL="https://my.hidrive.com/oauth2/token",
        HIDRIVE_TIMEOUT_SECONDS=7,
    )
    @patch("apps.integrations.hidrive.auth.requests.post")
    def test_refresh_access_token_uses_refresh_token_grant(
        self, post_mock: Mock
    ) -> None:
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "access_token": "a1",
            "expires_in": 3600,
            "refresh_token": "r2",
        }
        post_mock.return_value = response

        client = HiDriveOAuthClient()
        token = client.get_access_token()

        self.assertEqual(token, "a1")
        post_mock.assert_called_once()
        _, kwargs = post_mock.call_args
        self.assertEqual(kwargs["data"]["grant_type"], "refresh_token")
        self.assertEqual(kwargs["data"]["refresh_token"], "rtok")

    @override_settings(
        HIDRIVE_CLIENT_ID="cid",
        HIDRIVE_CLIENT_SECRET="sec",
        HIDRIVE_REFRESH_TOKEN="rtok",
        HIDRIVE_TOKEN_URL="https://my.hidrive.com/oauth2/token",
        HIDRIVE_TIMEOUT_SECONDS=7,
    )
    @patch("apps.integrations.hidrive.auth.requests.post")
    def test_cached_access_token_skips_extra_refresh_until_forced(
        self, post_mock: Mock
    ) -> None:
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "access_token": "a1",
            "expires_in": 3600,
            "refresh_token": "r2",
        }
        post_mock.return_value = response

        client = HiDriveOAuthClient()
        token_1 = client.get_access_token()
        token_2 = client.get_access_token()
        token_3 = client.get_access_token(force_refresh=True)

        self.assertEqual(token_1, "a1")
        self.assertEqual(token_2, "a1")
        self.assertEqual(token_3, "a1")
        self.assertEqual(post_mock.call_count, 2)


class HiDriveAdapterTests(TestCase):
    @override_settings(HIDRIVE_USE_MOCK="1")
    def test_mock_adapter_does_not_require_existing_file(self) -> None:
        adapter = get_hidrive_adapter()
        adapter.upload(
            remote_path="/hidrive/patients/p/a.pdf",
            local_path=Path("/not-existing.pdf"),
        )

    @override_settings(HIDRIVE_USE_MOCK="0")
    @patch("apps.integrations.hidrive.client.requests.put")
    @patch("apps.integrations.hidrive.client.requests.post")
    @patch("apps.integrations.hidrive.client.requests.get")
    @patch("apps.integrations.hidrive.client.get_hidrive_oauth_client")
    def test_real_adapter_retries_once_after_401(
        self,
        oauth_client_mock: Mock,
        get_mock: Mock,
        post_mock: Mock,
        put_mock: Mock,
    ) -> None:
        oauth = Mock()
        oauth.get_access_token.side_effect = ["tok-1", "tok-2"]
        oauth_client_mock.return_value = oauth

        user_me = Mock()
        user_me.status_code = 200
        user_me.json.return_value = {"alias": "cogitomedica"}
        get_mock.return_value = user_me

        dir_created = Mock()
        dir_created.status_code = 201
        post_mock.return_value = dir_created

        unauthorized = Mock()
        unauthorized.status_code = 401
        ok = Mock()
        ok.status_code = 200
        put_mock.side_effect = [unauthorized, ok]

        temp_file = Path("temp_hidrive_test.bin")
        temp_file.write_bytes(b"x")
        self.addCleanup(lambda: temp_file.unlink(missing_ok=True))

        adapter = get_hidrive_adapter()
        adapter.upload(remote_path="/hidrive/patients/p/a.pdf", local_path=temp_file)

        self.assertEqual(put_mock.call_count, 2)
        created_paths = [
            call.kwargs["params"]["path"] for call in post_mock.call_args_list
        ]
        self.assertNotIn("/users", created_paths)
        self.assertNotIn("/users/cogitomedica", created_paths)
        self.assertIn("/users/cogitomedica/hidrive", created_paths)


class HiDriveMetricsTests(SimpleTestCase):
    def test_refresh_metrics_expose_attempt_and_error_labels(self) -> None:
        stats = get_hidrive_refresh_metrics()
        self.assertIn("attempt", stats)
        self.assertIn("error", stats)
