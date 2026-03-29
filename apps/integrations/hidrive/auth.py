"""OAuth2 token management for HiDrive API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
from typing import Any

import requests
from django.conf import settings
from prometheus_client import Counter

logger = logging.getLogger(__name__)

_hidrive_token_refresh_total = Counter(
    "cogitomedica_hidrive_token_refresh_total",
    "Number of HiDrive access-token refresh attempts.",
    labelnames=["outcome"],
)


class HiDriveAuthError(RuntimeError):
    """Raised when HiDrive OAuth authentication fails."""


@dataclass
class _AccessTokenState:
    access_token: str
    expires_at: datetime
    refresh_token: str


class HiDriveOAuthClient:
    """Refresh and cache HiDrive access token in process memory."""

    def __init__(self) -> None:
        self._token_state: _AccessTokenState | None = None

    def get_access_token(self, *, force_refresh: bool = False) -> str:
        if (
            force_refresh
            or self._token_state is None
            or self._is_expired(self._token_state)
        ):
            self._token_state = self._refresh_access_token(
                refresh_token=(
                    self._token_state.refresh_token
                    if self._token_state is not None
                    else _required_setting("HIDRIVE_REFRESH_TOKEN")
                )
            )
        return self._token_state.access_token

    @staticmethod
    def _is_expired(state: _AccessTokenState) -> bool:
        return datetime.now(timezone.utc) >= state.expires_at

    def _refresh_access_token(self, *, refresh_token: str) -> _AccessTokenState:
        _hidrive_token_refresh_total.labels(outcome="attempt").inc()
        payload = {
            "client_id": _required_setting("HIDRIVE_CLIENT_ID"),
            "client_secret": _required_setting("HIDRIVE_CLIENT_SECRET"),
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }

        timeout = int(getattr(settings, "HIDRIVE_TIMEOUT_SECONDS", 30))
        response = requests.post(
            getattr(
                settings, "HIDRIVE_TOKEN_URL", "https://my.hidrive.com/oauth2/token"
            ),
            data=payload,
            timeout=timeout,
        )
        if response.status_code != 200:
            _hidrive_token_refresh_total.labels(outcome="error").inc()
            raise HiDriveAuthError(
                f"HiDrive token refresh failed with status {response.status_code}"
            )

        data = _safe_json(response)
        access_token = str(data.get("access_token") or "").strip()
        if not access_token:
            _hidrive_token_refresh_total.labels(outcome="error").inc()
            raise HiDriveAuthError("HiDrive token refresh returned empty access_token")

        expires_in_raw = data.get("expires_in")
        try:
            expires_in = int(expires_in_raw)  # type: ignore[arg-type]
        except (TypeError, ValueError) as exc:
            _hidrive_token_refresh_total.labels(outcome="error").inc()
            raise HiDriveAuthError(
                "HiDrive token refresh returned invalid expires_in"
            ) from exc

        next_refresh_token = str(data.get("refresh_token") or refresh_token).strip()
        if not next_refresh_token:
            _hidrive_token_refresh_total.labels(outcome="error").inc()
            raise HiDriveAuthError("HiDrive token refresh returned empty refresh_token")

        # Small safety margin before actual expiry.
        expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=max(30, expires_in - 30)
        )
        return _AccessTokenState(
            access_token=access_token,
            expires_at=expires_at,
            refresh_token=next_refresh_token,
        )


def _required_setting(name: str) -> str:
    value = str(getattr(settings, name, "") or "").strip()
    if not value:
        raise HiDriveAuthError(f"{name} must be set when HIDRIVE_USE_MOCK is disabled")
    return value


def _safe_json(response: requests.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except Exception as exc:
        raise HiDriveAuthError("HiDrive token refresh returned invalid JSON") from exc
    if not isinstance(data, dict):
        raise HiDriveAuthError("HiDrive token refresh returned non-object JSON")
    return data


_oauth_client: HiDriveOAuthClient | None = None


def get_hidrive_oauth_client() -> HiDriveOAuthClient:
    global _oauth_client
    if _oauth_client is None:
        _oauth_client = HiDriveOAuthClient()
    return _oauth_client


def get_hidrive_refresh_metrics() -> dict[str, float]:
    values = {"attempt": 0.0, "error": 0.0}
    for metric in _hidrive_token_refresh_total.collect():
        for sample in metric.samples:
            if sample.name != "cogitomedica_hidrive_token_refresh_total":
                continue
            outcome = str(sample.labels.get("outcome") or "")
            if outcome in values:
                values[outcome] = float(sample.value)
    return values
