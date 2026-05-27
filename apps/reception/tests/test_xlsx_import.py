"""Tests for apps.reception.xlsx_import — pure functions and integration."""

from __future__ import annotations

from datetime import date, time

from django.test import SimpleTestCase

from freezegun import freeze_time

from apps.reception.xlsx_import import (
    NormalizedRow,
    XlsxImportErrorCode,
    XlsxImportFailure,
    _cleanup_clinic_name,
    _extract_file_metadata,
    _find_header_indices,
    _normalize_header_cell,
    _normalize_row,
    _normalize_site_name,
    _parse_date,
    _parse_time,
    _split_full_name,
    _title_case_name,
    _validate_headers,
)

# =================================================================
# Pure-function tests — no DB
# =================================================================


class NormalizeHeaderCellTests(SimpleTestCase):
    def test_strips_whitespace_and_lowercases(self):
        self.assertEqual(_normalize_header_cell("  Vorname  "), "vorname")

    def test_collapses_double_spaces(self):
        self.assertEqual(
            _normalize_header_cell("date  of  birth"),
            "date of birth",
        )

    def test_none_returns_empty(self):
        self.assertEqual(_normalize_header_cell(None), "")


class FindHeaderIndicesTests(SimpleTestCase):
    def test_full_header_row(self):
        row = ["Vorname", "Nachname", "Geburtsdatum", "Telefon", "Email"]
        result = _find_header_indices(row)
        self.assertEqual(result["first_name"], 0)
        self.assertEqual(result["last_name"], 1)
        self.assertEqual(result["date_of_birth"], 2)
        self.assertEqual(result["phone"], 3)
        self.assertEqual(result["email"], 4)

    def test_full_name_column(self):
        row = ["Patient:in", "Geburtsdatum", "Tel", "E-Mail"]
        result = _find_header_indices(row)
        self.assertIn("full_name", result)
        self.assertIn("date_of_birth", result)

    def test_empty_row(self):
        self.assertEqual(_find_header_indices([]), {})

    def test_none_cells_skipped(self):
        row = [None, "Vorname", None, "Email"]
        result = _find_header_indices(row)
        self.assertEqual(result["first_name"], 1)
        self.assertEqual(result["email"], 3)


class ParseDateTests(SimpleTestCase):
    def test_dot_format(self):
        self.assertEqual(_parse_date("04.07.1996"), date(1996, 7, 4))

    def test_iso_format(self):
        self.assertEqual(_parse_date("1996-07-04"), date(1996, 7, 4))

    def test_slash_format(self):
        self.assertEqual(_parse_date("04/07/1996"), date(1996, 7, 4))

    def test_with_age_suffix(self):
        self.assertEqual(_parse_date("4.07.1996 (30 Jahre)"), date(1996, 7, 4))

    def test_german_textual_with_year(self):
        self.assertEqual(_parse_date("30. Dezember 2026"), date(2026, 12, 30))

    def test_german_textual_without_year_uses_default(self):
        result = _parse_date("Dienstag, 30. Dezember", default_year=2026)
        self.assertEqual(result, date(2026, 12, 30))

    def test_german_umlaut_month(self):
        self.assertEqual(_parse_date("15. März 2026"), date(2026, 3, 15))

    def test_empty_returns_none(self):
        self.assertIsNone(_parse_date(""))
        self.assertIsNone(_parse_date(None))

    def test_unparseable_returns_none(self):
        self.assertIsNone(_parse_date("not-a-date"))

    def test_invalid_german_date_returns_none(self):
        self.assertIsNone(_parse_date("32. Januar 2026"))


class ParseTimeTests(SimpleTestCase):
    def test_hh_mm(self):
        self.assertEqual(_parse_time("09:30"), time(9, 30))

    def test_hh_mm_ss(self):
        self.assertEqual(_parse_time("14:00:00"), time(14, 0, 0))

    def test_empty_returns_none(self):
        self.assertIsNone(_parse_time(""))
        self.assertIsNone(_parse_time(None))

    def test_invalid_returns_none(self):
        self.assertIsNone(_parse_time("25:99"))


class SplitFullNameTests(SimpleTestCase):
    def test_doctolib_format(self):
        first, last = _split_full_name("Frau KOWALSKI Anna Maria")
        self.assertEqual(last, "KOWALSKI")
        self.assertEqual(first, "Anna Maria")

    def test_herr_prefix(self):
        first, last = _split_full_name("Herr MULLER Max")
        self.assertEqual(last, "MULLER")
        self.assertEqual(first, "Max")

    def test_single_word(self):
        first, last = _split_full_name("Kowalski")
        self.assertEqual(first, "Kowalski")
        self.assertEqual(last, "")

    def test_empty(self):
        self.assertEqual(_split_full_name(""), ("", ""))
        self.assertEqual(_split_full_name(None), ("", ""))

    def test_only_title(self):
        self.assertEqual(_split_full_name("Frau"), ("", ""))


