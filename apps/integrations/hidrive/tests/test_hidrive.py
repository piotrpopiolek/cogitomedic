from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from apps.integrations.hidrive.auth import (
    HiDriveAuthError,
    HiDriveOAuthClient,
    get_hidrive_refresh_metrics,
)
from apps.integrations.hidrive import client as hidrive_client
from apps.integrations.hidrive.client import (
    _parse_dir_list_response,
    _resolve_remote_target_path,
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

    def test_parse_accepts_top_level_list_payload(self) -> None:
        out = _parse_dir_list_response(
            resolved_dir_path="/users/x/incoming",
            payload=[
                {"name": "L.pdf", "path": "/users/x/incoming/L.pdf", "size": "bad"},
            ],
        )
        self.assertEqual(out[0]["name"], "L.pdf")
        self.assertEqual(out[0]["size"], 0)

    def test_parse_non_dict_payload_returns_empty(self) -> None:
        self.assertEqual(
            _parse_dir_list_response(resolved_dir_path="/users/x/incoming", payload=42),
            [],
        )

    def test_parse_reads_items_and_result_list_variants(self) -> None:
        a = _parse_dir_list_response(
            resolved_dir_path="/u/i",
            payload={"items": [{"name": "I.pdf", "size": 1}]},
        )
        self.assertEqual(a[0]["name"], "I.pdf")
        b = _parse_dir_list_response(
            resolved_dir_path="/u/i",
            payload={"result": [{"name": "R.pdf", "path": "/u/i/R.pdf"}]},
        )
        self.assertEqual(b[0]["name"], "R.pdf")
        c = _parse_dir_list_response(
            resolved_dir_path="/u/i",
            payload={"dir": {"children": [{"name": "C.pdf", "path": "/u/i/C.pdf"}]}},
        )
        self.assertEqual(c[0]["name"], "C.pdf")

    def test_parse_skips_non_dict_member_and_empty_name(self) -> None:
        out = _parse_dir_list_response(
            resolved_dir_path="/u/i",
            payload={
                "members": ["x", {"name": "", "path": "/u/i/x.pdf"}, {"name": "Z.pdf"}]
            },
        )
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["name"], "Z.pdf")


