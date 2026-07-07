"""Pydantic contracts for accounting report REST API (GET /api/v1/accounting/report)."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from apps.core.api_schemas import OffsetPaginationQueryParams
from apps.operations.accounting_report import (
    AccountingReportResult,
    AccountingReportRow,
    DoctorPublicationCount,
    resolve_report_date_range,
)


class AccountingReportQueryParams(OffsetPaginationQueryParams):
    """Query params for GET /api/v1/accounting/report."""

    date_from: date | None = None
    date_to: date | None = None

    @field_validator("date_from", "date_to", mode="before")
    @classmethod
    def parse_iso_date(cls, value: str | date | None) -> date | None:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        if isinstance(value, date):
            return value
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError as exc:
            raise ValueError("Invalid date format. Use YYYY-MM-DD.") from exc

    def resolved_date_range(self) -> tuple[date, date]:
        return resolve_report_date_range(
            date_from_raw=self.date_from.isoformat() if self.date_from else None,
            date_to_raw=self.date_to.isoformat() if self.date_to else None,
        )


class AuditEventsListQueryParams(OffsetPaginationQueryParams):
    """Query params for GET /api/v1/audit-events."""

    event_type: str | None = None
    patient_id: UUID | None = None
    medical_document_id: UUID | None = None
    context_clinic_site_id: UUID | None = None
    actor_user_id: UUID | None = None
    outbox_event_id: UUID | None = None
    from_: str | None = Field(default=None, alias="from")
    to_: str | None = Field(default=None, alias="to")

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    @field_validator("event_type", mode="before")
    @classmethod
    def empty_event_type_to_none(cls, value: object) -> object:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        return value

    @field_validator(
        "patient_id",
        "medical_document_id",
        "context_clinic_site_id",
        "actor_user_id",
        "outbox_event_id",
        mode="before",
    )
    @classmethod
    def optional_uuid(cls, value: object) -> UUID | None:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        try:
            return UUID(str(value))
        except (ValueError, TypeError):
            return None

    @field_validator("from_", "to_", mode="before")
    @classmethod
    def empty_datetime_to_none(cls, value: object) -> object:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        return value


class AccountingReportRowResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row_no: int
    first_name: str
    last_name: str
    street: str
    postal_city: str
    email: str
    doctor_name: str
    exam_date: str
    medical_document_id: UUID
    doctor_user_id: UUID | None = None


class DoctorPublicationCountResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doctor_user_id: UUID | None = None
    doctor_name: str
    count: int = Field(ge=0)


class AccountingReportPagination(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total: int = Field(ge=0)


class AccountingReportResponse(BaseModel):
    """JSON response for GET /api/v1/accounting/report."""

    model_config = ConfigDict(extra="forbid")

    date_from: date
    date_to: date
    doctor_counts: list[DoctorPublicationCountResponse]
    items: list[AccountingReportRowResponse]
    pagination: AccountingReportPagination
    report_total_rows: int = Field(ge=0)


def _row_to_response(row: AccountingReportRow) -> AccountingReportRowResponse:
    return AccountingReportRowResponse.model_validate(row, from_attributes=True)


def _doctor_count_to_response(
    item: DoctorPublicationCount,
) -> DoctorPublicationCountResponse:
    return DoctorPublicationCountResponse.model_validate(item, from_attributes=True)


def build_accounting_report_response(
    report: AccountingReportResult,
    *,
    page: int,
    page_size: int,
) -> AccountingReportResponse:
    total = len(report.rows)
    start = (page - 1) * page_size
    end = start + page_size
    page_rows = report.rows[start:end]
    return AccountingReportResponse(
        date_from=report.date_from,
        date_to=report.date_to,
        doctor_counts=[
            _doctor_count_to_response(item) for item in report.doctor_counts
        ],
        items=[_row_to_response(row) for row in page_rows],
        pagination=AccountingReportPagination(
            page=page,
            page_size=page_size,
            total=total,
        ),
        report_total_rows=total,
    )
