from __future__ import annotations

import hashlib
import re
import unicodedata
import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

import pdfplumber
from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.exceptions import DomainError, StateTransitionError
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
    return re.sub(r"\s+", " ", ascii_value).strip().lower()


def _sanitize_pdf_text(value: str) -> str:
    cleaned = re.sub(r"\(cid:\d+\)", "", value or "")
    return re.sub(r"\s+", " ", cleaned).strip()


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
        lines: list[ExtractedLine] = []
        full_text_parts: list[str] = []
        try:
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
        except PatientPdfImportFailure:
            raise
        except Exception as exc:
            raise PatientPdfImportFailure(
                PatientPdfImportErrorCode.PDF_PARSE_FAILED,
                f"Could not read PDF file: {exc}",
            ) from exc
        return ExtractedPdfDocument(
            lines=tuple(lines),
            full_text="\n".join(part for part in full_text_parts if part),
        )


class DoctolibPdfLayoutDetector:
    REQUIRED_MARKERS = (
        ("godzina", "uhrzeit"),
        "telefon",
        ("email", "e-mail-adresse"),
        ("adres", "anschrift"),
        ("kod pocztowy", "postleitzahl"),
        ("data urodzenia", "geburtsdatum"),
    )

    def validate(self, document: ExtractedPdfDocument) -> None:
        normalized_text = _normalize_label(document.full_text)
        has_required_name_header = any(
            marker in normalized_text
            for marker in ("imie nazwisko", "patient:in", "patientin")
        )
        if has_required_name_header and all(
            any(option in normalized_text for option in marker)
            if isinstance(marker, tuple)
            else marker in normalized_text
            for marker in self.REQUIRED_MARKERS
        ):
            return
        raise PatientPdfImportFailure(
            PatientPdfImportErrorCode.PDF_UNSUPPORTED_LAYOUT,
            "PDF layout does not match the expected Doctolib export.",
        )


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
        self.layout_detector.validate(document)

        lines = [line for line in document.lines if line.text.strip()]
        header_index = self._find_header_index(lines)
        preamble_lines = lines[:header_index]
        import_date = self._extract_import_date(preamble_lines)
        clinic_name = self._extract_clinic_name(preamble_lines)
        column_ranges = self._build_column_ranges(lines[header_index])
        parsed_rows: list[ParsedPatientRow] = []
        row_number = 1

        for line in lines[header_index + 1 :]:
            normalized_line = _normalize_label(line.text)
            if not normalized_line:
                continue
            if (
                ("imie nazwisko" in normalized_line or "patient:in" in normalized_line or "patientin" in normalized_line)
                and "telefon" in normalized_line
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
            normalized = _normalize_label(line.text)
            if (
                ("godzina" in normalized or "uhrzeit" in normalized)
                and ("imie nazwisko" in normalized or "patient:in" in normalized or "patientin" in normalized)
                and "telefon" in normalized
                and ("data urodzenia" in normalized or "geburtsdatum" in normalized)
                and ("email" in normalized or "e-mail-adresse" in normalized)
                and ("adres" in normalized or "anschrift" in normalized)
                and ("kod pocztowy" in normalized or "postleitzahl" in normalized)
            ):
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
                    clinic_name = match.group("value").strip()
                    if clinic_name:
                        return clinic_name
        for line in reversed(preamble_lines):
            stripped = DATE_TOKEN_PATTERN.sub("", line.text).strip(" -:|")
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
            label = _normalize_label(word.text)
            if label in {"godzina", "uhrzeit"}:
                header_starts.append(("appointment_time_raw", word.x0))
            elif label in {"imie", "imie nazwisko"} or label.startswith("patient"):
                header_starts.append(("full_name_raw", word.x0))
            elif label == "telefon":
                header_starts.append(("phone_raw", word.x0))
            elif label in {"data", "geburtsdatum"}:
                header_starts.append(("date_of_birth_raw", word.x0))
            elif label in {"email", "e-mail-adresse"}:
                header_starts.append(("email_raw", word.x0))
            elif label in {"adres", "anschrift"}:
                header_starts.append(("address_raw", word.x0))
            elif label in {"kod", "postleitzahl"}:
                header_starts.append(("postal_code_raw", word.x0))
        expected_order = [
            "appointment_time_raw",
            "full_name_raw",
            "phone_raw",
            "date_of_birth_raw",
            "email_raw",
            "address_raw",
            "postal_code_raw",
        ]
        found_columns = [column_name for column_name, _ in header_starts]
        if found_columns != expected_order:
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


def _split_full_name(value: str) -> tuple[str | None, str | None]:
    honorifics = {"herr", "frau", "mr", "mrs", "ms"}
    raw_parts = [_sanitize_pdf_text(part) for part in value.split() if _sanitize_pdf_text(part)]
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

        clinic_site = ClinicSite.objects.select_related("pdf_import_default_consulting_room").get(
            name=parsed_import.clinic_name
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
    except ClinicSite.DoesNotExist as exc:
        _mark_batch_failed(
            batch=batch,
            error_code=PatientPdfImportErrorCode.UNKNOWN_CLINIC,
            message="Clinic from PDF could not be mapped to an existing ClinicSite.",
        )
        _ = exc
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
    existing_patient = Patient.objects.filter(
        first_name=normalized_row.first_name,
        last_name=normalized_row.last_name,
        phone=normalized_row.phone,
        date_of_birth=normalized_row.date_of_birth,
    ).first()
    try:
        patient = create_or_update_patient_manual(
            patient_id=existing_patient.id if existing_patient else None,
            first_name=normalized_row.first_name,
            last_name=normalized_row.last_name,
            date_of_birth=normalized_row.date_of_birth,
            phone=normalized_row.phone,
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
