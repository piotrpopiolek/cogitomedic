"""HiDrive upload adapter (real + mock)."""

from __future__ import annotations

import logging
import time
from pathlib import Path, PurePosixPath
from typing import Any, ClassVar, Protocol

import requests
from django.conf import settings

from apps.integrations.hidrive.auth import HiDriveAuthError, get_hidrive_oauth_client

logger = logging.getLogger(__name__)


class HiDriveApiError(RuntimeError):
    """HiDrive HTTP failure, invalid JSON body, or other API contract error (non-OAuth)."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class HiDriveTimeoutError(HiDriveApiError):
    """HiDrive listing or request exceeded a configured time budget."""


def _response_json(response: requests.Response) -> Any:
    try:
        return response.json()
    except ValueError as exc:
        raise HiDriveApiError(
            "HiDrive response body is not valid JSON",
            status_code=response.status_code,
        ) from exc


class HiDriveAdapterProtocol(Protocol):
    """Protocol for HiDrive uploads and file operations."""

    def upload(self, *, remote_path: str, local_path: Path) -> None:
        """Upload local file to remote HiDrive path."""
        ...

    def download(self, *, remote_path: str) -> bytes:
        """Download remote file and return raw bytes."""
        ...

    def list_dir(
        self,
        *,
        remote_path: str,
        timeout_seconds: float | None = None,
        total_timeout_seconds: float | None = None,
    ) -> list[dict[str, Any]]:
        """List files in a remote directory (not subfolders)."""
        ...

    def move_file(self, *, source_path: str, dest_path: str) -> None:
        """Move a remote file (POST ``/file/move``; not ``PATCH /file``, which is for partial content)."""
        ...


class _MockHiDriveAdapter:
    """Mock adapter – no outgoing HTTP.

    ``_dir_listings`` maps logical remote directory paths to file entries:
    each entry is ``{"name": str, "path": str, "size": int, "mtime": str|None}``.
    ``_file_contents`` maps logical file ``path`` to bytes for ``download``.

    When ``settings.HIDRIVE_MOCK_STATE_PATH`` is set, state is also persisted to that
    JSON file so a separate ``web`` process (Docker) can see seeds written by demo
    scripts. ``list_dir_error`` forces ``HiDriveTimeoutError`` (dashboard outage banner).
    """

    _dir_listings: ClassVar[dict[str, list[dict[str, Any]]]] = {}
    _file_contents: ClassVar[dict[str, bytes]] = {}
    _list_dir_error: ClassVar[str | None] = None
    _state_mtime_ns: ClassVar[int | None] = None

    @classmethod
    def _state_path(cls) -> Path | None:
        raw = str(getattr(settings, "HIDRIVE_MOCK_STATE_PATH", "") or "").strip()
        if not raw:
            return None
        return Path(raw)

    @classmethod
    def _load_state_from_disk(cls) -> None:
        """Reload mock state from the shared JSON file.

        Always re-reads when the file exists. Docker Desktop on Windows often
        keeps coarse ``mtime`` (1s), so a mtime short-circuit would miss
        mid-recording updates from the host Playwright process.
        """
        import base64
        import json

        path = cls._state_path()
        if path is None or not path.is_file():
            return
        try:
            raw = path.read_text(encoding="utf-8")
            mtime_ns = path.stat().st_mtime_ns
        except OSError:
            return
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            return
        listings = data.get("listings") or {}
        cls._dir_listings = {
            str(k): [dict(e) for e in (v or [])] for k, v in listings.items()
        }
        files_b64 = data.get("files_b64") or {}
        decoded: dict[str, bytes] = {}
        for k, v in files_b64.items():
            try:
                decoded[str(k)] = base64.b64decode(v)
            except (ValueError, TypeError):
                continue
        cls._file_contents = decoded
        err = data.get("list_dir_error")
        cls._list_dir_error = str(err) if err else None
        cls._state_mtime_ns = mtime_ns

    @classmethod
    def _persist_state(cls) -> None:
        import base64
        import json

        path = cls._state_path()
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "listings": cls._dir_listings,
                "files_b64": {
                    k: base64.b64encode(v).decode("ascii")
                    for k, v in cls._file_contents.items()
                },
                "list_dir_error": cls._list_dir_error,
            }
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            cls._state_mtime_ns = path.stat().st_mtime_ns
        except OSError:
            logger.warning(
                "[MOCK HIDRIVE] could not persist state to %s", path, exc_info=True
            )

    @classmethod
    def reset_test_state(cls) -> None:
        cls._dir_listings.clear()
        cls._file_contents.clear()
        cls._list_dir_error = None
        cls._state_mtime_ns = None
        path = cls._state_path()
        if path is not None and path.is_file():
            try:
                path.unlink()
            except OSError:
                cls._persist_state()

    @classmethod
    def seed_listing(cls, remote_dir: str, files: list[dict[str, Any]]) -> None:
        """Register mock directory listing (tests / demo)."""
        cls._load_state_from_disk()
        norm = _normalize_remote_path(remote_dir)
        cls._dir_listings[norm] = list(files)
        cls._list_dir_error = None
        cls._persist_state()

    @classmethod
    def seed_file(cls, remote_file: str, content: bytes) -> None:
        """Register mock file bytes (tests / demo)."""
        cls._load_state_from_disk()
        norm = _normalize_remote_path(remote_file)
        cls._file_contents[norm] = content
        cls._persist_state()

    @classmethod
    def seed_list_dir_error(cls, message: str | None) -> None:
        """Force ``list_dir`` to raise ``HiDriveTimeoutError`` (demo SC-027)."""
        cls._load_state_from_disk()
        cls._list_dir_error = (message or "").strip() or None
        cls._persist_state()

    def upload(self, *, remote_path: str, local_path: Path) -> None:
        self._load_state_from_disk()
        logger.info(
            "[MOCK HIDRIVE] upload path=%s local=%s — not sent to cloud; set HIDRIVE_USE_MOCK=0 + OAuth to use real HiDrive",
            remote_path,
            str(local_path),
        )
        norm = _normalize_remote_path(remote_path)
        if local_path.exists() and local_path.is_file():
            self._file_contents[norm] = local_path.read_bytes()
            self._persist_state()

    def download(self, *, remote_path: str) -> bytes:
        self._load_state_from_disk()
        norm = _normalize_remote_path(remote_path)
        logger.info("[MOCK HIDRIVE] download path=%s", norm)
        if norm not in self._file_contents:
            raise FileNotFoundError(f"[MOCK HIDRIVE] no file seeded for {norm}")
        return self._file_contents[norm]

    def list_dir(
        self,
        *,
        remote_path: str,
        timeout_seconds: float | None = None,
        total_timeout_seconds: float | None = None,
    ) -> list[dict[str, Any]]:
        del timeout_seconds, total_timeout_seconds
        self._load_state_from_disk()
        if self._list_dir_error:
            raise HiDriveTimeoutError(self._list_dir_error)
        norm = _normalize_remote_path(remote_path)
        logger.info("[MOCK HIDRIVE] list_dir path=%s", norm)
        return list(self._dir_listings.get(norm, []))

    def move_file(self, *, source_path: str, dest_path: str) -> None:
        self._load_state_from_disk()
        src = _normalize_remote_path(source_path)
        dst = _normalize_remote_path(dest_path)
        logger.info("[MOCK HIDRIVE] move_file %s -> %s", src, dst)
        data = self._file_contents.pop(src, None)
        if data is not None:
            self._file_contents[dst] = data
        for dir_path, entries in list(self._dir_listings.items()):
            changed = False
            new_entries: list[dict[str, Any]] = []
            for e in entries:
                ep = str(e.get("path") or "")
                if ep == src:
                    name = PurePosixPath(dst).name
                    new_entries.append(
                        {
                            **e,
                            "name": name,
                            "path": dst,
                        }
                    )
                    changed = True
                else:
                    new_entries.append(e)
            if changed:
                self._dir_listings[dir_path] = new_entries
        self._persist_state()


class _HiDriveAdapter:
    """Real HiDrive HTTP adapter."""

    def upload(self, *, remote_path: str, local_path: Path) -> None:
        if not local_path.exists() or not local_path.is_file():
            raise FileNotFoundError(f"HiDrive local file does not exist: {local_path}")

        oauth_client = get_hidrive_oauth_client()
        access_token = oauth_client.get_access_token()
        response = self._upload_once(
            access_token=access_token,
            remote_path=remote_path,
            local_path=local_path,
        )
        if response.status_code == 401:
            access_token = oauth_client.get_access_token(force_refresh=True)
            response = self._upload_once(
                access_token=access_token,
                remote_path=remote_path,
                local_path=local_path,
            )

        dbg_base = _hidrive_base_url()
        dbg_resolved = ""
        try:
            dbg_resolved = _resolve_remote_target_path(
                base_url=dbg_base,
                access_token=access_token,
                remote_path=remote_path,
            )
        except Exception as res_exc:
            dbg_resolved = f"<resolve_failed:{type(res_exc).__name__}>"
        if response.status_code in (200, 201, 204):
            logger.info(
                "HiDrive upload OK status=%s logical=%s api_path=%s",
                response.status_code,
                remote_path,
                dbg_resolved,
            )
            return
        if response.status_code >= 500:
            raise HiDriveApiError(
                f"HiDrive upload failed with status {response.status_code}",
                status_code=response.status_code,
            )
        if response.status_code == 401:
            raise HiDriveAuthError("HiDrive upload unauthorized after token refresh")
        err_snip = (response.text or "")[:160].replace("\n", " ")
        logger.warning(
            "HiDrive upload rejected status=%s logical=%s api_path=%s snippet=%s",
            response.status_code,
            remote_path,
            dbg_resolved,
            err_snip,
        )
        raise HiDriveApiError(
            f"HiDrive upload rejected with status {response.status_code}",
            status_code=response.status_code,
        )

    def _upload_once(
        self, *, access_token: str, remote_path: str, local_path: Path
    ) -> requests.Response:
        base_url = _hidrive_base_url()
        url = f"{base_url}/file"
        dir_path, file_name = _split_remote_path(
            _resolve_remote_target_path(
                base_url=base_url,
                access_token=access_token,
                remote_path=remote_path,
            )
        )
        _ensure_remote_directories(
            base_url=base_url, access_token=access_token, dir_path=dir_path
        )
        params = {
            "dir": dir_path,
            "name": file_name,
        }
        timeout = int(getattr(settings, "HIDRIVE_TIMEOUT_SECONDS", 30))
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/octet-stream",
        }
        with local_path.open("rb") as file_stream:
            response = requests.put(
                url,
                params=params,
                data=file_stream,
                headers=headers,
                timeout=timeout,
            )
        return response

    def download(self, *, remote_path: str) -> bytes:
        oauth_client = get_hidrive_oauth_client()
        access_token = oauth_client.get_access_token()
        response = self._download_once(
            access_token=access_token, remote_path=remote_path
        )
        if response.status_code == 401:
            access_token = oauth_client.get_access_token(force_refresh=True)
            response = self._download_once(
                access_token=access_token, remote_path=remote_path
            )
        if response.status_code == 200:
            return bytes(response.content or b"")
        if response.status_code >= 500:
            raise HiDriveApiError(
                f"HiDrive download failed with status {response.status_code}",
                status_code=response.status_code,
            )
        if response.status_code == 401:
            raise HiDriveAuthError("HiDrive download unauthorized after token refresh")
        raise HiDriveApiError(
            f"HiDrive download rejected with status {response.status_code}",
            status_code=response.status_code,
        )

    def _download_once(
        self, *, access_token: str, remote_path: str
    ) -> requests.Response:
        base_url = _hidrive_base_url()
        resolved = _resolve_remote_target_path(
            base_url=base_url,
            access_token=access_token,
            remote_path=remote_path,
        )
        timeout = int(getattr(settings, "HIDRIVE_TIMEOUT_SECONDS", 30))
        return requests.get(
            f"{base_url}/file",
            params={"path": resolved},
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=timeout,
        )

    def list_dir(
        self,
        *,
        remote_path: str,
        timeout_seconds: float | None = None,
        total_timeout_seconds: float | None = None,
    ) -> list[dict[str, Any]]:
        oauth_client = get_hidrive_oauth_client()
        access_token = oauth_client.get_access_token()
        page_size = int(getattr(settings, "HIDRIVE_LIST_DIR_PAGE_SIZE", 500))
        max_pages = int(getattr(settings, "HIDRIVE_LIST_DIR_MAX_PAGES", 50))
        default_timeout = float(getattr(settings, "HIDRIVE_TIMEOUT_SECONDS", 30))
        per_request_cap = float(
            timeout_seconds if timeout_seconds is not None else default_timeout
        )
        deadline: float | None = None
        if total_timeout_seconds is not None:
            deadline = time.monotonic() + float(total_timeout_seconds)
            page_cap = float(
                getattr(settings, "HIDRIVE_DASHBOARD_PAGE_TIMEOUT_SECONDS", 5)
            )
            per_request_cap = min(per_request_cap, page_cap)

        # Intentionally no ``POST /dir`` before listing: read-only (no mkdir side effects
        # on e.g. /incoming when the folder is missing or not configured yet).
        all_rows: list[dict[str, Any]] = []
        offset = 0
        pages_fetched = 0
        last_page_len = 0
        base_url = _hidrive_base_url()

        while pages_fetched < max_pages:
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise HiDriveTimeoutError(
                        f"HiDrive list_dir timed out for {remote_path} "
                        f"after {pages_fetched} page(s)",
                    )
                request_timeout = min(remaining, per_request_cap)
            else:
                request_timeout = per_request_cap

            response = self._list_dir_once(
                access_token=access_token,
                remote_path=remote_path,
                offset=offset,
                page_size=page_size,
                timeout=request_timeout,
            )
            if response.status_code == 401:
                access_token = oauth_client.get_access_token(force_refresh=True)
                response = self._list_dir_once(
                    access_token=access_token,
                    remote_path=remote_path,
                    offset=offset,
                    page_size=page_size,
                    timeout=request_timeout,
                )
            if response.status_code == 200:
                resolved_for_parse = _resolve_remote_target_path(
                    base_url=base_url,
                    access_token=access_token,
                    remote_path=remote_path,
                )
                payload = _response_json(response)
                page_rows = _parse_dir_list_response(
                    resolved_dir_path=resolved_for_parse,
                    payload=payload,
                )
                all_rows.extend(page_rows)
                pages_fetched += 1
                last_page_len = len(page_rows)
                if last_page_len < page_size:
                    break
                offset += last_page_len
                continue
            if response.status_code == 404 and offset == 0:
                logger.info(
                    "HiDrive list_dir returned 404 for %s — treating as empty directory",
                    remote_path,
                )
                return []
            if response.status_code >= 500:
                raise HiDriveApiError(
                    f"HiDrive list_dir failed with status {response.status_code}",
                    status_code=response.status_code,
                )
            if response.status_code == 401:
                raise HiDriveAuthError(
                    "HiDrive list_dir unauthorized after token refresh"
                )
            raise HiDriveApiError(
                f"HiDrive list_dir rejected with status {response.status_code}",
                status_code=response.status_code,
            )

        if pages_fetched >= max_pages and last_page_len >= page_size:
            raise HiDriveApiError(
                f"HiDrive list_dir exceeded max pages ({max_pages}) for {remote_path}",
            )

        logger.info(
            "HiDrive list_dir path=%s pages=%s total_entries=%s",
            remote_path,
            pages_fetched,
            len(all_rows),
        )
        return all_rows

    def _list_dir_once(
        self,
        *,
        access_token: str,
        remote_path: str,
        offset: int = 0,
        page_size: int | None = None,
        timeout: float | None = None,
    ) -> requests.Response:
        base_url = _hidrive_base_url()
        resolved = _resolve_remote_target_path(
            base_url=base_url,
            access_token=access_token,
            remote_path=remote_path,
        )
        request_timeout = float(
            timeout
            if timeout is not None
            else getattr(settings, "HIDRIVE_TIMEOUT_SECONDS", 30)
        )
        headers = {"Authorization": f"Bearer {access_token}"}
        url = f"{base_url}/dir"
        base_params: dict[str, str] = {"path": resolved, "members": "file"}
        if page_size is not None:
            base_params["limit"] = (
                str(page_size) if offset <= 0 else f"{offset},{page_size}"
            )
        # Omit ``fields=`` on GET /dir: HiDrive can return 200 with only the directory node
        # (``name``, ``path``, …) and **no** ``members`` array, so the listing would be empty.
        return requests.get(
            url, params=base_params, headers=headers, timeout=request_timeout
        )

    def move_file(self, *, source_path: str, dest_path: str) -> None:
        oauth_client = get_hidrive_oauth_client()
        access_token = oauth_client.get_access_token()
        response = self._move_file_once(
            access_token=access_token,
            source_path=source_path,
            dest_path=dest_path,
        )
        if response.status_code == 401:
            access_token = oauth_client.get_access_token(force_refresh=True)
            response = self._move_file_once(
                access_token=access_token,
                source_path=source_path,
                dest_path=dest_path,
            )
        if response.status_code in (200, 201, 204):
            return
        if response.status_code == 404:
            base_url = _hidrive_base_url()
            dst_resolved = _resolve_remote_target_path(
                base_url=base_url,
                access_token=access_token,
                remote_path=dest_path,
            )
            via_file = self._remote_file_exists_probe(
                access_token=access_token, resolved_path=dst_resolved
            )
            via_listing = False
            if not via_file:
                # HiDrive may omit or reject ``GET /file`` for an object that still appears in ``GET /dir``.
                via_listing = self._remote_dest_exists_by_dir_listing(
                    access_token=access_token,
                    dest_logical_path=dest_path,
                    dst_resolved=dst_resolved,
                )
            if via_file or via_listing:
                logger.info(
                    "HiDrive move_file: move returned 404 but destination exists — "
                    "treating as idempotent success (e.g. outbox retry after source already moved)"
                )
                return
        if response.status_code >= 500:
            raise HiDriveApiError(
                f"HiDrive move_file failed with status {response.status_code}",
                status_code=response.status_code,
            )
        if response.status_code == 401:
            raise HiDriveAuthError("HiDrive move_file unauthorized after token refresh")
        raise HiDriveApiError(
            f"HiDrive move_file rejected with status {response.status_code}",
            status_code=response.status_code,
        )

    def _move_file_once(
        self,
        *,
        access_token: str,
        source_path: str,
        dest_path: str,
    ) -> requests.Response:
        base_url = _hidrive_base_url()
        src_resolved = _resolve_remote_target_path(
            base_url=base_url,
            access_token=access_token,
            remote_path=source_path,
        )
        dst_resolved = _resolve_remote_target_path(
            base_url=base_url,
            access_token=access_token,
            remote_path=dest_path,
        )
        dest_dir_path, _ = _split_remote_path(dst_resolved)
        _ensure_remote_directories(
            base_url=base_url,
            access_token=access_token,
            dir_path=dest_dir_path,
        )
        timeout = int(getattr(settings, "HIDRIVE_TIMEOUT_SECONDS", 30))
        # HiDrive: ``PATCH /file`` requires ``offset`` (partial binary write). Moves use ``POST /file/move``.
        return requests.post(
            f"{base_url}/file/move",
            params={
                "src": src_resolved,
                "dst": dst_resolved,
                # Same lab filename can already exist in /processed/ after a prior publish.
                "on_exist": "overwrite",
            },
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=timeout,
        )

    def _remote_file_exists_probe(
        self, *, access_token: str, resolved_path: str
    ) -> bool:
        """True if ``GET /file`` finds the object (minimal byte range to avoid full PDF download)."""
        base_url = _hidrive_base_url()
        timeout = int(getattr(settings, "HIDRIVE_TIMEOUT_SECONDS", 30))
        r = requests.get(
            f"{base_url}/file",
            params={"path": resolved_path},
            headers={
                "Authorization": f"Bearer {access_token}",
                "Range": "bytes=0-0",
            },
            timeout=timeout,
        )
        if r.status_code in (200, 206):
            return True
        # HiDrive may ignore or reject ``Range``; stream without reading body to avoid full download.
        r2 = requests.get(
            f"{base_url}/file",
            params={"path": resolved_path},
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=timeout,
            stream=True,
        )
        try:
            if r2.status_code == 200:
                return True
        finally:
            r2.close()
        return False

    def _remote_dest_exists_by_dir_listing(
        self, *, access_token: str, dest_logical_path: str, dst_resolved: str
    ) -> bool:
        """True if ``GET /dir`` on the destination parent lists a file matching ``dest``."""
        base_url = _hidrive_base_url()
        normalized = _normalize_remote_path(dest_logical_path)
        dest_pp = PurePosixPath(normalized)
        file_name = dest_pp.name
        if not file_name:
            return False
        parent = str(dest_pp.parent)
        if parent in ("", ".", "/"):
            parent = "/"
        resp = self._list_dir_once(access_token=access_token, remote_path=parent)
        if resp.status_code != 200:
            return False
        resolved_dir = _resolve_remote_target_path(
            base_url=base_url,
            access_token=access_token,
            remote_path=parent,
        )
        rows = _parse_dir_list_response(
            resolved_dir_path=resolved_dir,
            payload=_response_json(resp),
        )
        want = file_name.lower()
        dst_norm = dst_resolved.rstrip("/")
        for row in rows:
            name = str(row.get("name") or "").strip()
            path = str(row.get("path") or "").strip()
            if name.lower() == want:
                return True
            if path and PurePosixPath(path).name.lower() == want:
                return True
            if path.rstrip("/") == dst_norm:
                return True
        return False


def _hidrive_base_url() -> str:
    return str(
        getattr(settings, "HIDRIVE_API_BASE_URL", "https://api.hidrive.strato.com/2.1")
    ).rstrip("/")


def _extract_dir_member_rows(payload: Any) -> list[Any]:
    """HiDrive ``GET /dir`` bodies vary: top-level ``members``, nested ``result.members``, etc."""
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ("members", "items", "files", "children"):
        val = payload.get(key)
        if isinstance(val, list):
            return val
    res = payload.get("result")
    if isinstance(res, list):
        return res
    if isinstance(res, dict):
        for key in ("members", "items", "files", "children"):
            val = res.get(key)
            if isinstance(val, list):
                return val
    dir_obj = payload.get("dir")
    if isinstance(dir_obj, dict):
        for key in ("members", "items", "files", "children"):
            val = dir_obj.get(key)
            if isinstance(val, list):
                return val
    return []


def _parse_dir_list_response(
    *,
    resolved_dir_path: str,
    payload: Any,
) -> list[dict[str, Any]]:
    """Normalize HiDrive /dir JSON to a list of file dicts with name, path, size, mtime."""
    raw_members = _extract_dir_member_rows(payload)
    base = (
        str(PurePosixPath((resolved_dir_path or "").strip().rstrip("/") or "/")).rstrip(
            "/"
        )
        or "/"
    )
    out: list[dict[str, Any]] = []
    for item in raw_members:
        if not isinstance(item, dict):
            continue
        nested = item.get("file")
        if isinstance(nested, dict):
            merged = {**nested}
            for k, v in item.items():
                if k != "file" and k not in merged:
                    merged[k] = v
            item = merged
        raw_name = str(
            item.get("name") or item.get("filename") or item.get("basename") or ""
        ).strip()
        if not raw_name:
            continue
        name = raw_name
        path_val = str(item.get("path") or "").strip()
        if not path_val:
            path_val = f"{base}/{name}"
        mime = str(
            item.get("mime")
            or item.get("mimetype")
            or item.get("content_type")
            or item.get("contentType")
            or ""
        ).lower()
        basename = PurePosixPath(path_val).name or name
        if (
            not basename.lower().endswith(".pdf")
            and "pdf" in mime
            and basename.count(".") == 0
        ):
            basename_pdf = f"{basename}.pdf"
            name = basename_pdf
            parent = PurePosixPath(path_val).parent
            parent_s = str(parent)
            if parent_s in ("", ".", "/") or not str(item.get("path") or "").strip():
                path_val = f"{base}/{basename_pdf}"
            else:
                path_val = str(parent / basename_pdf)
        size = item.get("size")
        try:
            size_int = int(size) if size is not None else 0
        except (TypeError, ValueError):
            size_int = 0
        mtime = item.get("mtime")
        out.append(
            {
                "name": name,
                "path": path_val,
                "size": size_int,
                "mtime": mtime if mtime is None else str(mtime),
            }
        )
    return out


def _normalize_remote_path(remote_path: str) -> str:
    normalized = (remote_path or "").strip()
    if not normalized:
        raise ValueError("HiDrive remote path must not be empty")
    if not normalized.startswith("/"):
        normalized = "/" + normalized
    return normalized


def _split_remote_path(remote_path: str) -> tuple[str, str]:
    normalized = _normalize_remote_path(remote_path)
    p = PurePosixPath(normalized)
    file_name = p.name
    if not file_name:
        raise ValueError("HiDrive remote path must include file name")
    parent = str(p.parent)
    if parent == ".":
        parent = "/"
    return parent, file_name


def _resolve_remote_target_path(
    *, base_url: str, access_token: str, remote_path: str
) -> str:
    normalized = _normalize_remote_path(remote_path)
    # Root-level absolute paths: /users/… (personal) and /public/… (Common/shared space).
    if normalized.startswith("/users/") or normalized.startswith("/public/"):
        return normalized
    root_prefix = (
        str(getattr(settings, "HIDRIVE_USERS_ROOT_PREFIX", "") or "")
        .strip()
        .rstrip("/")
    )
    if root_prefix:
        if not (
            root_prefix == "/public" or root_prefix.startswith(("/users/", "/public/"))
        ):
            raise ValueError(
                "HIDRIVE_USERS_ROOT_PREFIX must be an absolute HiDrive path "
                "starting with /users/ or /public/"
            )
        return f"{root_prefix}{normalized}"
    alias = _fetch_user_alias(base_url=base_url, access_token=access_token)
    return f"/users/{alias}{normalized}"


def _fetch_user_alias(*, base_url: str, access_token: str) -> str:
    timeout = int(getattr(settings, "HIDRIVE_TIMEOUT_SECONDS", 30))
    response = requests.get(
        f"{base_url}/user/me",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=timeout,
    )
    if response.status_code != 200:
        raise HiDriveApiError(
            f"HiDrive user/me failed with status {response.status_code}",
            status_code=response.status_code,
        )
    data = _response_json(response)
    alias = str(data.get("alias") or "").strip()
    if not alias:
        raise HiDriveApiError(
            "HiDrive user/me returned empty alias",
            status_code=response.status_code,
        )
    return alias


def _ensure_remote_directories(
    *, base_url: str, access_token: str, dir_path: str
) -> None:
    timeout = int(getattr(settings, "HIDRIVE_TIMEOUT_SECONDS", 30))
    headers = {"Authorization": f"Bearer {access_token}"}
    # Remote HiDrive paths are always POSIX; ``Path`` on Windows mangles leading ``/``.
    path_obj = PurePosixPath(dir_path)
    parts = [p for p in path_obj.parts if p not in ("", "/")]
    # HiDrive root namespaces are system-managed (creating them returns 403).
    # /users/<alias>/… → skip first 2 parts; /public/… → skip first 1 part.
    start_index = 0
    if len(parts) >= 2 and parts[0] == "users":
        start_index = 2
    elif parts and parts[0] == "public":
        start_index = 1
    current = ""
    for idx, part in enumerate(parts):
        current = f"{current}/{part}"
        if idx < start_index:
            continue
        response = requests.post(
            f"{base_url}/dir",
            params={"path": current},
            headers=headers,
            timeout=timeout,
        )
        if response.status_code in (200, 201, 409):
            continue
        # Treat already existing/forbidden as non-fatal when parent is not writable.
        if (
            response.status_code == 403
            and "already exists" in (response.text or "").lower()
        ):
            continue
        raise HiDriveApiError(
            f"HiDrive directory create failed for {current} with status {response.status_code}",
            status_code=response.status_code,
        )


def _use_mock_hidrive() -> bool:
    raw = getattr(settings, "HIDRIVE_USE_MOCK", "1")
    return str(raw).lower() in ("1", "true", "yes")


def get_hidrive_adapter() -> HiDriveAdapterProtocol:
    if _use_mock_hidrive():
        return _MockHiDriveAdapter()
    return _HiDriveAdapter()
