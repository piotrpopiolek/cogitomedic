"""Phone normalization for patient lookups and storage."""

from __future__ import annotations

import re
from typing import Final

import phonenumbers
from phonenumbers import NumberParseException, PhoneNumber, PhoneNumberFormat

SUPPORTED_SMS_REGIONS: Final[tuple[str, ...]] = (
    "PL",
    "DE",
    "FR",
    "IT",
    "ES",
    "UA",
    "PT",
    "NL",
    "BE",
    "CH",
    "AT",
    "CZ",
    "GB",
)


def _supported_prefix_table() -> tuple[tuple[str, str], ...]:
    rows: list[tuple[str, str]] = []
    for r in SUPPORTED_SMS_REGIONS:
        cc = phonenumbers.country_code_for_region(r)
        if cc == 0:
            continue
        rows.append((str(cc), r))
    rows.sort(key=lambda x: (-len(x[0]), x[0]))
    return tuple(rows)


_PREFIX_TABLE: tuple[tuple[str, str], ...] = _supported_prefix_table()


def _digits_only(value: str) -> str:
    return re.sub(r"[^\d]", "", (value or "").strip())


def _region_from_parsed_digits(digits: str) -> str | None:
    if not digits:
        return None
    for prefix, region in _PREFIX_TABLE:
        if not digits.startswith(prefix):
            continue
        try:
            parsed = phonenumbers.parse("+" + digits, None)
            if phonenumbers.is_valid_number(parsed):
                rc = phonenumbers.region_code_for_number(parsed)
                if rc and rc in SUPPORTED_SMS_REGIONS:
                    return rc
        except NumberParseException:
            pass
        break
    return None


def infer_sms_region_from_phone(phone: str) -> str:
    """
    Infer ISO region for SMS / normalization from phone digits.

    Uses calling-code prefixes in stored digits. Does not use Patient.country_code
    (often always DE in production). Falls back to DE for legacy national numbers.
    """
    region = _region_from_parsed_digits(_digits_only(phone))
    return region if region else "DE"


def _valid_national_number_in_region(value: str, region: str) -> bool:
    """True when ``value`` is a national-format number valid in ``region`` only."""
    trimmed = (value or "").strip()
    if not trimmed or trimmed.startswith("+"):
        return False
    try:
        parsed = phonenumbers.parse(trimmed, region)
    except NumberParseException:
        return False
    if phonenumbers.region_code_for_number(parsed) != region:
        return False
    if not phonenumbers.is_valid_number_for_region(parsed, region):
        return False
    national_fmt = phonenumbers.format_number(parsed, PhoneNumberFormat.NATIONAL)
    return _digits_only(trimmed) == _digits_only(national_fmt)


def _regions_matching_national_input(value: str) -> tuple[str, ...]:
    """
    Supported regions where ``value`` parses as a valid national number.

    Same rules for every entry in ``SUPPORTED_SMS_REGIONS``.
    """
    legacy = normalize_phone(value)
    if len(legacy) < 7:
        return ()

    valid_regions = [
        region
        for region in SUPPORTED_SMS_REGIONS
        if _valid_national_number_in_region(value, region)
    ]
    de_norm = normalize_phone(value, default_region="DE")
    if (
        "DE" in valid_regions
        and de_norm == legacy
        and legacy.startswith(("15", "16", "17"))
    ):
        return ("DE",)

    matched: list[str] = []
    for region in valid_regions:
        cc = phonenumbers.country_code_for_region(region) or 0
        if cc >= 300:
            continue
        candidate = normalize_phone(value, default_region=region)
        if candidate and candidate != legacy:
            matched.append(region)
    return tuple(matched)


def _national_input_region_hint(value: str, matched: tuple[str, ...]) -> str | None:
    """
    Disambiguate national trunk input using dial-string prefixes (before legacy strip).

    Same idea as DE-first for 15/16/17: local conventions, not a second parse pass for one region.
    """
    digits = _digits_only(value)
    if not digits:
        return None
    if digits.startswith("06") and "FR" in matched:
        return "FR"
    if digits.startswith("07"):
        if "GB" in matched and "FR" not in matched:
            return "GB"
        if "FR" in matched and "GB" not in matched:
            return "FR"
    if digits.startswith(("01", "02", "03")) and "GB" in matched:
        return "GB"
    return None


def _pick_national_storage_region(value: str, matched: tuple[str, ...]) -> str:
    """Choose one region when several national parses validate."""
    if not matched:
        return ""
    if len(matched) == 1:
        return matched[0]

    hinted = _national_input_region_hint(value, matched)
    if hinted:
        return hinted

    for region in sorted(
        matched,
        key=lambda r: phonenumbers.country_code_for_region(r) or 0,
        reverse=True,
    ):
        stored = normalize_phone(value, default_region=region)
        if not stored:
            continue
        try:
            parsed = phonenumbers.parse("+" + stored, None)
        except NumberParseException:
            continue
        if (
            phonenumbers.is_valid_number(parsed)
            and phonenumbers.region_code_for_number(parsed) == region
        ):
            return region
    return matched[0]


def phone_lookup_variants(value: str) -> tuple[str, ...]:
    """
    Candidate normalized digit strings for patient / OTP lookup.

    Legacy digit strip first; international prefixes use the matching region;
    national trunk numbers (no CC in input) add storage forms for each supported
    region where libphonenumber validates the number.
    """
    seen: list[str] = []

    def add(candidate: str) -> None:
        if candidate and candidate not in seen:
            seen.append(candidate)

    legacy = normalize_phone(value)
    add(legacy)

    digits = _digits_only(value)
    region_from_prefix = _region_from_parsed_digits(digits)
    if region_from_prefix:
        add(normalize_phone(value, default_region=region_from_prefix))
        return tuple(seen)

    matched = _regions_matching_national_input(value)
    if matched == ("DE",):
        add(normalize_phone(value, default_region="DE"))
        return tuple(seen)
    if matched:
        region = _pick_national_storage_region(value, matched)
        add(normalize_phone(value, default_region=region))

    return tuple(seen)


