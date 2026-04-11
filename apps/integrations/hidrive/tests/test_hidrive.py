from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from apps.integrations.hidrive.auth import (
    HiDriveOAuthClient,
    get_hidrive_refresh_metrics,
)
from apps.integrations.hidrive import client as hidrive_client
from apps.integrations.hidrive.client import (
    _parse_dir_list_response,
    get_hidrive_adapter,
)


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


class HiDriveAdapterMockUploadTests(SimpleTestCase):
    @override_settings(HIDRIVE_USE_MOCK="1")
    def test_mock_adapter_does_not_require_existing_file(self) -> None:
        adapter = get_hidrive_adapter()
        adapter.upload(
            remote_path="/patients/p/a.pdf",
            local_path=Path("/not-existing.pdf"),
        )


class HiDriveRealAdapterUploadTests(SimpleTestCase):
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
        adapter.upload(remote_path="/patients/p/a.pdf", local_path=temp_file)

        self.assertEqual(put_mock.call_count, 2)
        created_paths = [
            call.kwargs["params"]["path"] for call in post_mock.call_args_list
        ]
        self.assertNotIn("/users", created_paths)
        self.assertNotIn("/users/cogitomedica", created_paths)
        self.assertIn("/users/cogitomedica/patients", created_paths)
        self.assertIn("/users/cogitomedica/patients/p", created_paths)


class HiDriveParseDirListResponseTests(SimpleTestCase):
    def test_parse_appends_pdf_when_mime_is_pdf_and_basename_has_no_extension(
        self,
    ) -> None:
        out = _parse_dir_list_response(
            resolved_dir_path="/users/cogito/incoming",
            payload=[
                {
                    "name": "Jean_Christophe_Scheider",
                    "mime": "application/pdf",
                    "size": 1,
                }
            ],
        )
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["name"], "Jean_Christophe_Scheider.pdf")
        self.assertTrue(out[0]["path"].endswith("/Jean_Christophe_Scheider.pdf"))

    def test_parse_does_not_invent_pdf_without_mime(self) -> None:
        out = _parse_dir_list_response(
            resolved_dir_path="/users/c/incoming",
            payload=[{"name": "NoExt", "size": 1}],
        )
        self.assertEqual(out[0]["name"], "NoExt")
        self.assertEqual(out[0]["path"], "/users/c/incoming/NoExt")

    def test_parse_reads_members_nested_under_result(self) -> None:
        out = _parse_dir_list_response(
            resolved_dir_path="/users/x/incoming",
            payload={
                "result": {
                    "members": [
                        {"name": "A.pdf", "path": "/users/x/incoming/A.pdf", "size": 3}
                    ]
                }
            },
        )
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["name"], "A.pdf")

    def test_parse_flattens_file_wrapper_object(self) -> None:
        out = _parse_dir_list_response(
            resolved_dir_path="/users/x/incoming",
            payload={
                "members": [
                    {
                        "type": "file",
                        "file": {
                            "name": "Wrap.pdf",
                            "path": "/users/x/incoming/Wrap.pdf",
                            "size": 9,
                        },
                    }
                ]
            },
        )
        self.assertEqual(out[0]["name"], "Wrap.pdf")
        self.assertEqual(out[0]["size"], 9)


