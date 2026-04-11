"""Tests for apps.medical.name_normalize."""

from __future__ import annotations

import datetime
from unittest.mock import Mock

from django.test import SimpleTestCase

from apps.medical.name_normalize import (
    build_patient_filename_candidates,
    match_filename_to_candidates,
    normalize_name,
    stem_matches_dated_variant,
)


class NameNormalizeTests(SimpleTestCase):
    def test_normalize_name_diacritics_and_separators(self) -> None:
        self.assertEqual(normalize_name("Müller"), "muller")
        self.assertEqual(normalize_name("König"), "konig")
        self.assertEqual(normalize_name("Großmann"), "grossmann")
        self.assertEqual(normalize_name("Śliwka"), "sliwka")
        self.assertEqual(normalize_name("Kowalska-Nowak"), "kowalska_nowak")
        self.assertEqual(normalize_name("Kowalski Jan"), "kowalski_jan")

    def test_build_patient_filename_candidates_with_dob(self) -> None:
        p = Mock()
        p.first_name = "Jan"
        p.last_name = "Kowalski"
        p.date_of_birth = datetime.date(1985, 3, 12)
        c = build_patient_filename_candidates(p)
        self.assertEqual(
            c,
            [
                "jan_kowalski",
                "kowalski_jan",
                "jan_kowalski_1985_03_12",
                "kowalski_jan_1985_03_12",
            ],
        )

    def test_match_filename_to_candidates(self) -> None:
        p = Mock()
        p.first_name = "Jan"
        p.last_name = "Kowalski"
        p.date_of_birth = datetime.date(1985, 3, 12)
        c = build_patient_filename_candidates(p)
        self.assertTrue(match_filename_to_candidates("Kowalski_Jan", c))
        self.assertTrue(match_filename_to_candidates("kowalski_jan_1985_03_12_2", c))
        self.assertFalse(match_filename_to_candidates("kowalski_jan_wyniki_brata", c))

    def test_stem_matches_dated_variant(self) -> None:
        p = Mock()
        p.first_name = "Jan"
        p.last_name = "Kowalski"
        p.date_of_birth = datetime.date(1985, 3, 12)
        self.assertTrue(stem_matches_dated_variant("Kowalski_Jan_1985_03_12.pdf", p))
        self.assertFalse(stem_matches_dated_variant("Kowalski_Jan.pdf", p))
