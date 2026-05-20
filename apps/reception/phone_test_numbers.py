"""Generate mobile test numbers for supported SMS regions (fixtures / tests)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, TypedDict

import phonenumbers
from phonenumbers import PhoneNumber, PhoneNumberFormat, PhoneNumberType
from phonenumbers.phonenumberutil import example_number_for_type

from apps.reception.phone_utils import (
    SUPPORTED_SMS_REGIONS,
    format_phone_e164_for_sms,
    infer_sms_region_from_phone,
    normalize_phone_for_patient_storage,
    phone_lookup_variants,
)

MOBILE_NUMBERS_PER_REGION = 25
MAX_SEARCH_DELTA = 3000


class MobilePhoneCase(TypedDict):
    region: str
    e164: str
    national: str
    international_digits: str
    supports_national_roundtrip: bool


def iter_mobile_candidates(region: str) -> Iterator[PhoneNumber]:
    """Valid MOBILE numbers in ``region``, deterministic order around lib example."""
    base = example_number_for_type(region, PhoneNumberType.MOBILE)
    if base is None:
        return
    seed = int(base.national_number)
    cc = base.country_code
    seen: set[int] = set()
    for delta in range(MAX_SEARCH_DELTA):
        for candidate in (seed + delta, seed - delta):
            if candidate <= 0 or candidate in seen:
                continue
            seen.add(candidate)
            parsed = PhoneNumber(country_code=cc, national_number=candidate)
            if phonenumbers.number_type(parsed) != PhoneNumberType.MOBILE:
                continue
            if not phonenumbers.is_valid_number_for_region(parsed, region):
                continue
            yield parsed


def _passes_e164_contract(region: str, e164: str, stored: str) -> bool:
    digits = e164.lstrip("+")
    return (
        infer_sms_region_from_phone(stored) == region
        and format_phone_e164_for_sms(stored) == e164
        and stored in phone_lookup_variants(e164)
        and stored in phone_lookup_variants(digits)
    )


def _supports_national_roundtrip(region: str, national: str, stored: str) -> bool:
    stored_nat = normalize_phone_for_patient_storage(national)
    return (
        infer_sms_region_from_phone(stored_nat) == region
        and stored_nat == stored
        and stored in phone_lookup_variants(national)
    )


def build_mobile_case(region: str, parsed: PhoneNumber) -> MobilePhoneCase | None:
    e164 = phonenumbers.format_number(parsed, PhoneNumberFormat.E164)
    stored = normalize_phone_for_patient_storage(e164)
    if not stored or not _passes_e164_contract(region, e164, stored):
        return None
    national = phonenumbers.format_number(parsed, PhoneNumberFormat.NATIONAL)
    return MobilePhoneCase(
        region=region,
        e164=e164,
        national=national,
        international_digits=e164.lstrip("+"),
        supports_national_roundtrip=_supports_national_roundtrip(
            region, national, stored
        ),
    )


def generate_region_mobile_cases(
    region: str,
    *,
    count: int = MOBILE_NUMBERS_PER_REGION,
) -> list[MobilePhoneCase]:
    cases: list[MobilePhoneCase] = []
    seen_e164: set[str] = set()
    for parsed in iter_mobile_candidates(region):
        case = build_mobile_case(region, parsed)
        if case is None or case["e164"] in seen_e164:
            continue
        seen_e164.add(case["e164"])
        cases.append(case)
        if len(cases) >= count:
            break
    return cases


def generate_all_region_fixtures() -> dict[str, list[MobilePhoneCase]]:
    fixtures: dict[str, list[MobilePhoneCase]] = {}
    for region in SUPPORTED_SMS_REGIONS:
        fixtures[region] = generate_region_mobile_cases(region)
    return fixtures


def fixtures_to_jsonable(fixtures: dict[str, list[MobilePhoneCase]]) -> dict[str, Any]:
    return {region: list(cases) for region, cases in fixtures.items()}