class HiDriveRealAdapterMoveFileTests(SimpleTestCase):
    @override_settings(HIDRIVE_USE_MOCK="0")
    @patch("apps.integrations.hidrive.client.requests.post")
    @patch("apps.integrations.hidrive.client.requests.get")
    @patch("apps.integrations.hidrive.client.get_hidrive_oauth_client")
    def test_real_adapter_move_file_creates_destination_parent_dirs(
        self,
        oauth_client_mock: Mock,
        get_mock: Mock,
        post_mock: Mock,
    ) -> None:
        """POST /file/move must run after mkdir chain; mkdir-only was not enough when PATCH /file was wrong API."""
        oauth = Mock()
        oauth.get_access_token.return_value = "tok-1"
        oauth_client_mock.return_value = oauth

        user_me = Mock()
        user_me.status_code = 200
        user_me.json.return_value = {"alias": "cogitomedica"}

        dir_created = Mock()
        dir_created.status_code = 201

        move_ok = Mock()
        move_ok.status_code = 200

        get_mock.return_value = user_me
        order: list[str] = []

        def post_side_effect(url, **_kwargs):
            order.append("post")
            if "/file/move" in str(url):
                return move_ok
            return dir_created

        post_mock.side_effect = post_side_effect

        adapter = get_hidrive_adapter()
        adapter.move_file(
            source_path="/incoming/a.pdf",
            dest_path="/processed/a.pdf",
        )

        move_calls = [
            c
            for c in post_mock.call_args_list
            if c.args and "/file/move" in str(c.args[0])
        ]
        self.assertEqual(len(move_calls), 1, post_mock.call_args_list)
        move_kw = move_calls[0].kwargs
        self.assertEqual(
            move_kw.get("params", {}).get("src"),
            "/users/cogitomedica/incoming/a.pdf",
        )
        self.assertEqual(
            move_kw.get("params", {}).get("dst"),
            "/users/cogitomedica/processed/a.pdf",
        )
        self.assertEqual(move_kw.get("params", {}).get("on_exist"), "overwrite")
        self.assertGreaterEqual(len(order), 2)

    @override_settings(HIDRIVE_USE_MOCK="0")
    @patch("apps.integrations.hidrive.client.requests.post")
    @patch("apps.integrations.hidrive.client.requests.get")
    @patch("apps.integrations.hidrive.client.get_hidrive_oauth_client")
    def test_real_adapter_move_file_404_when_dest_exists_is_success(
        self,
        oauth_client_mock: Mock,
        get_mock: Mock,
        post_mock: Mock,
    ) -> None:
        """Outbox retry: source already moved (POST /file/move → 404) but dest present → idempotent OK."""
        oauth = Mock()
        oauth.get_access_token.return_value = "tok-1"
        oauth_client_mock.return_value = oauth

        user_me = Mock()
        user_me.status_code = 200
        user_me.json.return_value = {"alias": "cogitomedica"}

        dir_created = Mock()
        dir_created.status_code = 201

        move_missing_src = Mock()
        move_missing_src.status_code = 404
        move_missing_src.text = "No such file or directory"

        dest_probe = Mock()
        dest_probe.status_code = 206

        get_mock.side_effect = [
            user_me,
            user_me,
            user_me,
            dest_probe,
        ]

        def post_side_effect(url, **_kwargs):
            if "/file/move" in str(url):
                return move_missing_src
            return dir_created

        post_mock.side_effect = post_side_effect

        adapter = get_hidrive_adapter()
        adapter.move_file(
            source_path="/incoming/a.pdf",
            dest_path="/processed/a.pdf",
        )

        file_gets = [
            c
            for c in get_mock.call_args_list
            if c.args and str(c.args[0]).endswith("/file")
        ]
        self.assertEqual(len(file_gets), 1)
        self.assertEqual(
            (file_gets[0].kwargs.get("params") or {}).get("path"),
            "/users/cogitomedica/processed/a.pdf",
        )
        range_hdr = (file_gets[0].kwargs.get("headers") or {}).get("Range")
        self.assertEqual(range_hdr, "bytes=0-0")

    @override_settings(HIDRIVE_USE_MOCK="0")
    @patch("apps.integrations.hidrive.client.requests.post")
    @patch("apps.integrations.hidrive.client.requests.get")
    @patch("apps.integrations.hidrive.client.get_hidrive_oauth_client")
    def test_real_adapter_move_file_404_idempotent_when_range_probe_ignored(
        self,
        oauth_client_mock: Mock,
        get_mock: Mock,
        post_mock: Mock,
    ) -> None:
        """If ``Range`` probe is not 200/206 but plain ``GET /file`` returns 200, still treat as exists."""
        oauth = Mock()
        oauth.get_access_token.return_value = "tok-1"
        oauth_client_mock.return_value = oauth

        user_me = Mock()
        user_me.status_code = 200
        user_me.json.return_value = {"alias": "cogitomedica"}

        dir_created = Mock()
        dir_created.status_code = 201

        move_missing_src = Mock()
        move_missing_src.status_code = 404
        move_missing_src.text = "No such file or directory"

        range_weird = Mock()
        range_weird.status_code = 400

        stream_ok = Mock()
        stream_ok.status_code = 200
        stream_ok.close = Mock()

        get_mock.side_effect = [
            user_me,
            user_me,
            user_me,
            range_weird,
            stream_ok,
        ]

        def post_side_effect(url, **_kwargs):
            if "/file/move" in str(url):
                return move_missing_src
            return dir_created

        post_mock.side_effect = post_side_effect

        adapter = get_hidrive_adapter()
        adapter.move_file(
            source_path="/incoming/a.pdf",
            dest_path="/processed/a.pdf",
        )

        file_gets = [
            c
            for c in get_mock.call_args_list
            if c.args and str(c.args[0]).endswith("/file")
        ]
        self.assertEqual(len(file_gets), 2)
        self.assertTrue((file_gets[1].kwargs.get("stream")))

    @override_settings(HIDRIVE_USE_MOCK="0")
    @patch("apps.integrations.hidrive.client.requests.post")
    @patch("apps.integrations.hidrive.client.requests.get")
    @patch("apps.integrations.hidrive.client.get_hidrive_oauth_client")
    def test_real_adapter_move_file_404_idempotent_when_get_file_fails_but_dir_lists_file(
        self,
        oauth_client_mock: Mock,
        get_mock: Mock,
        post_mock: Mock,
    ) -> None:
        """HiDrive can return 404 on ``GET /file`` while ``GET /dir`` still lists the destination."""
        oauth = Mock()
        oauth.get_access_token.return_value = "tok-1"
        oauth_client_mock.return_value = oauth

        user_me = Mock()
        user_me.status_code = 200
        user_me.json.return_value = {"alias": "cogitomedica"}

        dir_created = Mock()
        dir_created.status_code = 201

        move_missing_src = Mock()
        move_missing_src.status_code = 404
        move_missing_src.text = '{"msg":"Not Found: incoming","code":"404"}'

        def get_side_effect(url, **kwargs):
            u = str(url)
            if "/user/me" in u:
                return user_me
            if "/file" in u:
                nf = Mock()
                nf.status_code = 404
                nf.text = "not found"
                nf.close = Mock()
                return nf
            if "/dir" in u:
                d = Mock()
                d.status_code = 200
                d.json.return_value = {
                    "members": [
                        {
                            "name": "a.pdf",
                            "path": "/users/cogitomedica/processed/a.pdf",
                            "size": 1,
                        }
                    ]
                }
                return d
            return user_me

        get_mock.side_effect = get_side_effect

        def post_side_effect(url, **_kwargs):
            if "/file/move" in str(url):
                return move_missing_src
            return dir_created

        post_mock.side_effect = post_side_effect

        adapter = get_hidrive_adapter()
        adapter.move_file(
            source_path="/incoming/a.pdf",
            dest_path="/processed/a.pdf",
        )

        dir_gets = [
            c for c in get_mock.call_args_list if c.args and "/dir" in str(c.args[0])
        ]
        self.assertGreaterEqual(len(dir_gets), 1)
        dir_params = dir_gets[-1].kwargs.get("params") or {}
        self.assertEqual(
            dir_params.get("path"),
            "/users/cogitomedica/processed",
        )


