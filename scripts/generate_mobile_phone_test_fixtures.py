#!/usr/bin/env python3
"""
Generate mobile_numbers_by_region.json for reception phone_utils tests.

Run from repo root (Docker recommended):
    docker compose run --rm web python scripts/generate_mobile_phone_test_fixtures.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.reception.phone_test_numbers import (  # noqa: E402
    MOBILE_NUMBERS_PER_REGION,
    fixtures_to_jsonable,
    generate_all_region_fixtures,
)
from apps.reception.phone_utils import SUPPORTED_SMS_REGIONS  # noqa: E402

OUTPUT = (
    ROOT / "apps" / "reception" / "tests" / "fixtures" / "mobile_numbers_by_region.json"
)


def main() -> int:
    fixtures = generate_all_region_fixtures()
    missing = [
        region
        for region in SUPPORTED_SMS_REGIONS
        if len(fixtures.get(region, [])) < MOBILE_NUMBERS_PER_REGION
    ]
    if missing:
        for region in missing:
            print(
                f"ERROR {region}: only {len(fixtures.get(region, []))}/"
                f"{MOBILE_NUMBERS_PER_REGION}",
                file=sys.stderr,
            )
        return 1

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(fixtures_to_jsonable(fixtures), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {OUTPUT}")
    for region in SUPPORTED_SMS_REGIONS:
        cases = fixtures[region]
        national_ok = sum(1 for c in cases if c["supports_national_roundtrip"])
        print(f"  {region}: {len(cases)} numbers, national_roundtrip={national_ok}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
