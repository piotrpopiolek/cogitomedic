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
    normalized_name_variants,
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

    def test_match_filename_lab_export_with_cmber_and_timestamp(self) -> None:
        """Lab PDFs: ``Nazwisko_Imię_CMBER2026FR##_…`` (ASCII w stemie), dopasowanie po ``normalize_name``.

        Pokrycie niemieckich znaków w ``first_name`` / ``last_name``: ä Ä ö Ö ü Ü ß.
        """
        cases: list[tuple[str, str, str]] = [
            ("Thomas", "Müller", "Muller_Thomas_CMBER2026FR01_20260418090102"),
            ("Michael", "Schmidt", "Schmidt_Michael_CMBER2026FR02_20260418090215"),
            ("Andreas", "Schneider", "Schneider_Andreas_CMBER2026FR03_20260418090328"),
            ("Stefan", "Fischer", "Fischer_Stefan_CMBER2026FR04_20260418090441"),
            ("Christian", "Weber", "Weber_Christian_CMBER2026FR05_20260418090554"),
            ("Markus", "Meyer", "Meyer_Markus_CMBER2026FR06_20260418090707"),
            ("Martin", "Wagner", "Wagner_Martin_CMBER2026FR07_20260418090820"),
            ("Daniel", "Becker", "Becker_Daniel_CMBER2026FR08_20260418090933"),
            ("Sebastian", "Schulz", "Schulz_Sebastian_CMBER2026FR09_20260418091046"),
            (
                "Alexander",
                "Hoffmann",
                "Hoffmann_Alexander_CMBER2026FR10_20260418091159",
            ),
            ("Anna", "Schäfer", "Schafer_Anna_CMBER2026FR11_20260418091312"),
            ("Maria", "Koch", "Koch_Maria_CMBER2026FR12_20260418091425"),
            ("Petra", "Bauer", "Bauer_Petra_CMBER2026FR13_20260418091538"),
            ("Sabine", "Richter", "Richter_Sabine_CMBER2026FR14_20260418091651"),
            ("Monika", "Klein", "Klein_Monika_CMBER2026FR15_20260418091804"),
            ("Julia", "Wolf", "Wolf_Julia_CMBER2026FR16_20260418091917"),
            ("Laura", "Schroeder", "Schroeder_Laura_CMBER2026FR17_20260418092030"),
            ("Hannah", "Neumann", "Neumann_Hannah_CMBER2026FR18_20260418092143"),
            ("Leon", "Schwarz", "Schwarz_Leon_CMBER2026FR19_20260418092256"),
            ("Paul", "Zimmermann", "Zimmermann_Paul_CMBER2026FR20_20260418092409"),
            ("Felix", "Braun", "Braun_Felix_CMBER2026FR21_20260418092522"),
            ("Lukas", "Krüger", "Kruger_Lukas_CMBER2026FR22_20260418092635"),
            (
                "Maximilian",
                "Hofmann",
                "Hofmann_Maximilian_CMBER2026FR23_20260418092748",
            ),
            ("Emilia", "Hartmann", "Hartmann_Emilia_CMBER2026FR24_20260418092901"),
            ("Sophie", "Werner", "Werner_Sophie_CMBER2026FR25_20260418093014"),
            ("Äneas", "Wagner", "Wagner_Aneas_CMBER2026FR26_20260418100001"),
            ("Björn", "Schäfer", "Schafer_Bjorn_CMBER2026FR27_20260418100114"),
            ("Franz", "König", "Konig_Franz_CMBER2026FR28_20260418100227"),
            ("Lena", "Groß", "Gross_Lena_CMBER2026FR29_20260418100340"),
            ("Laura", "Schröder", "Schroder_Laura_CMBER2026FR30_20260418100453"),
            ("Nina", "Köhler", "Kohler_Nina_CMBER2026FR31_20260418100606"),
            ("Simon", "Bäcker", "Backer_Simon_CMBER2026FR32_20260418100719"),
            ("Tim", "Jäger", "Jager_Tim_CMBER2026FR33_20260418100832"),
            ("Uwe", "Höller", "Holler_Uwe_CMBER2026FR34_20260418100945"),
            ("Mehmet", "Öztürk", "Ozturk_Mehmet_CMBER2026FR35_20260418101058"),
            ("Klaus", "Weiß", "Weiss_Klaus_CMBER2026FR36_20260418101211"),
            ("Oliver", "Götz", "Gotz_Oliver_CMBER2026FR37_20260418101324"),
            ("Sandra", "Lübke", "Lubke_Sandra_CMBER2026FR38_20260418101437"),
            ("Bärbel", "Möller", "Moller_Barbel_CMBER2026FR39_20260418101550"),
            ("Leon", "Häßler", "Hassler_Leon_CMBER2026FR40_20260418101703"),
            ("Anna", "Voß", "Voss_Anna_CMBER2026FR41_20260418101816"),
            ("Max", "Zöller", "Zoller_Max_CMBER2026FR42_20260418101929"),
            ("Eva-Maria", "Stöcker", "Stocker_Eva-Maria_CMBER2026FR43_20260418102042"),
            ("Friedrich", "Preußen", "Preussen_Friedrich_CMBER2026FR44_20260418102155"),
            ("Günther", "Überacker", "Uberacker_Gunther_CMBER2026FR45_20260418102308"),
            ("Rüdiger", "Bähr", "Bahr_Rudiger_CMBER2026FR46_20260418102421"),
            ("Käthe", "Weiß", "Weiss_Kathe_CMBER2026FR47_20260418102534"),
            ("Sören", "Höfner", "Hofner_Soren_CMBER2026FR48_20260418102647"),
            ("Dörte", "Müller", "Muller_Dorte_CMBER2026FR49_20260418102800"),
            ("Jürgen", "Grün", "Grun_Jurgen_CMBER2026FR50_20260418102913"),
        ]
        for first_name, last_name, stem in cases:
            with self.subTest(stem=stem):
                p = Mock()
                p.first_name = first_name
                p.last_name = last_name
                p.date_of_birth = None
                c = build_patient_filename_candidates(p)
                self.assertTrue(
                    match_filename_to_candidates(stem, c),
                    f"expected {stem}.pdf to match {first_name} {last_name}",
                )

    def test_incoming_stem_norm_lookup_bases_lab_stem_includes_name_prefix(
        self,
    ) -> None:
        incoming_stem_norm_lookup_bases.cache_clear()
        norm = normalize_name("Muller_Thomas_CMBER2026FR01_20260418090102")
        bases = incoming_stem_norm_lookup_bases(norm)
        self.assertIn("muller_thomas", bases)

    def test_stem_matches_dated_variant(self) -> None:
        p = Mock()
        p.first_name = "Jan"
        p.last_name = "Kowalski"
        p.date_of_birth = datetime.date(1985, 3, 12)
        self.assertTrue(stem_matches_dated_variant("Kowalski_Jan_1985_03_12.pdf", p))
        self.assertFalse(stem_matches_dated_variant("Kowalski_Jan.pdf", p))

    def test_stem_matches_dated_variant_umlaut_transliteration_stems(self) -> None:
        """Dated HiDrive stems may use ``Mueller``/``Muller`` for ``Müller`` (ASCII)."""
        p = Mock()
        p.first_name = "Thomas"
        p.last_name = "Müller"
        p.date_of_birth = datetime.date(1990, 1, 1)
        self.assertTrue(stem_matches_dated_variant("Mueller_Thomas_1990_01_01.pdf", p))
        self.assertTrue(stem_matches_dated_variant("Muller_Thomas_1990_01_01.pdf", p))
        self.assertTrue(stem_matches_dated_variant("Thomas_Mueller_1990_01_01.pdf", p))
        dc = dated_match_candidates(p)
        self.assertIn("mueller_thomas_1990_01_01", dc)
        self.assertIn("muller_thomas_1990_01_01", dc)

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

    def test_normalized_name_variants_cover_umlaut_and_transliteration(self) -> None:
        self.assertEqual(
            normalized_name_variants("Müller"),
            ("muller", "mueller"),
        )
        self.assertEqual(
            normalized_name_variants("Mueller"),
            ("mueller", "muller"),
        )
        self.assertEqual(
            normalized_name_variants("Schröder"),
            ("schroder", "schroeder"),
        )
        self.assertEqual(
            normalized_name_variants("Blue"),
            ("blue",),
        )
        self.assertEqual(
            normalized_name_variants("Queenie"),
            ("queenie",),
        )

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

    def test_match_filename_accepts_mueller_and_umlaut_variants_both_directions(
        self,
    ) -> None:
        p = Mock()
        p.first_name = "Thomas"
        p.last_name = "Müller"
        p.date_of_birth = None
        candidates = build_patient_filename_candidates(p)

        self.assertTrue(match_filename_to_candidates("Mueller_Thomas", candidates))
        self.assertTrue(match_filename_to_candidates("Muller_Thomas", candidates))

        p2 = Mock()
        p2.first_name = "Thomas"
        p2.last_name = "Mueller"
        p2.date_of_birth = None
        candidates2 = build_patient_filename_candidates(p2)

        self.assertTrue(match_filename_to_candidates("Müller_Thomas", candidates2))
        self.assertTrue(match_filename_to_candidates("Muller_Thomas", candidates2))

    def test_match_undated_multi_file_suffix_kowalski_jan_2(self) -> None:
        """§12: ``kowalski_jan_2`` matches undated candidate ``kowalski_jan``."""
        p = Mock()
        p.first_name = "Jan"
        p.last_name = "Kowalski"
        p.date_of_birth = datetime.date(1985, 3, 12)
        c = build_patient_filename_candidates(p)
        self.assertTrue(match_filename_to_candidates("kowalski_jan_2", c))
        self.assertFalse(stem_matches_dated_variant("kowalski_jan_2", p))

    def test_incoming_stem_lookup_bases_include_collapsed_umlaut_transliteration(
        self,
    ) -> None:
        incoming_stem_norm_lookup_bases.cache_clear()
        norm = normalize_name("Mueller_Thomas_CMBER2026FR01_20260418090102")
        bases = incoming_stem_norm_lookup_bases(norm)
        self.assertIn("mueller_thomas", bases)
        self.assertIn("muller_thomas", bases)

    def test_incoming_stem_lookup_bases_do_not_collapse_non_umlaut_like_tokens(
        self,
    ) -> None:
        incoming_stem_norm_lookup_bases.cache_clear()
        norm = normalize_name("Blue_Queenie_CMBER2026FR01_20260418090102")
        bases = incoming_stem_norm_lookup_bases(norm)
        self.assertIn("blue_queenie", bases)
        self.assertNotIn("blu_queenie", bases)
        self.assertNotIn("blue_quenie", bases)

    def test_match_digit_in_last_name(self) -> None:
        p = Mock()
        p.first_name = "Jan"
        p.last_name = "Kowalski2"
        p.date_of_birth = None
        c = build_patient_filename_candidates(p)
        self.assertTrue(match_filename_to_candidates("kowalski2_jan", c))
        self.assertTrue(match_filename_to_candidates("jan_kowalski2", c))
