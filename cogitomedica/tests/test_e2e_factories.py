"""Unit checks for E2E factory helpers (no browser)."""

from __future__ import annotations

import re

from django.test import SimpleTestCase

from cogitomedica.tests.e2e.factories import e2e_patient_phone


class E2eFactoryHelperTests(SimpleTestCase):
    def test_patient_phone_matches_db_check_constraint(self) -> None:
        pattern = re.compile(r"^[0-9]{7,20}$")
        phones = {e2e_patient_phone() for _ in range(40)}
        self.assertGreaterEqual(len(phones), 30)
        for phone in phones:
            self.assertRegex(phone, pattern)