class HiDriveRealAdapterListDirTests(SimpleTestCase):
    @override_settings(HIDRIVE_USE_MOCK="0")
    @patch("apps.integrations.hidrive.client.get_hidrive_oauth_client")
    @patch("apps.integrations.hidrive.client.requests.get")
    @patch("apps.integrations.hidrive.client.requests.post")
    def test_real_adapter_list_dir_404_returns_empty(
        self, post_mock: Mock, get_mock: Mock, oauth_client_mock: Mock
    ) -> None:
        """Missing /dir listing (404) must not crash the doctor gate — treat as no PDFs."""
        oauth = Mock()
        oauth.get_access_token.return_value = "tok-1"
        oauth_client_mock.return_value = oauth

        user_me = Mock()
        user_me.status_code = 200
        user_me.json.return_value = {"alias": "cogitomedica"}

        dir_missing = Mock()
        dir_missing.status_code = 404

        get_mock.side_effect = [user_me, user_me, dir_missing]

        post_mock.return_value = Mock(status_code=201)

        adapter = get_hidrive_adapter()
        files = adapter.list_dir(remote_path="/incoming")

        self.assertEqual(files, [])

    @override_settings(HIDRIVE_USE_MOCK="0")
    @patch("apps.integrations.hidrive.client.get_hidrive_oauth_client")
    @patch("apps.integrations.hidrive.client.requests.get")
    @patch("apps.integrations.hidrive.client.requests.post")
    def test_real_adapter_list_dir_does_not_send_fields_param(
        self, post_mock: Mock, get_mock: Mock, oauth_client_mock: Mock
    ) -> None:
        """GET /dir must not use ``fields=`` — it can strip ``members`` from the JSON (HiDrive)."""
        oauth = Mock()
        oauth.get_access_token.return_value = "tok-1"
        oauth_client_mock.return_value = oauth

        user_me = Mock()
        user_me.status_code = 200
        user_me.json.return_value = {"alias": "cogitomedica"}

        ok_listing = Mock()
        ok_listing.status_code = 200
        ok_listing.json.return_value = {
            "members": [
                {
                    "name": "X.pdf",
                    "path": "/users/cogitomedica/incoming/X.pdf",
                    "size": 1,
                }
            ]
        }

        get_mock.side_effect = [user_me, user_me, ok_listing, user_me]
        post_mock.return_value = Mock(status_code=201)

        adapter = get_hidrive_adapter()
        files = adapter.list_dir(remote_path="/incoming")

        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]["name"], "X.pdf")
        dir_get = get_mock.call_args_list[2]
        dir_params = dir_get.kwargs.get("params") or {}
        self.assertNotIn("fields", dir_params)
        self.assertEqual(dir_params.get("members"), "file")


