from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

import pdfplumber
try:
    import fitz  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - optional dependency
    fitz = None
from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.exceptions import DomainError, StateTransitionError

logger = logging.getLogger(__name__)

# Max length of extracted text to log (avoid huge payloads).
_EXTRACTED_TEXT_LOG_LIMIT = 2000
from apps.reception.models import (
    ClinicSite,
    ImportSourceSystem,
    ImportStatus,
    ImportType,
    Patient,
    PatientImportBatch,
    PatientImportError,
    QueueEntry,
    QueueShift,
    QueueSource,
)
from apps.reception.phone_utils import normalize_phone
from apps.reception.services import (
    create_daily_queue,
    create_or_update_patient_manual,
    create_queue_entry,
)

TIME_PATTERN = re.compile(r"^\d{1,2}:\d{2}$")
DATE_TOKEN_PATTERN = re.compile(r"\b\d{2}[./-]\d{2}[./-]\d{4}\b|\b\d{4}-\d{2}-\d{2}\b")
TEXTUAL_DATE_PATTERN = re.compile(
    r"\b(?:montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag)\s*,?\s*(?P<day>\d{1,2})\.\s*(?P<month>[a-zA-ZäöüÄÖÜ]+)(?:\s*(?P<year>\d{4}))?\b",
    re.IGNORECASE,
)
GERMAN_MONTHS = {
    "januar": 1,
    "februar": 2,
    "marz": 3,
    "april": 4,
    "mai": 5,
    "juni": 6,
    "juli": 7,
    "august": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "dezember": 12,
}


class PatientPdfImportErrorCode:
    PDF_PARSE_FAILED = "PDF_PARSE_FAILED"
    PDF_UNSUPPORTED_LAYOUT = "PDF_UNSUPPORTED_LAYOUT"
    MISSING_IMPORT_DATE = "MISSING_IMPORT_DATE"
    MISSING_CLINIC_NAME = "MISSING_CLINIC_NAME"
    UNKNOWN_CLINIC = "UNKNOWN_CLINIC"
    INVALID_ROW_FORMAT = "INVALID_ROW_FORMAT"
    INVALID_APPOINTMENT_TIME = "INVALID_APPOINTMENT_TIME"
    INVALID_DATE_OF_BIRTH = "INVALID_DATE_OF_BIRTH"
    AMBIGUOUS_FULL_NAME = "AMBIGUOUS_FULL_NAME"
    PATIENT_UNIQUENESS_CONFLICT = "PATIENT_UNIQUENESS_CONFLICT"
    DUPLICATE_VISIT = "DUPLICATE_VISIT"
    MISSING_QUEUE_IMPORT_CONFIG = "MISSING_QUEUE_IMPORT_CONFIG"
    AMBIGUOUS_CLINIC = "AMBIGUOUS_CLINIC"


class PatientPdfImportFailure(DomainError):
    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


