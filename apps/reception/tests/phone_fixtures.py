"""Shared loader for mobile_numbers_by_region.json test fixture."""

from __future__ import annotations

import json
from pathlib import Path

from apps.reception.phone_test_numbers import MobilePhoneCase

_FIXTURE_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "mobile_numbers_by_region.json"
)


def load_mobile_numbers_by_region() -> dict[str, list[MobilePhoneCase]]:
    data = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    return {region: list(cases) for region, cases in data.items()}