class HiDriveMockAdapterFileOpsTests(SimpleTestCase):
    @override_settings(HIDRIVE_USE_MOCK="1")
    def setUp(self) -> None:
        hidrive_client._MockHiDriveAdapter.reset_test_state()

    @override_settings(HIDRIVE_USE_MOCK="1")
    def test_mock_list_download_move_roundtrip(self) -> None:
        hidrive_client._MockHiDriveAdapter.seed_listing(
            "/incoming",
            [
                {
                    "name": "Kowalski_Jan.pdf",
                    "path": "/incoming/Kowalski_Jan.pdf",
                    "size": 3,
                    "mtime": None,
                }
            ],
        )
        hidrive_client._MockHiDriveAdapter.seed_file(
            "/incoming/Kowalski_Jan.pdf", b"%PDF-1.4 mock"
        )
        adapter = get_hidrive_adapter()
        files = adapter.list_dir(remote_path="/incoming")
        self.assertEqual(len(files), 1)
        data = adapter.download(remote_path="/incoming/Kowalski_Jan.pdf")
        self.assertEqual(data, b"%PDF-1.4 mock")
        adapter.move_file(
            source_path="/incoming/Kowalski_Jan.pdf",
            dest_path="/incoming/rejected_Kowalski_Jan.pdf",
        )
        files2 = adapter.list_dir(remote_path="/incoming")
        self.assertEqual(files2[0]["name"], "rejected_Kowalski_Jan.pdf")


class HiDriveMetricsTests(SimpleTestCase):
    def test_refresh_metrics_expose_attempt_and_error_labels(self) -> None:
        stats = get_hidrive_refresh_metrics()
        self.assertIn("attempt", stats)
        self.assertIn("error", stats)