def normalize_phone_for_patient_storage(phone: str) -> str:
    """Normalize phone on Patient.save using region inferred from the number."""
    if not phone:
        return phone
    digits = _digits_only(phone)
    region_from_prefix = _region_from_parsed_digits(digits)
    if region_from_prefix:
        norm = normalize_phone(phone, default_region=region_from_prefix)
        return norm or normalize_phone(phone)

    matched = _regions_matching_national_input(phone)
    if matched:
        region = _pick_national_storage_region(phone, matched)
        norm = normalize_phone(phone, default_region=region)
        return norm or normalize_phone(phone)

    if _valid_national_number_in_region(phone, "DE"):
        return normalize_phone(phone, default_region="DE") or normalize_phone(phone)

    return normalize_phone(phone)


def _legacy_digit_normalize(value: str) -> str:
    if not value or not isinstance(value, str):
        return ""
    digits = re.sub(r"[^\d]", "", value.strip())
    digits = digits.lstrip("0")
    if not digits:
        return ""
    return digits if len(digits) >= 7 else ""


def normalize_phone(value: str, default_region: str | None = None) -> str:
    """
    Normalize phone for storage and lookup: digits only, no leading zeros.

    Without ``default_region``, strips a national trunk ``0`` (e.g. DE ``0170…``)
    and an international dialing prefix ``00`` so that ``0049…`` and ``+49…``
    converge to the same digit string as far as leading zeros allow.

    With ``default_region`` (ISO-3166-1 alpha-2), parses using libphonenumber
    when possible so national numbers (e.g. ``0612…`` in FR, ``07911…`` in GB)
    are stored with the correct country calling code.
    """
    if default_region is None:
        return _legacy_digit_normalize(value)

    trimmed = (value or "").strip()
    if not trimmed:
        return ""

    legacy = _legacy_digit_normalize(value)
    if len(legacy) < 7:
        return ""

    region = (default_region or "DE").strip().upper()
    if region not in SUPPORTED_SMS_REGIONS:
        region = "DE"

    try:
        parsed: PhoneNumber | None = None
        if trimmed.startswith("+"):
            parsed = phonenumbers.parse(trimmed, None)
        else:
            raw_digits = re.sub(r"[^\d]", "", trimmed)
            if raw_digits.startswith("00"):
                raw_digits = raw_digits[2:]
            has_prefix = any(
                raw_digits.startswith(prefix) for prefix, _ in _PREFIX_TABLE
            )
            if has_prefix:
                parsed = phonenumbers.parse("+" + raw_digits, None)
            else:
                parsed = phonenumbers.parse(trimmed, region)

        if parsed is not None and phonenumbers.is_valid_number(parsed):
            rc = phonenumbers.region_code_for_number(parsed)
            if rc and rc in SUPPORTED_SMS_REGIONS:
                return _storage_digits(parsed, legacy, rc)
    except NumberParseException:
        pass

    return legacy


def _storage_digits(parsed: PhoneNumber, legacy: str, region_code: str) -> str:
    """Digits for DB: DE may omit country code; other regions use full CC+NN."""
    cc = str(parsed.country_code)
    nn = str(parsed.national_number)
    full_intl = f"{cc}{nn}"
    if region_code == "DE":
        if legacy.startswith("49"):
            return legacy
        return nn
    if legacy.startswith(cc):
        try:
            alt = phonenumbers.parse("+" + legacy, None)
            if phonenumbers.is_valid_number(alt):
                alt_rc = phonenumbers.region_code_for_number(alt)
                if alt_rc == region_code:
                    return legacy
        except NumberParseException:
            pass
    return full_intl


def format_phone_e164_for_sms(phone: str, default_region: str = "DE") -> str:
    """
    Build E.164 with leading ``+`` for SMS APIs from stored digits (no ``+`` in DB).

    Detects country from supported calling-code prefixes. If none match, parses as
    a national number in ``default_region`` (use ``infer_sms_region_from_phone`` for
    stored digits). Falls back to ``+49`` + digits for backward compatibility.
    """
    if not phone or not isinstance(phone, str):
        return ""
    digits = _digits_only(phone)
    if not digits:
        return ""

    for prefix, _ in _PREFIX_TABLE:
        if digits.startswith(prefix):
            try:
                parsed = phonenumbers.parse("+" + digits, None)
                if phonenumbers.is_valid_number(parsed):
                    rc = phonenumbers.region_code_for_number(parsed)
                    if rc in SUPPORTED_SMS_REGIONS:
                        return phonenumbers.format_number(
                            parsed, PhoneNumberFormat.E164
                        )
            except NumberParseException:
                pass
            break

    region = (default_region or "DE").strip().upper()
    if region not in SUPPORTED_SMS_REGIONS:
        region = "DE"
    try:
        parsed = phonenumbers.parse(digits, region)
        if phonenumbers.is_valid_number(parsed):
            rc = phonenumbers.region_code_for_number(parsed)
            if rc in SUPPORTED_SMS_REGIONS:
                return phonenumbers.format_number(parsed, PhoneNumberFormat.E164)
    except NumberParseException:
        pass

    return f"+49{digits}"