class HiDriveRealAdapterDownloadListMoveErrorTests(SimpleTestCase):
    @override_settings(HIDRIVE_USE_MOCK="0")
    @patch("apps.integrations.hidrive.client.requests.get")
    @patch("apps.integrations.hidrive.client.get_hidrive_oauth_client")
    def test_real_adapter_download_retries_on_401(
        self, oauth_client_mock: Mock, get_mock: Mock
    ) -> None:
        oauth = Mock()
        oauth.get_access_token.side_effect = ["t1", "t2"]
        oauth_client_mock.return_value = oauth
        user_me = Mock()
        user_me.status_code = 200
        user_me.json.return_value = {"alias": "cogitomedica"}
        unauthorized = Mock()
        unauthorized.status_code = 401
        ok = Mock()
        ok.status_code = 200
        ok.content = b"%PDF-1.4\n"
        get_mock.side_effect = [user_me, unauthorized, user_me, ok]
        adapter = get_hidrive_adapter()
        data = adapter.download(remote_path="/incoming/x.pdf")
        self.assertEqual(data, b"%PDF-1.4\n")

    @override_settings(HIDRIVE_USE_MOCK="0")
    @patch("apps.integrations.hidrive.client.requests.get")
    @patch("apps.integrations.hidrive.client.get_hidrive_oauth_client")
    def test_real_adapter_download_502_raises_runtime_error(
        self, oauth_client_mock: Mock, get_mock: Mock
    ) -> None:
        oauth = Mock()
        oauth.get_access_token.return_value = "t1"
        oauth_client_mock.return_value = oauth
        user_me = Mock()
        user_me.status_code = 200
        user_me.json.return_value = {"alias": "cogitomedica"}
        err = Mock()
        err.status_code = 503
        get_mock.side_effect = [user_me, err]
        adapter = get_hidrive_adapter()
        with self.assertRaises(RuntimeError):
            adapter.download(remote_path="/incoming/x.pdf")

    @override_settings(HIDRIVE_USE_MOCK="0")
    @patch("apps.integrations.hidrive.client.requests.get")
    @patch("apps.integrations.hidrive.client.get_hidrive_oauth_client")
    def test_real_adapter_download_401_after_refresh_raises_auth_error(
        self, oauth_client_mock: Mock, get_mock: Mock
    ) -> None:
        oauth = Mock()
        oauth.get_access_token.side_effect = ["t1", "t2"]
        oauth_client_mock.return_value = oauth
        user_me = Mock()
        user_me.status_code = 200
        user_me.json.return_value = {"alias": "cogitomedica"}

        def get_side_effect(url, **_kwargs):
            u = str(url)
            if "/user/me" in u:
                return user_me
            if "/file" in u:
                m = Mock()
                m.status_code = 401
                return m
            return user_me

        get_mock.side_effect = get_side_effect
        adapter = get_hidrive_adapter()
        with self.assertRaises(HiDriveAuthError):
            adapter.download(remote_path="/incoming/x.pdf")

    @override_settings(HIDRIVE_USE_MOCK="0")
    @patch("apps.integrations.hidrive.client.requests.get")
    @patch("apps.integrations.hidrive.client.get_hidrive_oauth_client")
    def test_real_adapter_list_dir_retries_on_401_then_lists(
        self, oauth_client_mock: Mock, get_mock: Mock
    ) -> None:
        oauth = Mock()
        oauth.get_access_token.side_effect = ["t1", "t2"]
        oauth_client_mock.return_value = oauth
        user_me = Mock()
        user_me.status_code = 200
        user_me.json.return_value = {"alias": "cogitomedica"}
        list_unauth = Mock()
        list_unauth.status_code = 401
        list_ok = Mock()
        list_ok.status_code = 200
        list_ok.json.return_value = {"members": []}
        list_calls: list[str] = []

        def get_side_effect(url, **_kwargs):
            u = str(url)
            if "/user/me" in u:
                return user_me
            if "/dir" in u:
                list_calls.append("dir")
                return list_unauth if len(list_calls) == 1 else list_ok
            return user_me

        get_mock.side_effect = get_side_effect
        post_mock = Mock(return_value=Mock(status_code=201))
        with patch("apps.integrations.hidrive.client.requests.post", post_mock):
            adapter = get_hidrive_adapter()
            files = adapter.list_dir(remote_path="/incoming")
        self.assertEqual(files, [])
        post_mock.assert_not_called()

    @override_settings(HIDRIVE_USE_MOCK="0")
    @patch("apps.integrations.hidrive.client.requests.get")
    @patch("apps.integrations.hidrive.client.get_hidrive_oauth_client")
    def test_real_adapter_list_dir_503_raises(
        self, oauth_client_mock: Mock, get_mock: Mock
    ) -> None:
        oauth = Mock()
        oauth.get_access_token.return_value = "t1"
        oauth_client_mock.return_value = oauth
        user_me = Mock()
        user_me.status_code = 200
        user_me.json.return_value = {"alias": "cogitomedica"}
        boom = Mock()
        boom.status_code = 503
        get_mock.side_effect = [user_me, boom]
        post_mock = Mock(return_value=Mock(status_code=201))
        with patch("apps.integrations.hidrive.client.requests.post", post_mock):
            adapter = get_hidrive_adapter()
            with self.assertRaises(RuntimeError):
                adapter.list_dir(remote_path="/incoming")
        post_mock.assert_not_called()

    @override_settings(HIDRIVE_USE_MOCK="0")
    @patch("apps.integrations.hidrive.client.requests.post")
    @patch("apps.integrations.hidrive.client.requests.get")
    @patch("apps.integrations.hidrive.client.get_hidrive_oauth_client")
    def test_real_adapter_move_502_raises(
        self, oauth_client_mock: Mock, get_mock: Mock, post_mock: Mock
    ) -> None:
        oauth = Mock()
        oauth.get_access_token.return_value = "t1"
        oauth_client_mock.return_value = oauth
        user_me = Mock()
        user_me.status_code = 200
        user_me.json.return_value = {"alias": "cogitomedica"}
        dir_ok = Mock()
        dir_ok.status_code = 201
        move_err = Mock()
        move_err.status_code = 502
        get_mock.return_value = user_me

        def post_side_effect(url, **_kwargs):
            return move_err if "/file/move" in str(url) else dir_ok

        post_mock.side_effect = post_side_effect
        adapter = get_hidrive_adapter()
        with self.assertRaises(RuntimeError):
            adapter.move_file(
                source_path="/incoming/a.pdf",
                dest_path="/processed/a.pdf",
            )


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


