"""SMS adapter for SMSApi (smsapi.pl)."""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Protocol

from django.conf import settings

from apps.core.translation_service import get_translation_map, normalize_language_code

logger = logging.getLogger(__name__)

SMS_PATIENT_RESULTS_KEY = "other.sms.patient_results"
_DEFAULT_SMS_PATIENT_RESULTS = "Neue Dokumentation bei CogitoMed {url}"


def get_sms_patient_results_text(locale: str | None, url: str) -> str:
    """Return SMS text for patient results notification from DB translations."""
    lang = normalize_language_code(locale or "de")
    mapping = get_translation_map(category="other", language_code=lang)
    template = mapping.get(SMS_PATIENT_RESULTS_KEY) or _DEFAULT_SMS_PATIENT_RESULTS
    return template.format(url=url)


class SmsAdapterProtocol(Protocol):
    """Protocol for SMS sending."""

    def send_sms(self, to: str, message: str) -> None:
        """Send SMS to the given number."""
        ...


class _SmsApiAdapter:
    """Real SMSApi (smsapi.pl) adapter."""

    def __init__(self) -> None:
        token = getattr(settings, "SMSAPI_ACCESS_TOKEN", None) or ""
        if not token:
            raise ValueError("SMSAPI_ACCESS_TOKEN must be set when SMSAPI_USE_MOCK is False")
        from smsapi.client import SmsApiPlClient

        self._client = SmsApiPlClient(access_token=token)

    def send_sms(self, to: str, message: str) -> None:
        result = self._client.sms.send(to=to, message=message)
        logger.info("SMS sent to %s, id=%s, status=%s", to[:4] + "***", getattr(result, "id", "?"), getattr(result, "status", "?"))


class _MockSmsAdapter:
    """Mock adapter – logs only, no HTTP."""

    def send_sms(self, to: str, message: str) -> None:
        logger.info("[MOCK SMS] to=%s*** message=%s", to[: min(4, len(to))], message[:50] + ("..." if len(message) > 50 else ""))


def _use_mock_sms() -> bool:
    raw = getattr(settings, "SMSAPI_USE_MOCK", "1")
    return str(raw).lower() in ("1", "true", "yes")


@lru_cache(maxsize=1)
def get_sms_adapter() -> SmsAdapterProtocol:
    """Return configured SMS adapter (singleton)."""
    if _use_mock_sms():
        return _MockSmsAdapter()
    return _SmsApiAdapter()


# Alias for plan compatibility
SmsAdapter = SmsAdapterProtocol
