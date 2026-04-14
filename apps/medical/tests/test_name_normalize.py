"""Tests for apps.medical.name_normalize."""

from __future__ import annotations

import datetime
from unittest.mock import Mock

from django.test import SimpleTestCase

from apps.medical.name_normalize import (
    build_patient_filename_candidates,
    compute_incoming_pdf_name_keys,
    dated_match_candidates,
    incoming_stem_norm_lookup_bases,
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

    def test_dated_match_candidates_empty_when_no_dob(self) -> None:
        p = Mock()
        p.first_name = "Jan"
        p.last_name = "Kowalski"
        p.date_of_birth = None
        self.assertEqual(dated_match_candidates(p), [])

    def test_stem_matches_dated_variant_false_when_patient_has_no_dob(self) -> None:
        p = Mock()
        p.first_name = "Jan"
        p.last_name = "Kowalski"
        p.date_of_birth = None
        self.assertFalse(stem_matches_dated_variant("Kowalski_Jan_1985_03_12.pdf", p))

    def test_compute_incoming_pdf_name_keys(self) -> None:
        self.assertEqual(
            compute_incoming_pdf_name_keys("Jan", "Kowalski"),
            ("jan_kowalski", "kowalski_jan"),
        )

    def test_incoming_stem_norm_lookup_bases_multi_file_suffix(self) -> None:
        incoming_stem_norm_lookup_bases.cache_clear()
        self.assertEqual(
            incoming_stem_norm_lookup_bases("med_test_2"),
            frozenset({"med_test_2", "med_test"}),
        )

    def test_incoming_stem_norm_lookup_bases_dob_tail_not_stripped(self) -> None:
        incoming_stem_norm_lookup_bases.cache_clear()
        self.assertEqual(
            incoming_stem_norm_lookup_bases("jan_kowalski_1985_03_12"),
            frozenset({"jan_kowalski_1985_03_12"}),
        )

    def test_normalize_name_plan_examples_german_polish(self) -> None:
        """§12 plan: further diacritics / compound names."""
        self.assertEqual(normalize_name("Straße"), "strasse")
        self.assertEqual(normalize_name("Żołnierz"), "zolnierz")
        self.assertEqual(normalize_name("Świątek"), "swiatek")

    def test_normalize_name_fifty_german_full_name_stems(self) -> None:
        """Fifty full-name stems (spaces): DE orderings, Zweitname, von/zu, hyphens, ß/umlauts.

        Mirrors how reception may name PDFs before ``.pdf`` — entire stem is normalized as one string.
        """
        cases: list[tuple[str, str]] = [
            ("Hans Müller", "hans_muller"),
            ("Müller Hans", "muller_hans"),
            ("Hans Peter Müller", "hans_peter_muller"),
            ("Müller Hans Peter", "muller_hans_peter"),
            ("Anna Müller-Schmidt", "anna_muller_schmidt"),
            ("Müller-Schmidt Anna", "muller_schmidt_anna"),
            ("Jürgen Wagner", "jurgen_wagner"),
            ("Wagner Jürgen", "wagner_jurgen"),
            ("Käthe Kollwitz", "kathe_kollwitz"),
            ("Kollwitz Käthe", "kollwitz_kathe"),
            ("Heinz Dieter Lorenz", "heinz_dieter_lorenz"),
            ("Lorenz Heinz Dieter", "lorenz_heinz_dieter"),
            ("von Stauffenberg Klaus", "von_stauffenberg_klaus"),
            ("Klaus von Stauffenberg", "klaus_von_stauffenberg"),
            (
                "Friedrich Wilhelm Prinz von Preußen",
                "friedrich_wilhelm_prinz_von_preussen",
            ),
            (
                "Prinz von Preußen Friedrich Wilhelm",
                "prinz_von_preussen_friedrich_wilhelm",
            ),
            ("Renée Zellweger", "renee_zellweger"),
            ("Zellweger Renée", "zellweger_renee"),
            ("Françoise Dupont", "francoise_dupont"),
            ("Straßen Räuber", "strassen_rauber"),
            ("Räuber Straßen", "rauber_strassen"),
            ("Günter Graß", "gunter_grass"),
            ("Graß Günter", "grass_gunter"),
            ("Voß Voß", "voss_voss"),
            ("Weiß Grau", "weiss_grau"),
            ("Schön Groß Klein", "schon_gross_klein"),
            ("Klein Groß Schön", "klein_gross_schon"),
            ("Ödipus Röhrig", "odipus_rohrig"),
            ("Mönchen Gladbach Fan", "monchen_gladbach_fan"),
            ("Henriëtte Bosmans", "henriette_bosmans"),
            ("Überacker Franz", "uberacker_franz"),
            ("Zoë Schmidt", "zoe_schmidt"),
            ("Naß Naß", "nass_nass"),
            (
                "Alexandra Freifrau von und zu Hohenstein",
                "alexandra_freifrau_von_und_zu_hohenstein",
            ),
            (
                "Hohenstein Alexandra Freifrau von und zu",
                "hohenstein_alexandra_freifrau_von_und_zu",
            ),
            ("Jean-Pierre Müller", "jean_pierre_muller"),
            ("Müller Jean-Pierre", "muller_jean_pierre"),
            ("Thomas Decker", "thomas_decker"),
            ("Luis García Hernández", "luis_garcia_hernandez"),
            ("Hernández Luis García", "hernandez_luis_garcia"),
            ("Cäcilie Berger", "cacilie_berger"),
            ("Berger Cäcilie", "berger_cacilie"),
            ("Piątek Robert", "piatek_robert"),
            ("Straße 17", "strasse_17"),
            ("Dr med Müller Hans", "dr_med_muller_hans"),
            ("Karl-Heinz Römer", "karl_heinz_romer"),
            ("Eva-Maria Stöcker", "eva_maria_stocker"),
            ("Stöcker Eva-Maria", "stocker_eva_maria"),
            ("von der Heide Tim", "von_der_heide_tim"),
            ("Tim von der Heide", "tim_von_der_heide"),
        ]
        self.assertEqual(len(cases), 50)
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(normalize_name(raw), expected)

    def test_match_filename_fifty_german_full_name_splits(self) -> None:
        """DB ``first_name`` / ``last_name`` (with diacritics) vs stems as on HiDrive ``/incoming/``.

        Plan (``hidrive_pdf_download``): PDF names use ``_`` everywhere and are **ASCII-only**
        (no diacritics); matching compares ``normalize_name`` of the stem to candidates from DB.
        """
        dob = datetime.date(1971, 5, 9)
        rows: list[tuple[str, str, datetime.date | None, str, bool]] = [
            ("Hans", "Müller", None, "Muller_Hans", True),
            ("Hans Peter", "Müller", None, "Muller_Hans_Peter", True),
            ("Hans Peter", "Müller", None, "Hans_Peter_Muller", True),
            ("Anna", "Müller-Schmidt", None, "Muller_Schmidt_Anna", True),
            ("Jürgen", "Wagner", dob, "Wagner_Jurgen_1971_05_09", True),
            ("Käthe", "Kollwitz", None, "Kollwitz_Kathe", True),
            ("Heinz Dieter", "Lorenz", None, "Lorenz_Heinz_Dieter", True),
            ("Klaus", "von Stauffenberg", None, "von_Stauffenberg_Klaus", True),
            (
                "Friedrich Wilhelm",
                "Prinz von Preußen",
                None,
                "Prinz_von_Preussen_Friedrich_Wilhelm",
                True,
            ),
            ("Renée", "Zellweger", None, "Zellweger_Renee", True),
            ("Jean-Pierre", "Müller", None, "Muller_Jean-Pierre", True),
            ("Luis", "García Hernández", None, "Garcia_Hernandez_Luis", True),
            ("Cäcilie", "Berger", None, "Berger_Cacilie", True),
            ("Eva-Maria", "Stöcker", dob, "Stocker_Eva-Maria_1971_05_09", True),
            ("Tim", "von der Heide", None, "von_der_Heide_Tim", True),
            ("Hans", "Müller", None, "Muller_Franz", False),
            ("Hans", "Müller", dob, "Muller_Hans_1999_01_01", False),
            ("Hans Peter", "Müller", None, "Muller_Hans", False),
            ("Heinz Dieter", "Lorenz", None, "Lorenz_Heinz", False),
            ("Klaus", "von Stauffenberg", None, "Stauffenberg_Klaus", False),
            ("Günter", "Graß", None, "Grass_Gunter", True),
            ("Günter", "Graß", None, "Gunter_Grass", True),
            ("Voß", "Voß", None, "Voss_Voss", True),
            ("Weiß", "Grau", None, "Weiss_Grau", True),
            ("Thomas", "Decker", None, "Decker_Thomas", True),
            ("Zoë", "Schmidt", None, "Schmidt_Zoe", True),
            ("Ödipus", "Röhrig", None, "Rohrig_Odipus", True),
            ("Françoise", "Dupont", None, "Dupont_Francoise", True),
            ("Hans", "Müller", None, "Muller_Hans_3", True),
            ("Hans", "Müller", dob, "Muller_Hans_1971_05_09", True),
            ("Nicola", "Löwenbräu", None, "Lowenbrau_Nicola", True),
            ("Ute", "Groß", None, "Gross_Ute", True),
            ("Bärbel", "Höhn", None, "Hohn_Barbel", True),
            ("Rüdiger", "Lübke", None, "Lubke_Rudiger", True),
            ("Michael", "Großmann", None, "Grossmann_Michael", True),
            ("Sandra", "Weiß", None, "Weiss_Sandra", True),
            ("Ingo", "Schröder", None, "Schroder_Ingo", True),
            ("Petra", "Möller", None, "Moller_Petra", True),
            ("Kevin", "Öztürk", None, "Ozturk_Kevin", True),
            ("Lisa", "Männlein", None, "Mannlein_Lisa", True),
            ("Andrea", "Groß-Klein", None, "Gross_Klein_Andrea", True),
            ("Marco", "Fischer-Schlüter", None, "Fischer_Schluter_Marco", True),
            ("Henriëtte", "Bosmans", None, "Bosmans_Henriette", True),
            ("Franz", "Überacker", None, "Uberacker_Franz", True),
            ("Piątek", "Robert", None, "Robert_Piatek", True),
            ("Hans", "Müller", dob, "Hans_Muller_1971_05_09", True),
            ("Karl-Heinz", "Römer", None, "Romer_Karl-Heinz", True),
            ("Karl-Heinz", "Römer", dob, "Romer_Karl-Heinz_1971_05_09", True),
            ("Hans", "Müller", None, "Muller", False),
            ("Anna", "Müller-Schmidt", None, "Schmidt_Anna", False),
        ]
        self.assertEqual(len(rows), 50)
        for first_name, last_name, date_of_birth, stem, want in rows:
            with self.subTest(
                first_name=first_name,
                last_name=last_name,
                stem=stem,
            ):
                p = Mock()
                p.first_name = first_name
                p.last_name = last_name
                p.date_of_birth = date_of_birth
                c = build_patient_filename_candidates(p)
                self.assertEqual(match_filename_to_candidates(stem, c), want)

    def test_normalize_name_empty_and_whitespace(self) -> None:
        self.assertEqual(normalize_name(""), "")
        self.assertEqual(normalize_name("   "), "")
        self.assertEqual(normalize_name("  Kowalski   Jan  "), "kowalski_jan")
        self.assertEqual(normalize_name("A__B"), "a__b")

    def test_build_patient_filename_candidates_without_dob(self) -> None:
        p = Mock()
        p.first_name = "Jan"
        p.last_name = "Kowalski"
        p.date_of_birth = None
        self.assertEqual(
            build_patient_filename_candidates(p),
            ["jan_kowalski", "kowalski_jan"],
        )

    def test_match_filename_with_space_in_stem_via_normalize(self) -> None:
        """§12: stem from ``Kowalski Jan.pdf`` normalizes to ``kowalski_jan``."""
        p = Mock()
        p.first_name = "Jan"
        p.last_name = "Kowalski"
        p.date_of_birth = datetime.date(1985, 3, 12)
        c = build_patient_filename_candidates(p)
        self.assertTrue(match_filename_to_candidates("Kowalski Jan", c))

    def test_match_undated_multi_file_suffix_kowalski_jan_2(self) -> None:
        """§12: ``kowalski_jan_2`` matches undated candidate ``kowalski_jan``."""
        p = Mock()
        p.first_name = "Jan"
        p.last_name = "Kowalski"
        p.date_of_birth = datetime.date(1985, 3, 12)
        c = build_patient_filename_candidates(p)
        self.assertTrue(match_filename_to_candidates("kowalski_jan_2", c))
        self.assertFalse(stem_matches_dated_variant("kowalski_jan_2", p))

    def test_match_digit_in_last_name(self) -> None:
        p = Mock()
        p.first_name = "Jan"
        p.last_name = "Kowalski2"
        p.date_of_birth = None
        c = build_patient_filename_candidates(p)
        self.assertTrue(match_filename_to_candidates("kowalski2_jan", c))
        self.assertTrue(match_filename_to_candidates("jan_kowalski2", c))