class HiDriveRealAdapterDownloadParamsEncodingTests(SimpleTestCase):
    """§12: logical paths with spaces are passed as ``params`` (requests encodes the URL)."""

    @override_settings(HIDRIVE_USE_MOCK="0")
    @patch("apps.integrations.hidrive.client.requests.get")
    @patch("apps.integrations.hidrive.client.get_hidrive_oauth_client")
    @patch("apps.integrations.hidrive.client._resolve_remote_target_path")
    def test_download_get_file_passes_space_in_resolved_path_as_param(
        self, resolve_mock: Mock, oauth_client_mock: Mock, get_mock: Mock
    ) -> None:
        oauth = Mock()
        oauth.get_access_token.return_value = "tok-1"
        oauth_client_mock.return_value = oauth

        ok_file = Mock()
        ok_file.status_code = 200
        ok_file.content = b"%PDF-1.4\n"

        resolve_mock.return_value = "/users/cogitomedica/incoming/Kowalski Jan.pdf"
        get_mock.return_value = ok_file

        adapter = get_hidrive_adapter()
        adapter.download(remote_path="/incoming/Kowalski Jan.pdf")

        file_calls = [
            c
            for c in get_mock.call_args_list
            if c.args and str(c.args[0]).endswith("/file")
        ]
        self.assertGreaterEqual(len(file_calls), 1)
        self.assertEqual(
            file_calls[0].kwargs["params"]["path"],
            "/users/cogitomedica/incoming/Kowalski Jan.pdf",
        )

    @override_settings(HIDRIVE_USE_MOCK="0")
    @patch("apps.integrations.hidrive.client.requests.post")
    @patch("apps.integrations.hidrive.client.requests.get")
    @patch("apps.integrations.hidrive.client.get_hidrive_oauth_client")
    @patch("apps.integrations.hidrive.client._resolve_remote_target_path")
    def test_move_file_post_passes_space_in_src_dst_params(
        self,
        resolve_mock: Mock,
        oauth_client_mock: Mock,
        get_mock: Mock,
        post_mock: Mock,
    ) -> None:
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

        def resolve_side_effect(**kwargs: object) -> str:
            rp = str(kwargs.get("remote_path") or "")
            if "rejected" in rp:
                return "/users/cogitomedica/incoming/rejected_Kowalski Jan.pdf"
            if rp.startswith("/processed"):
                return "/users/cogitomedica/processed/Kowalski Jan.pdf"
            return "/users/cogitomedica/incoming/Kowalski Jan.pdf"

        resolve_mock.side_effect = resolve_side_effect

        get_mock.return_value = user_me

        def post_side_effect(url, **_kwargs):
            if "/file/move" in str(url):
                return move_ok
            return dir_created

        post_mock.side_effect = post_side_effect

        adapter = get_hidrive_adapter()
        adapter.move_file(
            source_path="/incoming/Kowalski Jan.pdf",
            dest_path="/incoming/rejected_Kowalski Jan.pdf",
        )

        move_calls = [
            c
            for c in post_mock.call_args_list
            if c.args and "/file/move" in str(c.args[0])
        ]
        self.assertEqual(len(move_calls), 1)
        params = move_calls[0].kwargs.get("params") or {}
        self.assertEqual(params["src"], "/users/cogitomedica/incoming/Kowalski Jan.pdf")
        self.assertEqual(
            params["dst"], "/users/cogitomedica/incoming/rejected_Kowalski Jan.pdf"
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

        # One ``user/me`` before ``GET /dir`` (no extra resolve at start of ``list_dir``).
        get_mock.side_effect = [user_me, dir_missing]

        post_mock.return_value = Mock(status_code=201)

        adapter = get_hidrive_adapter()
        files = adapter.list_dir(remote_path="/incoming")

        self.assertEqual(files, [])
        post_mock.assert_not_called()

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

        get_mock.side_effect = [user_me, ok_listing, user_me]
        post_mock.return_value = Mock(status_code=201)

        adapter = get_hidrive_adapter()
        files = adapter.list_dir(remote_path="/incoming")

        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]["name"], "X.pdf")
        dir_get = get_mock.call_args_list[1]
        dir_params = dir_get.kwargs.get("params") or {}
        self.assertNotIn("fields", dir_params)
        self.assertEqual(dir_params.get("members"), "file")
        post_mock.assert_not_called()