class PatientPdfImportRowFailure(PatientPdfImportFailure):
    def __init__(
        self,
        *,
        row_number: int,
        error_code: str,
        message: str,
        raw_row: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(error_code, message)
        self.row_number = row_number
        self.raw_row = raw_row


@dataclass(frozen=True)
class ExtractedWord:
    text: str
    x0: float
    x1: float
    top: float
    bottom: float
    page_number: int


@dataclass(frozen=True)
class ExtractedLine:
    page_number: int
    words: tuple[ExtractedWord, ...]
    text: str


@dataclass(frozen=True)
class ExtractedPdfDocument:
    lines: tuple[ExtractedLine, ...]
    full_text: str


@dataclass(frozen=True)
class ParsedPatientRow:
    row_number: int
    appointment_time_raw: str
    full_name_raw: str
    phone_raw: str
    date_of_birth_raw: str
    email_raw: str
    address_raw: str
    postal_code_raw: str


@dataclass(frozen=True)
class ParsedPdfImport:
    import_date: date
    clinic_name: str
    rows: tuple[ParsedPatientRow, ...]


@dataclass(frozen=True)
class NormalizedPatientRow:
    row_number: int
    appointment_time: datetime
    first_name: str
    last_name: str
    phone: str
    date_of_birth: date
    email: str
    street: str | None
    postal_code: str | None
    city: str | None
    country_code: str


@dataclass(frozen=True)
class StoredPdfUpload:
    source_file_name: str
    source_file_sha256: str
    stored_file_path: str


def _normalize_label(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_value = "".join(char for char in normalized if not unicodedata.combining(char))
    ascii_value = ascii_value.replace("ß", "ss").replace("ẞ", "SS")
    return re.sub(r"\s+", " ", ascii_value).strip().lower()


def _normalize_clinic_name_for_matching(value: str) -> str:
    normalized = _normalize_label(value)
    normalized = re.sub(r"^(standort|clinic|klinika|location|site|placowka)\s+", "", normalized)
    return normalized.strip(" -:|,")


def _sanitize_pdf_text(value: str) -> str:
    cleaned = re.sub(r"\(cid:\d+\)", "", value or "")
    return re.sub(r"\s+", " ", cleaned).strip()


def _full_text_for_layout_check(document: ExtractedPdfDocument) -> str:
    """
    Text used for layout validation. Strips (cid:N) placeholders so that
    CID-encoded PDFs don't match literal '(cid:0)' etc.; after stripping,
    if the PDF had real text mixed in, it can still match.
    """
    return _sanitize_pdf_text(document.full_text)


def _is_likely_cid_encoded(full_text: str, sanitized: str) -> bool:
    """True if PDF appears to be mostly CID-encoded (no usable text after stripping CIDs)."""
    if not full_text or len(sanitized) > 100:
        return False
    cid_count = len(re.findall(r"\(cid:\d+\)", full_text))
    return cid_count > 20 and len(sanitized.strip()) < 50


def _strip_date_fragments(value: str) -> str:
    cleaned = DATE_TOKEN_PATTERN.sub("", value or "")
    cleaned = TEXTUAL_DATE_PATTERN.sub("", cleaned)
    return _sanitize_pdf_text(cleaned).strip(" -:|,")


# Alias table for Doctolib PDF import: one logical column can match multiple header strings (DE/PL/EN).
# Keys are internal column names; values are tuples of normalized labels accepted for that column.
DOCTOLIB_IMPORT_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "appointment_time_raw": ("godzina", "uhrzeit"),
    "full_name_raw": ("imie nazwisko", "patient:in", "patientin", "patient", "imie"),
    "phone_raw": ("telefon",),
    "date_of_birth_raw": ("data urodzenia", "geburtsdatum", "data"),
    "email_raw": ("email", "e-mail-adresse"),
    "address_raw": ("adres", "anschrift"),
    "postal_code_raw": ("kod pocztowy", "postleitzahl", "kod"),
}
DOCTOLIB_IMPORT_COLUMN_ORDER = (
    "appointment_time_raw",
    "full_name_raw",
    "phone_raw",
    "date_of_birth_raw",
    "email_raw",
    "address_raw",
    "postal_code_raw",
)


def _normalized_text_has_column(normalized_text: str, column_key: str) -> bool:
    """Return True if normalized_text contains any alias for the given column."""
    return any(
        alias in normalized_text for alias in DOCTOLIB_IMPORT_COLUMN_ALIASES[column_key]
    )


def _label_matches_column(normalized_label: str, column_key: str) -> bool:
    """Return True if a single header word/label matches any alias for the column."""
    return normalized_label in DOCTOLIB_IMPORT_COLUMN_ALIASES[column_key]


def _document_quality_score(document: ExtractedPdfDocument) -> tuple[int, int, int, int]:
    """
    Rank extraction quality so we can choose the more readable backend.
    Prefer documents that expose expected headers and contain more letters.
    """
    normalized_text = _normalize_label(_full_text_for_layout_check(document))
    alias_hits = sum(
        1 for column_key in DOCTOLIB_IMPORT_COLUMN_ORDER if _normalized_text_has_column(normalized_text, column_key)
    )
    best_line_alias_hits = 0
    for line in document.lines:
        normalized_line = _normalize_label(_sanitize_pdf_text(line.text))
        if not normalized_line:
            continue
        line_alias_hits = sum(
            1 for column_key in DOCTOLIB_IMPORT_COLUMN_ORDER if _normalized_text_has_column(normalized_line, column_key)
        )
        best_line_alias_hits = max(best_line_alias_hits, line_alias_hits)
    alpha_chars = sum(1 for char in normalized_text if char.isalpha())
    return (alias_hits, best_line_alias_hits, alpha_chars, len(normalized_text))


def _log_extracted_pdf_text(
    file_path: str | Path | None,
    document: ExtractedPdfDocument,
    *,
    normalized_text: str | None = None,
    missing_columns: list[str] | None = None,
) -> None:
    """Log extracted and normalized PDF text for debugging layout validation."""
    path_str = str(file_path) if file_path else "unknown"
    norm = (
        normalized_text
        if normalized_text is not None
        else _normalize_label(_full_text_for_layout_check(document))
    )
    snippet = norm[:_EXTRACTED_TEXT_LOG_LIMIT]
    if len(norm) > _EXTRACTED_TEXT_LOG_LIMIT:
        snippet += f" ... [truncated, total {len(norm)} chars]"
    if not missing_columns:
        logger.info(
            "PDF import extracted text: path=%s, full_text_len=%s, normalized_preview=%s",
            path_str,
            len(document.full_text),
            repr(snippet),
        )
    if missing_columns:
        logger.warning(
            "PDF import layout validation failed: path=%s, missing_columns=%s, normalized_text_preview=%s",
            path_str,
            missing_columns,
            repr(snippet),
        )


def _group_words_into_lines(words: list[ExtractedWord], *, y_tolerance: float = 3.0) -> list[ExtractedLine]:
    if not words:
        return []
    sorted_words = sorted(words, key=lambda word: (round(word.top, 1), word.x0))
    grouped: list[list[ExtractedWord]] = []
    current_group: list[ExtractedWord] = []
    current_top: float | None = None
    for word in sorted_words:
        if current_top is None or abs(word.top - current_top) <= y_tolerance:
            current_group.append(word)
            current_top = word.top if current_top is None else current_top
            continue
        grouped.append(sorted(current_group, key=lambda item: item.x0))
        current_group = [word]
        current_top = word.top
    if current_group:
        grouped.append(sorted(current_group, key=lambda item: item.x0))
    return [
        ExtractedLine(
            page_number=line_words[0].page_number,
            words=tuple(line_words),
            text=" ".join(word.text.strip() for word in line_words if word.text.strip()),
        )
        for line_words in grouped
    ]


class PdfTextExtractor:
    def extract(self, file_path: str | Path) -> ExtractedPdfDocument:
        pdfplumber_document: ExtractedPdfDocument | None = None
        pdfplumber_error: Exception | None = None

        try:
            pdfplumber_document = self._extract_with_pdfplumber(file_path)
        except Exception as exc:
            pdfplumber_error = exc

        if fitz is not None and Path(file_path).exists():
            try:
                pymupdf_document = self._extract_with_pymupdf(file_path)
            except Exception as exc:
                if pdfplumber_document is None:
                    raise PatientPdfImportFailure(
                        PatientPdfImportErrorCode.PDF_PARSE_FAILED,
                        f"Could not read PDF file: {exc}",
                    ) from exc
                logger.warning("PyMuPDF fallback extraction failed for %s: %s", file_path, exc)
            else:
                if pdfplumber_document is None:
                    logger.info("PDF import extractor selected: path=%s, extractor=pymupdf", file_path)
                    return pymupdf_document
                if _document_quality_score(pymupdf_document) > _document_quality_score(pdfplumber_document):
                    logger.info("PDF import extractor selected: path=%s, extractor=pymupdf", file_path)
                    return pymupdf_document

        if pdfplumber_document is not None:
            return pdfplumber_document
        if pdfplumber_error is not None:
            raise PatientPdfImportFailure(
                PatientPdfImportErrorCode.PDF_PARSE_FAILED,
                f"Could not read PDF file: {pdfplumber_error}",
            ) from pdfplumber_error
        raise PatientPdfImportFailure(
            PatientPdfImportErrorCode.PDF_PARSE_FAILED,
            "Could not read PDF file.",
        )

    def _extract_with_pdfplumber(self, file_path: str | Path) -> ExtractedPdfDocument:
        lines: list[ExtractedLine] = []
        full_text_parts: list[str] = []
        with pdfplumber.open(str(file_path)) as pdf:
            for page_number, page in enumerate(pdf.pages, start=1):
                page_text = page.extract_text() or ""
                full_text_parts.append(page_text)
                page_words = [
                    ExtractedWord(
                        text=str(word.get("text", "")).strip(),
                        x0=float(word.get("x0", 0.0)),
                        x1=float(word.get("x1", 0.0)),
                        top=float(word.get("top", 0.0)),
                        bottom=float(word.get("bottom", 0.0)),
                        page_number=page_number,
                    )
                    for word in page.extract_words(use_text_flow=True, keep_blank_chars=False)
                    if str(word.get("text", "")).strip()
                ]
                lines.extend(_group_words_into_lines(page_words))
        return ExtractedPdfDocument(
            lines=tuple(lines),
            full_text="\n".join(part for part in full_text_parts if part),
        )

    def _extract_with_pymupdf(self, file_path: str | Path) -> ExtractedPdfDocument:
        if fitz is None:  # pragma: no cover - guarded by caller
            raise RuntimeError("PyMuPDF is not installed")
        lines: list[ExtractedLine] = []
        full_text_parts: list[str] = []
        with fitz.open(str(file_path)) as pdf:
            for page_number, page in enumerate(pdf, start=1):
                page_text = page.get_text("text", sort=True) or ""
                full_text_parts.append(page_text)
                page_words = [
                    ExtractedWord(
                        text=str(word[4]).strip(),
                        x0=float(word[0]),
                        x1=float(word[2]),
                        top=float(word[1]),
                        bottom=float(word[3]),
                        page_number=page_number,
                    )
                    for word in page.get_text("words", sort=True)
                    if len(word) >= 5 and str(word[4]).strip()
                ]
                lines.extend(_group_words_into_lines(page_words))
        return ExtractedPdfDocument(
            lines=tuple(lines),
            full_text="\n".join(part for part in full_text_parts if part),
        )


class DoctolibPdfLayoutDetector:
    """Validates that the PDF contains the expected Doctolib table header (all columns via alias table)."""

    def validate(self, document: ExtractedPdfDocument, file_path: str | Path | None = None) -> None:
        text_for_layout = _full_text_for_layout_check(document)
        normalized_text = _normalize_label(text_for_layout)
        missing: list[str] = []
        for column_key in DOCTOLIB_IMPORT_COLUMN_ORDER:
            if not _normalized_text_has_column(normalized_text, column_key):
                aliases = DOCTOLIB_IMPORT_COLUMN_ALIASES[column_key]
                missing.append(f"one of: {', '.join(aliases)}")
        if not missing:
            return
        _log_extracted_pdf_text(file_path, document, normalized_text=normalized_text, missing_columns=missing)
        msg = (
            "PDF layout does not match the expected Doctolib export. Missing in PDF: "
            + "; ".join(missing)
            + ". Expected: table header with Uhrzeit/Godzina, Patient:in/Imię Nazwisko, Telefon, Geburtsdatum, E-Mail, Anschrift, Postleitzahl (DE/PL)."
        )
        if _is_likely_cid_encoded(document.full_text, text_for_layout):
            msg += (
                " This PDF appears to use CID-encoded fonts (text not extractable). "
                "Try re-exporting from Doctolib (e.g. 'Print to PDF' with 'Background graphics') or use a different browser/PDF export."
            )
        raise PatientPdfImportFailure(PatientPdfImportErrorCode.PDF_UNSUPPORTED_LAYOUT, msg)


class DoctolibPdfParser:
    def __init__(
        self,
        *,
        extractor: PdfTextExtractor | None = None,
        layout_detector: DoctolibPdfLayoutDetector | None = None,
    ) -> None:
        self.extractor = extractor or PdfTextExtractor()
        self.layout_detector = layout_detector or DoctolibPdfLayoutDetector()

    def parse(self, file_path: str | Path) -> ParsedPdfImport:
        document = self.extractor.extract(file_path)
        _log_extracted_pdf_text(file_path, document)
        self.layout_detector.validate(document, file_path)

        lines = [line for line in document.lines if line.text.strip()]
        header_index = self._find_header_index(lines)
        preamble_lines = lines[:header_index]
        import_date = self._extract_import_date(preamble_lines)
        clinic_name = self._extract_clinic_name(preamble_lines)
        column_ranges = self._build_column_ranges(lines[header_index])
        parsed_rows: list[ParsedPatientRow] = []
        row_number = 1

        for line in lines[header_index + 1 :]:
            normalized_line = _normalize_label(_sanitize_pdf_text(line.text))
            if not normalized_line:
                continue
            if _normalized_text_has_column(normalized_line, "full_name_raw") and _normalized_text_has_column(
                normalized_line, "phone_raw"
            ):
                continue
            if not line.words or not TIME_PATTERN.fullmatch(line.words[0].text.strip()):
                continue
            parsed_rows.append(
                ParsedPatientRow(
                    row_number=row_number,
                    **self._parse_row_values(line, column_ranges),
                )
            )
            row_number += 1

        if not parsed_rows:
            raise PatientPdfImportFailure(
                PatientPdfImportErrorCode.INVALID_ROW_FORMAT,
                "No patient rows were found in the PDF.",
            )

        return ParsedPdfImport(
            import_date=import_date,
            clinic_name=clinic_name,
            rows=tuple(parsed_rows),
        )

    def _find_header_index(self, lines: list[ExtractedLine]) -> int:
        for index, line in enumerate(lines):
            normalized = _normalize_label(_sanitize_pdf_text(line.text))
            if all(_normalized_text_has_column(normalized, col) for col in DOCTOLIB_IMPORT_COLUMN_ORDER):
                return index
        raise PatientPdfImportFailure(
            PatientPdfImportErrorCode.PDF_UNSUPPORTED_LAYOUT,
            "Could not locate the patient table header in the PDF.",
        )

    def _extract_import_date(self, preamble_lines: list[ExtractedLine]) -> date:
        for line in preamble_lines:
            if match := DATE_TOKEN_PATTERN.search(line.text):
                return _parse_date_value(match.group(0))
            normalized_line = _normalize_label(line.text)
            if textual_match := TEXTUAL_DATE_PATTERN.search(normalized_line):
                return _parse_textual_date_value(
                    day=textual_match.group("day"),
                    month=textual_match.group("month"),
                    year=textual_match.group("year"),
                )
        raise PatientPdfImportFailure(
            PatientPdfImportErrorCode.MISSING_IMPORT_DATE,
            "Import date was not found in the PDF header.",
        )

    def _extract_clinic_name(self, preamble_lines: list[ExtractedLine]) -> str:
        patterns = (
            re.compile(r"(?:clinic|klinika|standort|location)\s*[:\-]?\s*(?P<value>.+)$", re.I),
            re.compile(r"(?:site|placowka)\s*[:\-]\s*(?P<value>.+)$", re.I),
        )
        for line in preamble_lines:
            stripped = line.text.strip()
            for pattern in patterns:
                match = pattern.search(stripped)
                if match:
                    clinic_name = _strip_date_fragments(match.group("value"))
                    if clinic_name:
                        return clinic_name
        for line in reversed(preamble_lines):
            stripped = _strip_date_fragments(line.text)
            normalized = _normalize_label(stripped)
            if not stripped:
                continue
            if any(marker in normalized for marker in ("data", "date", "datum", "godzina", "telefon")):
                continue
            return stripped
        raise PatientPdfImportFailure(
            PatientPdfImportErrorCode.MISSING_CLINIC_NAME,
            "Clinic name was not found in the PDF header.",
        )

    def _build_column_ranges(self, header_line: ExtractedLine) -> dict[str, tuple[float, float | None]]:
        header_starts: list[tuple[str, float]] = []
        for word in header_line.words:
            label = _normalize_label(_sanitize_pdf_text(word.text))
            for column_key in DOCTOLIB_IMPORT_COLUMN_ORDER:
                if _label_matches_column(label, column_key):
                    header_starts.append((column_key, word.x0))
                    break
        found_columns = [column_name for column_name, _ in header_starts]
        if found_columns != list(DOCTOLIB_IMPORT_COLUMN_ORDER):
            raise PatientPdfImportFailure(
                PatientPdfImportErrorCode.PDF_UNSUPPORTED_LAYOUT,
                "Could not determine PDF column positions.",
            )
        column_ranges: dict[str, tuple[float, float | None]] = {}
        for index, (column_name, x0) in enumerate(header_starts):
            next_x0 = header_starts[index + 1][1] if index + 1 < len(header_starts) else None
            column_ranges[column_name] = (x0, next_x0)
        return column_ranges

    def _parse_row_values(
        self,
        line: ExtractedLine,
        column_ranges: dict[str, tuple[float, float | None]],
    ) -> dict[str, str]:
        values: dict[str, list[str]] = {column_name: [] for column_name in column_ranges}
        for word in line.words:
            for column_name, (start_x0, end_x0) in column_ranges.items():
                if word.x0 >= start_x0 and (end_x0 is None or word.x0 < end_x0):
                    values[column_name].append(word.text.strip())
                    break
        parsed_values = {
            key: _sanitize_pdf_text(" ".join(part for part in parts if part).strip())
            for key, parts in values.items()
        }
        required_columns = {
            "appointment_time_raw",
            "full_name_raw",
            "phone_raw",
            "date_of_birth_raw",
            "email_raw",
        }
        if any(not parsed_values[column_name] for column_name in required_columns):
            raise PatientPdfImportFailure(
                PatientPdfImportErrorCode.INVALID_ROW_FORMAT,
                f"Could not parse all columns for line: {line.text}",
            )
        return parsed_values


def _parse_date_value(value: str) -> date:
    normalized = _sanitize_pdf_text(value)
    if match := DATE_TOKEN_PATTERN.search(normalized):
        normalized = match.group(0)
    for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(normalized, fmt).date()
        except ValueError:
            continue
    raise PatientPdfImportFailure(
        PatientPdfImportErrorCode.INVALID_DATE_OF_BIRTH,
        f"Invalid date value: {value}",
    )


def _parse_textual_date_value(*, day: str, month: str, year: str | None) -> date:
    month_key = _normalize_label(month)
    month_number = GERMAN_MONTHS.get(month_key)
    if month_number is None:
        raise PatientPdfImportFailure(
            PatientPdfImportErrorCode.INVALID_DATE_OF_BIRTH,
            f"Invalid textual date month: {month}",
        )
    parsed_year = int(year) if year else timezone.localdate().year
    return date(parsed_year, month_number, int(day))


def _parse_time_value(value: str) -> time:
    try:
        return datetime.strptime(value.strip(), "%H:%M").time()
    except ValueError as exc:
        raise PatientPdfImportFailure(
            PatientPdfImportErrorCode.INVALID_APPOINTMENT_TIME,
            f"Invalid appointment time: {value}",
        ) from exc


def normalize_patient_row(*, parsed_row: ParsedPatientRow, import_date: date) -> NormalizedPatientRow:
    first_name, last_name = _split_full_name(parsed_row.full_name_raw)
    if not first_name or not last_name:
        raise PatientPdfImportRowFailure(
            row_number=parsed_row.row_number,
            error_code=PatientPdfImportErrorCode.AMBIGUOUS_FULL_NAME,
            message=f"Could not split full name: {parsed_row.full_name_raw}",
            raw_row=asdict(parsed_row),
        )

    try:
        appointment_time = timezone.make_aware(
            datetime.combine(import_date, _parse_time_value(parsed_row.appointment_time_raw)),
            timezone.get_current_timezone(),
        )
    except PatientPdfImportFailure as exc:
        raise PatientPdfImportRowFailure(
            row_number=parsed_row.row_number,
            error_code=exc.error_code,
            message=str(exc),
            raw_row=asdict(parsed_row),
        ) from exc

    try:
        date_of_birth = _parse_date_value(parsed_row.date_of_birth_raw)
    except PatientPdfImportFailure as exc:
        raise PatientPdfImportRowFailure(
            row_number=parsed_row.row_number,
            error_code=exc.error_code,
            message=str(exc),
            raw_row=asdict(parsed_row),
        ) from exc

    email = _sanitize_pdf_text(parsed_row.email_raw).lower()
    if not email:
        raise PatientPdfImportRowFailure(
            row_number=parsed_row.row_number,
            error_code=PatientPdfImportErrorCode.INVALID_ROW_FORMAT,
            message="Email is required for patient import.",
            raw_row=asdict(parsed_row),
        )

    phone = _normalize_phone(parsed_row.phone_raw)
    if len(phone) < 7:
        raise PatientPdfImportRowFailure(
            row_number=parsed_row.row_number,
            error_code=PatientPdfImportErrorCode.INVALID_ROW_FORMAT,
            message=f"Invalid phone value: {parsed_row.phone_raw}",
            raw_row=asdict(parsed_row),
        )

    return NormalizedPatientRow(
        row_number=parsed_row.row_number,
        appointment_time=appointment_time,
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        date_of_birth=date_of_birth,
        email=email,
        street=_sanitize_pdf_text(parsed_row.address_raw) or None,
        postal_code=_sanitize_pdf_text(parsed_row.postal_code_raw) or None,
        city=None,
        country_code="DE",
    )


def _normalize_phone(value: str) -> str:
    stripped = _sanitize_pdf_text(value)
    digits_only = re.sub(r"[^\d]", "", stripped)
    if stripped.startswith("+"):
        return f"+{digits_only}"
    return digits_only


def _sanitize_name_token(value: str) -> str:
    allowed_separators = {"-", "'", "’"}
    cleaned_chars: list[str] = []
    for char in _sanitize_pdf_text(value):
        if char.isalpha() or char in allowed_separators:
            cleaned_chars.append(char)
    cleaned = "".join(cleaned_chars).strip("-'’")
    return cleaned


def _split_full_name(value: str) -> tuple[str | None, str | None]:
    honorifics = {"herr", "frau", "mr", "mrs", "ms"}
    raw_parts = [_sanitize_name_token(part) for part in value.split() if _sanitize_name_token(part)]
    parts = [part for part in raw_parts if _normalize_label(part) not in honorifics]
    if len(parts) < 2:
        return None, None
    if _looks_like_last_name_first(parts):
        first_name = parts[-1]
        last_name = " ".join(parts[:-1])
        return first_name, last_name
    first_name = parts[0]
    last_name = " ".join(parts[1:])
    return first_name, last_name


def _looks_like_last_name_first(parts: list[str]) -> bool:
    if len(parts) < 2:
        return False
    leading_parts = parts[:-1]
    trailing_part = parts[-1]
    return all(_is_likely_surname_token(part) for part in leading_parts) and not _is_likely_surname_token(trailing_part)


def _is_likely_surname_token(value: str) -> bool:
    letters_only = re.sub(r"[^A-Za-zÄÖÜäöüß-]", "", value)
    return bool(letters_only) and letters_only.upper() == letters_only


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def store_uploaded_patient_pdf(uploaded_file) -> StoredPdfUpload:
    target_dir = Path(settings.MEDIA_ROOT) / "imports" / "patients_pdf"
    target_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(uploaded_file.name or "import.pdf").suffix or ".pdf"
    stored_path = target_dir / f"{uuid.uuid4()}{suffix.lower()}"
    sha256 = hashlib.sha256()
    with stored_path.open("wb") as destination:
        for chunk in uploaded_file.chunks():
            sha256.update(chunk)
            destination.write(chunk)
    return StoredPdfUpload(
        source_file_name=uploaded_file.name or stored_path.name,
        source_file_sha256=sha256.hexdigest(),
        stored_file_path=str(stored_path),
    )


def enqueue_patient_pdf_import(*, uploaded_file, created_by_user) -> PatientImportBatch:
    stored_pdf = store_uploaded_patient_pdf(uploaded_file)
    batch = PatientImportBatch.objects.create(
        source_file_name=stored_pdf.source_file_name,
        source_file_sha256=stored_pdf.source_file_sha256,
        import_type=ImportType.DAILY_FILE_IMPORT,
        source_system=ImportSourceSystem.DOCTOLIB_EXPORT,
        status=ImportStatus.PROCESSING,
        created_by_user=created_by_user,
    )
    try:
        from apps.reception.tasks import run_patient_pdf_import

        run_patient_pdf_import.enqueue(str(batch.id), stored_pdf.stored_file_path)
    except Exception:
        batch.status = ImportStatus.FAILED
        batch.finished_at = timezone.now()
        batch.save(update_fields=["status", "finished_at"])
        Path(stored_pdf.stored_file_path).unlink(missing_ok=True)
        raise
    return batch


def process_patient_pdf_import_batch(*, batch_id: uuid.UUID, stored_file_path: str) -> None:
    batch = PatientImportBatch.objects.select_related("created_by_user").get(id=batch_id)
    parser = DoctolibPdfParser()
    try:
        parsed_import = parser.parse(stored_file_path)
        batch.total_rows = len(parsed_import.rows)
        batch.save(update_fields=["total_rows"])

        clinic_site = _resolve_clinic_site(
            parsed_import.clinic_name
        )
        if clinic_site.pdf_import_default_consulting_room_id is None:
            raise PatientPdfImportFailure(
                PatientPdfImportErrorCode.MISSING_QUEUE_IMPORT_CONFIG,
                f"Clinic '{clinic_site.name}' has no default consulting room configured for PDF import.",
            )

        daily_queue = _get_or_create_import_queue(
            queue_date=parsed_import.import_date,
            clinic_site=clinic_site,
            created_by_user_id=batch.created_by_user_id,
        )

        inserted_rows = 0
        error_rows = 0
        for parsed_row in parsed_import.rows:
            try:
                normalized_row = normalize_patient_row(parsed_row=parsed_row, import_date=parsed_import.import_date)
                _create_import_row(
                    batch=batch,
                    clinic_site=clinic_site,
                    daily_queue_id=daily_queue.id,
                    normalized_row=normalized_row,
                )
                inserted_rows += 1
            except PatientPdfImportRowFailure as exc:
                _create_import_error(
                    batch=batch,
                    row_number=exc.row_number,
                    error_code=exc.error_code,
                    error_message=str(exc),
                    raw_row=exc.raw_row,
                )
                error_rows += 1

        batch.inserted_rows = inserted_rows
        batch.error_rows = error_rows
        batch.status = (
            ImportStatus.COMPLETED_WITH_ERRORS if error_rows else ImportStatus.COMPLETED
        )
        batch.finished_at = timezone.now()
        batch.save(
            update_fields=[
                "inserted_rows",
                "error_rows",
                "status",
                "finished_at",
            ]
        )
        logger.info(
            "PDF import completed: batch_id=%s, path=%s, clinic=%s, import_date=%s, total_rows=%s, inserted=%s, errors=%s",
            batch_id,
            stored_file_path,
            parsed_import.clinic_name,
            parsed_import.import_date.isoformat(),
            batch.total_rows,
            inserted_rows,
            error_rows,
        )
    except PatientPdfImportFailure as exc:
        _mark_batch_failed(batch=batch, error_code=exc.error_code, message=str(exc))
    except Exception as exc:
        _mark_batch_failed(
            batch=batch,
            error_code=PatientPdfImportErrorCode.PDF_PARSE_FAILED,
            message=f"Unexpected import failure: {exc}",
        )
        raise
    finally:
        Path(stored_file_path).unlink(missing_ok=True)


def _get_or_create_import_queue(
    *,
    queue_date: date,
    clinic_site: ClinicSite,
    created_by_user_id: uuid.UUID,
):
    existing_queue = clinic_site.daily_queues.filter(
        queue_date=queue_date,
        consulting_room_id=clinic_site.pdf_import_default_consulting_room_id,
        shift_code=clinic_site.pdf_import_shift_code,
    ).first()
    if existing_queue:
        return existing_queue
    try:
        return create_daily_queue(
            queue_date=queue_date,
            clinic_site_id=clinic_site.id,
            consulting_room_id=clinic_site.pdf_import_default_consulting_room_id,
            shift_code=clinic_site.pdf_import_shift_code,
            created_by_user_id=created_by_user_id,
            source=QueueSource.IMPORT,
        )
    except StateTransitionError:
        return clinic_site.daily_queues.get(
            queue_date=queue_date,
            consulting_room_id=clinic_site.pdf_import_default_consulting_room_id,
            shift_code=clinic_site.pdf_import_shift_code,
        )


def _resolve_clinic_site(clinic_name: str) -> ClinicSite:
    normalized_target = _normalize_clinic_name_for_matching(clinic_name)
    matches = [
        clinic_site
        for clinic_site in ClinicSite.objects.select_related("pdf_import_default_consulting_room").all()
        if _normalize_clinic_name_for_matching(clinic_site.name) == normalized_target
    ]
    if not matches:
        raise PatientPdfImportFailure(
            PatientPdfImportErrorCode.UNKNOWN_CLINIC,
            f"Clinic from PDF could not be mapped to an existing ClinicSite: {clinic_name}",
        )
    if len(matches) > 1:
        raise PatientPdfImportFailure(
            PatientPdfImportErrorCode.AMBIGUOUS_CLINIC,
            f"Clinic name from PDF matches multiple ClinicSite records: {clinic_name}",
        )
    return matches[0]


def _create_import_row(
    *,
    batch: PatientImportBatch,
    clinic_site: ClinicSite,
    daily_queue_id: uuid.UUID,
    normalized_row: NormalizedPatientRow,
) -> None:
    with transaction.atomic():
        patient = _upsert_patient_for_import(
            clinic_site=clinic_site,
            normalized_row=normalized_row,
            created_by_user_id=batch.created_by_user_id,
        )
        visit_external_id = _build_visit_external_id(
            clinic_site_id=clinic_site.id,
            normalized_row=normalized_row,
        )
        if QueueEntry.objects.filter(
            daily_queue_id=daily_queue_id,
            visit_external_id=visit_external_id,
        ).exists():
            raise PatientPdfImportRowFailure(
                row_number=normalized_row.row_number,
                error_code=PatientPdfImportErrorCode.DUPLICATE_VISIT,
                message="Visit already exists for this queue slot and patient.",
                raw_row=asdict(normalized_row),
            )
        try:
            create_queue_entry(
                daily_queue_id=daily_queue_id,
                patient_id=patient.id,
                created_by_user_id=batch.created_by_user_id,
                appointment_time=normalized_row.appointment_time,
                visit_external_id=visit_external_id,
            )
        except IntegrityError as exc:
            raise PatientPdfImportRowFailure(
                row_number=normalized_row.row_number,
                error_code=PatientPdfImportErrorCode.DUPLICATE_VISIT,
                message="Visit already exists for this queue slot and patient.",
                raw_row=asdict(normalized_row),
            ) from exc


def _upsert_patient_for_import(
    *,
    clinic_site: ClinicSite,
    normalized_row: NormalizedPatientRow,
    created_by_user_id: uuid.UUID,
) -> Patient:
    phone_norm = normalize_phone(normalized_row.phone)
    existing_patient = None
    if phone_norm:
        existing_patient = Patient.objects.filter(
            first_name=normalized_row.first_name,
            last_name=normalized_row.last_name,
            date_of_birth=normalized_row.date_of_birth,
            phone=phone_norm,
        ).first()
        if not existing_patient:
            existing_patient = Patient.objects.filter(phone=phone_norm).first()
    try:
        patient = create_or_update_patient_manual(
            patient_id=existing_patient.id if existing_patient else None,
            first_name=normalized_row.first_name,
            last_name=normalized_row.last_name,
            date_of_birth=normalized_row.date_of_birth,
            phone=phone_norm or normalized_row.phone,
            email=normalized_row.email,
            created_or_updated_by_user_id=created_by_user_id,
        )
    except IntegrityError as exc:
        raise PatientPdfImportRowFailure(
            row_number=normalized_row.row_number,
            error_code=PatientPdfImportErrorCode.PATIENT_UNIQUENESS_CONFLICT,
            message="Patient uniqueness conflict while importing row.",
            raw_row=asdict(normalized_row),
        ) from exc

    patient.street = normalized_row.street
    patient.postal_code = normalized_row.postal_code
    patient.city = normalized_row.city
    patient.country_code = normalized_row.country_code
    patient.save(update_fields=["street", "postal_code", "city", "country_code", "updated_at"])
    patient.clinic_sites.add(clinic_site)
    return patient


def _build_visit_external_id(*, clinic_site_id: uuid.UUID, normalized_row: NormalizedPatientRow) -> str:
    identity = "|".join(
        [
            str(clinic_site_id),
            normalized_row.appointment_time.isoformat(),
            normalized_row.first_name,
            normalized_row.last_name,
            normalized_row.phone,
            normalized_row.date_of_birth.isoformat(),
        ]
    )
    return f"pdf:{hashlib.sha256(identity.encode('utf-8')).hexdigest()}"


def _create_import_error(
    *,
    batch: PatientImportBatch,
    row_number: int,
    error_code: str,
    error_message: str,
    raw_row: dict[str, Any] | None,
) -> None:
    PatientImportError.objects.create(
        batch=batch,
        row_number=max(1, row_number),
        error_code=error_code,
        error_message=error_message,
        raw_row=_json_safe(raw_row),
    )


def _mark_batch_failed(*, batch: PatientImportBatch, error_code: str, message: str) -> None:
    _create_import_error(
        batch=batch,
        row_number=1,
        error_code=error_code,
        error_message=message,
        raw_row=None,
    )
    batch.error_rows = max(batch.error_rows, 1)
    batch.status = ImportStatus.FAILED
    batch.finished_at = timezone.now()
    batch.save(update_fields=["error_rows", "status", "finished_at"])