class TitleCaseNameTests(SimpleTestCase):
    def test_simple_name(self):
        self.assertEqual(_title_case_name("KOWALSKI"), "Kowalski")

    def test_hyphenated(self):
        self.assertEqual(
            _title_case_name("VON DER-MULLER"),
            "Von Der-Muller",
        )

    def test_apostrophe(self):
        self.assertEqual(_title_case_name("o'BRIEN"), "O'Brien")

    def test_empty(self):
        self.assertEqual(_title_case_name(""), "")
        self.assertEqual(_title_case_name(None), "")

    def test_extra_whitespace(self):
        self.assertEqual(_title_case_name("  JAN   MARIA  "), "Jan Maria")


class NormalizeSiteNameTests(SimpleTestCase):
    def test_removes_standort_prefix(self):
        self.assertEqual(
            _normalize_site_name("Standort Hamburg"),
            "hamburg",
        )

    def test_strips_non_alpha(self):
        self.assertEqual(
            _normalize_site_name("Kreutziger-Straße 12"),
            "kreutzigerstrasse12",
        )

    def test_handles_ss_ligature(self):
        self.assertEqual(_normalize_site_name("Straße"), "strasse")


class CleanupClinicNameTests(SimpleTestCase):
    def test_removes_trailing_date(self):
        self.assertEqual(
            _cleanup_clinic_name("Kreutzigerstraße Freitag, 6. März"),
            "Kreutzigerstraße",
        )

    def test_no_date_unchanged(self):
        self.assertEqual(
            _cleanup_clinic_name("Hamburg Zentrum"),
            "Hamburg Zentrum",
        )

    def test_strips_surrounding_separators(self):
        self.assertEqual(_cleanup_clinic_name(" , Hamburg ; "), "Hamburg")


class ValidateHeadersTests(SimpleTestCase):
    def test_valid_with_first_last(self):
        indices = {
            "first_name": 0,
            "last_name": 1,
            "date_of_birth": 2,
            "phone": 3,
            "email": 4,
        }
        _validate_headers(indices)

    def test_valid_with_full_name(self):
        indices = {
            "full_name": 0,
            "date_of_birth": 1,
            "phone": 2,
            "email": 3,
        }
        _validate_headers(indices)

    def test_missing_name_raises(self):
        indices = {
            "date_of_birth": 0,
            "phone": 1,
            "email": 2,
        }
        with self.assertRaises(XlsxImportFailure) as ctx:
            _validate_headers(indices)
        self.assertEqual(
            ctx.exception.error_code,
            XlsxImportErrorCode.TEMPLATE_HEADER_INVALID,
        )

    def test_missing_phone_raises(self):
        indices = {
            "first_name": 0,
            "date_of_birth": 1,
            "email": 2,
        }
        with self.assertRaises(XlsxImportFailure):
            _validate_headers(indices)

    def test_missing_email_raises(self):
        indices = {
            "first_name": 0,
            "date_of_birth": 1,
            "phone": 2,
        }
        with self.assertRaises(XlsxImportFailure):
            _validate_headers(indices)


class ExtractFileMetadataTests(SimpleTestCase):
    @freeze_time("2026-03-10")
    def test_extracts_date_and_clinic(self):
        rows = [
            ["Standort Hamburg"],
            ["10.03.2026"],
            [],
        ]
        queue_date, clinic_name = _extract_file_metadata(rows)
        self.assertEqual(queue_date, date(2026, 3, 10))
        self.assertEqual(clinic_name, "Hamburg")

    @freeze_time("2026-03-10")
    def test_standort_in_next_cell(self):
        rows = [
            ["Standort", "Berlin Mitte"],
            ["10.03.2026"],
        ]
        queue_date, clinic_name = _extract_file_metadata(rows)
        self.assertEqual(clinic_name, "Berlin Mitte")

    def test_missing_date_raises(self):
        rows = [["Standort Hamburg"], ["no date here"]]
        with self.assertRaises(XlsxImportFailure) as ctx:
            _extract_file_metadata(rows)
        self.assertEqual(
            ctx.exception.error_code,
            XlsxImportErrorCode.MISSING_IMPORT_DATE,
        )

    def test_missing_clinic_raises(self):
        rows = [["10.03.2026"], ["just data"]]
        with self.assertRaises(XlsxImportFailure) as ctx:
            _extract_file_metadata(rows)
        self.assertEqual(
            ctx.exception.error_code,
            XlsxImportErrorCode.MISSING_CLINIC_NAME,
        )

    @freeze_time("2026-03-10")
    def test_clinic_with_trailing_date_cleaned(self):
        rows = [
            ["Standort: Kreutzigerstraße Freitag, 6. März"],
            ["06.03.2026"],
        ]
        _, clinic_name = _extract_file_metadata(rows)
        self.assertEqual(clinic_name, "Kreutzigerstraße")


