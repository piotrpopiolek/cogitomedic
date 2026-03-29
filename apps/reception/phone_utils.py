"""Phone normalization for patient lookups and storage."""

from __future__ import annotations

import re


def normalize_phone(value: str) -> str:
    """Normalize phone to digits only (for storage and lookup)."""
    if not value or not isinstance(value, str):
        return ""
    digits = re.sub(r"[^\d]", "", value.strip())
    return digits if len(digits) >= 7 else ""
