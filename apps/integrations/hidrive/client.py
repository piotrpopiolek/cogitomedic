"""HiDrive upload adapter (real + mock)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol

import requests
from django.conf import settings

from apps.integrations.hidrive.auth import HiDriveAuthError, get_hidrive_oauth_client

logger = logging.getLogger(__name__)


class HiDriveAdapterProtocol(Protocol):
    """Protocol for HiDrive uploads."""

    def upload(self, *, remote_path: str, local_path: Path) -> None:
        """Upload local file to remote HiDrive path."""
        ...


class _MockHiDriveAdapter:
    """Mock adapter – no outgoing HTTP."""

    def upload(self, *, remote_path: str, local_path: Path) -> None:
        logger.info(
            "[MOCK HIDRIVE] upload path=%s local=%s",
            remote_path,
            str(local_path),
        )


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

        if response.status_code in (200, 201, 204):
            return
        if response.status_code >= 500:
            raise RuntimeError(
                f"HiDrive upload failed with status {response.status_code}"
            )
        if response.status_code == 401:
            raise HiDriveAuthError("HiDrive upload unauthorized after token refresh")
        raise RuntimeError(
            f"HiDrive upload rejected with status {response.status_code}"
        )

    def _upload_once(
        self, *, access_token: str, remote_path: str, local_path: Path
    ) -> requests.Response:
        base_url = str(
            getattr(
                settings, "HIDRIVE_API_BASE_URL", "https://api.hidrive.strato.com/2.1"
            )
        ).rstrip("/")
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


def _normalize_remote_path(remote_path: str) -> str:
    normalized = (remote_path or "").strip()
    if not normalized:
        raise ValueError("HiDrive remote path must not be empty")
    if not normalized.startswith("/"):
        normalized = "/" + normalized
    return normalized


def _split_remote_path(remote_path: str) -> tuple[str, str]:
    normalized = _normalize_remote_path(remote_path)
    file_name = Path(normalized).name
    if not file_name:
        raise ValueError("HiDrive remote path must include file name")
    parent = str(Path(normalized).parent).replace("\\", "/")
    if parent == ".":
        parent = "/"
    return parent, file_name


def _resolve_remote_target_path(
    *, base_url: str, access_token: str, remote_path: str
) -> str:
    normalized = _normalize_remote_path(remote_path)
    if normalized.startswith("/users/"):
        return normalized
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
        raise RuntimeError(f"HiDrive user/me failed with status {response.status_code}")
    data = response.json()
    alias = str(data.get("alias") or "").strip()
    if not alias:
        raise RuntimeError("HiDrive user/me returned empty alias")
    return alias


def _ensure_remote_directories(
    *, base_url: str, access_token: str, dir_path: str
) -> None:
    timeout = int(getattr(settings, "HIDRIVE_TIMEOUT_SECONDS", 30))
    headers = {"Authorization": f"Bearer {access_token}"}
    path_obj = Path(dir_path)
    parts = [p for p in path_obj.parts if p not in ("", "/")]
    # HiDrive root namespaces like /users and /users/<alias> are system-managed.
    # Creating them returns 403, so only create paths below user alias.
    start_index = 0
    if len(parts) >= 2 and parts[0] == "users":
        start_index = 2
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
        raise RuntimeError(
            f"HiDrive directory create failed for {current} with status {response.status_code}"
        )


def _use_mock_hidrive() -> bool:
    raw = getattr(settings, "HIDRIVE_USE_MOCK", "1")
    return str(raw).lower() in ("1", "true", "yes")


def get_hidrive_adapter() -> HiDriveAdapterProtocol:
    if _use_mock_hidrive():
        return _MockHiDriveAdapter()
    return _HiDriveAdapter()