class NormalizeRowTests(SimpleTestCase):
    HEADERS = {
        "first_name": 0,
        "last_name": 1,
        "date_of_birth": 2,
        "phone": 3,
        "email": 4,
        "appointment_time": 5,
    }

    def test_valid_row(self):
        row = [
            "Jan",
            "Kowalski",
            "15.05.1990",
            "+48 500 100 200",
            "jan@example.com",
            "09:30",
        ]
        result = _normalize_row(2, row, self.HEADERS)
        self.assertIsInstance(result, NormalizedRow)
        self.assertEqual(result.first_name, "Jan")
        self.assertEqual(result.last_name, "Kowalski")
        self.assertEqual(result.date_of_birth, date(1990, 5, 15))
        self.assertEqual(result.phone, "48500100200")
        self.assertEqual(result.email, "jan@example.com")
        self.assertEqual(result.appointment_time, time(9, 30))

    def test_empty_name_returns_none(self):
        row = ["", "", "15.05.1990", "+48500100200", "a@b.com", ""]
        result = _normalize_row(2, row, self.HEADERS)
        self.assertIsNone(result)

    def test_partial_name_raises_missing_required(self):
        row = ["Jan", "", "15.05.1990", "+48500100200", "a@b.com", ""]
        with self.assertRaises(XlsxImportFailure) as ctx:
            _normalize_row(2, row, self.HEADERS)
        self.assertEqual(
            ctx.exception.error_code,
            XlsxImportErrorCode.MISSING_REQUIRED_FIELD,
        )

    def test_full_name_fallback(self):
        headers = {
            "full_name": 0,
            "date_of_birth": 1,
            "phone": 2,
            "email": 3,
        }
        row = [
            "Frau KOWALSKA Anna",
            "15.05.1990",
            "+48500100200",
            "a@b.com",
        ]
        result = _normalize_row(2, row, headers)
        self.assertEqual(result.first_name, "Anna")
        self.assertEqual(result.last_name, "Kowalska")

    def test_invalid_dob_raises(self):
        row = [
            "Jan",
            "K",
            "not-a-date",
            "+48500100200",
            "a@b.com",
            "",
        ]
        with self.assertRaises(XlsxImportFailure) as ctx:
            _normalize_row(2, row, self.HEADERS)
        self.assertEqual(
            ctx.exception.error_code,
            XlsxImportErrorCode.INVALID_DATE_OF_BIRTH,
        )

    def test_short_phone_raises(self):
        row = [
            "Jan",
            "K",
            "15.05.1990",
            "123",
            "a@b.com",
            "",
        ]
        with self.assertRaises(XlsxImportFailure) as ctx:
            _normalize_row(2, row, self.HEADERS)
        self.assertEqual(
            ctx.exception.error_code,
            XlsxImportErrorCode.INVALID_PHONE,
        )

    def test_missing_email_raises(self):
        row = [
            "Jan",
            "K",
            "15.05.1990",
            "+48500100200",
            "",
            "",
        ]
        with self.assertRaises(XlsxImportFailure) as ctx:
            _normalize_row(2, row, self.HEADERS)
        self.assertEqual(
            ctx.exception.error_code,
            XlsxImportErrorCode.MISSING_REQUIRED_FIELD,
        )

    def test_datetime_dob_handled(self):
        from datetime import datetime

        row = [
            "Jan",
            "K",
            datetime(1990, 5, 15),
            "+48500100200",
            "a@b.com",
            "",
        ]
        result = _normalize_row(2, row, self.HEADERS)
        self.assertEqual(result.date_of_birth, date(1990, 5, 15))

    def test_date_dob_handled(self):
        row = [
            "Jan",
            "K",
            date(1990, 5, 15),
            "+48500100200",
            "a@b.com",
            "",
        ]
        result = _normalize_row(2, row, self.HEADERS)
        self.assertEqual(result.date_of_birth, date(1990, 5, 15))

    def test_missing_column_returns_empty(self):
        headers = {
            "first_name": 0,
            "last_name": 1,
            "date_of_birth": 2,
            "phone": 3,
            "email": 4,
            "address": 99,
        }
        row = [
            "Jan",
            "K",
            "15.05.1990",
            "+48500100200",
            "a@b.com",
        ]
        result = _normalize_row(2, row, headers)
        self.assertIsNone(result.street)
