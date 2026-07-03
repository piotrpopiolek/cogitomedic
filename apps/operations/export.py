"""CSV / XLSX export for accounting report."""

from __future__ import annotations

import csv
import io
from typing import Iterable, Sequence

from openpyxl import Workbook

from apps.operations.accounting_report import (
    AccountingReportRow,
    accounting_report_export_headers_default,
)


def accounting_report_row_values(row: AccountingReportRow) -> list[str]:
    return [
        str(row.row_no),
        row.first_name,
        row.last_name,
        row.street,
        row.postal_city,
        row.email,
        row.doctor_name,
        row.exam_date,
    ]


def render_accounting_report_csv(
    rows: Iterable[AccountingReportRow],
    *,
    headers: Sequence[str] | None = None,
) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    hdr = (
        tuple(headers)
        if headers is not None
        else accounting_report_export_headers_default()
    )
    writer.writerow(hdr)
    for row in rows:
        writer.writerow(accounting_report_row_values(row))
    return buffer.getvalue().encode("utf-8")


def render_accounting_report_xlsx(
    rows: Iterable[AccountingReportRow],
    *,
    headers: Sequence[str] | None = None,
    sheet_title: str = "Patientendaten",
) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = sheet_title[:31]
    hdr = (
        tuple(headers)
        if headers is not None
        else accounting_report_export_headers_default()
    )
    sheet.append(list(hdr))
    for row in rows:
        sheet.append(accounting_report_row_values(row))
    out = io.BytesIO()
    workbook.save(out)
    return out.getvalue()
