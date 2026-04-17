"""Phone normalization for patient lookups and storage."""

from __future__ import annotations

import re


def normalize_phone(value: str) -> str:
    """
    Normalize phone for storage and lookup: digits only, no leading zeros.

    Strips a national trunk ``0`` (e.g. DE ``0170…``) and an international
    dialing prefix ``00`` so that ``0049…`` and ``+49…`` converge to the same
    digit string as far as leading zeros allow.
    """
    if not value or not isinstance(value, str):
        return ""
    digits = re.sub(r"[^\d]", "", value.strip())
    digits = digits.lstrip("0")
    if not digits:
        return ""
    return digits if len(digits) >= 7 else ""


def format_phone_e164_for_sms(phone: str) -> str:
    """
    Build E.164 with leading ``+`` for SMS APIs from stored digits (no ``+`` in DB).

    Polish numbers are stored with country code ``48`` (``48…``). German numbers
    are stored without ``49``; it is prepended here. If the number already starts
    with ``49`` (full international DE), it is left unchanged.
    """
    if not phone or not isinstance(phone, str):
        return ""
    digits = re.sub(r"[^\d]", "", phone.strip())
    if not digits:
        return ""
    if digits.startswith("48"):
        return f"+{digits}"
    if digits.startswith("49"):
        return f"+{digits}"
    return f"+49{digits}"