class HiDriveMockAdapterFileOpsTests(SimpleTestCase):
    @override_settings(HIDRIVE_USE_MOCK="1")
    def setUp(self) -> None:
        hidrive_client._MockHiDriveAdapter.reset_test_state()

    @override_settings(HIDRIVE_USE_MOCK="1")
    def test_mock_download_raises_when_file_not_seeded(self) -> None:
        adapter = get_hidrive_adapter()
        with self.assertRaises(FileNotFoundError):
            adapter.download(remote_path="/incoming/missing.pdf")

    @override_settings(HIDRIVE_USE_MOCK="1")
    def test_mock_upload_seeds_bytes_when_local_file_exists(self) -> None:
        adapter = get_hidrive_adapter()
        tmp = Path("hidrive_mock_upload_test.bin")
        tmp.write_bytes(b"seeded-bytes")
        self.addCleanup(lambda: tmp.unlink(missing_ok=True))
        adapter.upload(remote_path="/incoming/uploaded.bin", local_path=tmp)
        self.assertEqual(
            adapter.download(remote_path="/incoming/uploaded.bin"),
            b"seeded-bytes",
        )

    @override_settings(HIDRIVE_USE_MOCK="1")
    def test_mock_move_updates_only_matching_listing_row(self) -> None:
        hidrive_client._MockHiDriveAdapter.seed_listing(
            "/incoming",
            [
                {
                    "name": "a.pdf",
                    "path": "/incoming/a.pdf",
                    "size": 1,
                    "mtime": None,
                },
                {
                    "name": "b.pdf",
                    "path": "/incoming/b.pdf",
                    "size": 2,
                    "mtime": None,
                },
            ],
        )
        hidrive_client._MockHiDriveAdapter.seed_file("/incoming/a.pdf", b"aa")
        hidrive_client._MockHiDriveAdapter.seed_file("/incoming/b.pdf", b"bb")
        adapter = get_hidrive_adapter()
        adapter.move_file(
            source_path="/incoming/a.pdf",
            dest_path="/incoming/moved_a.pdf",
        )
        rows = adapter.list_dir(remote_path="/incoming")
        names = {r["name"] for r in rows}
        self.assertIn("moved_a.pdf", names)
        self.assertIn("b.pdf", names)

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


class HiDriveResolvePathTests(SimpleTestCase):
    @override_settings(HIDRIVE_USERS_ROOT_PREFIX="/users/teamspace")
    def test_resolve_appends_logical_path_to_users_root_prefix(self) -> None:
        out = _resolve_remote_target_path(
            base_url="https://api.hidrive.strato.com/2.1",
            access_token="ignored",
            remote_path="/patients/u/f.pdf",
        )
        self.assertEqual(out, "/users/teamspace/patients/u/f.pdf")

    @override_settings(HIDRIVE_USERS_ROOT_PREFIX="/users/teamspace/")
    def test_resolve_trims_trailing_slash_on_prefix(self) -> None:
        out = _resolve_remote_target_path(
            base_url="https://api.hidrive.strato.com/2.1",
            access_token="ignored",
            remote_path="/incoming/x.pdf",
        )
        self.assertEqual(out, "/users/teamspace/incoming/x.pdf")

    def test_resolve_absolute_users_path_unchanged(self) -> None:
        out = _resolve_remote_target_path(
            base_url="https://api.hidrive.strato.com/2.1",
            access_token="ignored",
            remote_path="/users/other/incoming/x.pdf",
        )
        self.assertEqual(out, "/users/other/incoming/x.pdf")

    def test_resolve_absolute_public_path_unchanged(self) -> None:
        """Paths starting with /public/ target the Common (shared) space — no /users/<alias> prepend."""
        out = _resolve_remote_target_path(
            base_url="https://api.hidrive.strato.com/2.1",
            access_token="ignored",
            remote_path="/public/incoming/x.pdf",
        )
        self.assertEqual(out, "/public/incoming/x.pdf")

    def test_resolve_public_patients_path_unchanged(self) -> None:
        out = _resolve_remote_target_path(
            base_url="https://api.hidrive.strato.com/2.1",
            access_token="ignored",
            remote_path="/public/patients/some-uuid/Befund_v1.pdf",
        )
        self.assertEqual(out, "/public/patients/some-uuid/Befund_v1.pdf")

    @override_settings(HIDRIVE_USERS_ROOT_PREFIX="/public/shared")
    def test_resolve_public_root_prefix(self) -> None:
        out = _resolve_remote_target_path(
            base_url="https://api.hidrive.strato.com/2.1",
            access_token="ignored",
            remote_path="/incoming/x.pdf",
        )
        self.assertEqual(out, "/public/shared/incoming/x.pdf")

    @override_settings(HIDRIVE_USERS_ROOT_PREFIX="/public")
    def test_resolve_public_bare_prefix_maps_to_common(self) -> None:
        """HIDRIVE_USERS_ROOT_PREFIX=/public maps relative paths into the Common space."""
        out = _resolve_remote_target_path(
            base_url="https://api.hidrive.strato.com/2.1",
            access_token="ignored",
            remote_path="/incoming/x.pdf",
        )
        self.assertEqual(out, "/public/incoming/x.pdf")

    @override_settings(HIDRIVE_USERS_ROOT_PREFIX="bad")
    def test_resolve_invalid_prefix_raises(self) -> None:
        with self.assertRaises(ValueError):
            _resolve_remote_target_path(
                base_url="https://api.hidrive.strato.com/2.1",
                access_token="ignored",
                remote_path="/incoming/x.pdf",
            )


class HiDriveMetricsTests(SimpleTestCase):
    def test_refresh_metrics_expose_attempt_and_error_labels(self) -> None:
        stats = get_hidrive_refresh_metrics()
        self.assertIn("attempt", stats)
        self.assertIn("error", stats)
