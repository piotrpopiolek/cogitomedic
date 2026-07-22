"""Admin views for accounting weekly report."""

from __future__ import annotations

from typing import Literal

from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
)
from django.template.response import TemplateResponse

from apps.core.admin_list_page_size import (
    changelist_page_size_context,
    persist_admin_list_page_size,
    resolve_admin_list_page_size,
)
from apps.core.api_utils import get_scoped_clinic_site_ids, safe_parse_positive_int
from apps.core.list_pagination import clamp_page_to_total
from apps.core.translation_service import (
    format_administration_message,
    get_admin_translation,
)
from apps.operations.accounting_access import accounting_report_access_ok
from apps.operations.accounting_report import (
    ACCOUNTING_REPORT_MODES,
    REPORT_MODE_ATTENDED,
    REPORT_MODE_AUSFALL,
    REPORT_MODE_PUBLISHED,
    ReportMode,
    build_accounting_report,
    parse_report_mode,
    resolve_accounting_ausfallhonorar_yes,
    resolve_accounting_report_export_headers,
    resolve_accounting_report_export_sheet_title,
    resolve_report_date_range,
)
from apps.operations.export import (
    render_accounting_report_csv,
    render_accounting_report_xlsx,
)
from apps.operations.services import create_audit_event

ExportFormat = Literal["csv", "xlsx"]

_EXPORT_CONTENT_TYPES: dict[ExportFormat, str] = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def _accounting_report_forbidden_response(
    request: HttpRequest,
) -> HttpResponseForbidden:
    return HttpResponseForbidden(
        get_admin_translation(
            request,
            "administration.accounting_access_forbidden",
            "Keine Berechtigung für den Buchhaltungsbericht.",
        )
    )


def _parse_pagination(request: HttpRequest) -> tuple[int, int]:
    page = safe_parse_positive_int(
        request.GET.get("page"),
        default=1,
        maximum=10_000,
    )
    page_size = resolve_admin_list_page_size(request)
    return page, page_size


def _parse_report_mode_param(
    request: HttpRequest,
) -> ReportMode | HttpResponseBadRequest:
    try:
        return parse_report_mode(request.GET.get("report_mode"))
    except ValueError:
        allowed = ", ".join(sorted(ACCOUNTING_REPORT_MODES))
        return HttpResponseBadRequest(
            format_administration_message(
                "administration.accounting_report_mode_invalid",
                "Ungültiger report_mode. Erlaubt: {allowed}.",
                request,
                allowed=allowed,
            )
        )


def _report_context(request: HttpRequest, *, report_mode: ReportMode) -> dict:
    persist_admin_list_page_size(request)
    date_from, date_to = resolve_report_date_range(
        date_from_raw=request.GET.get("date_from"),
        date_to_raw=request.GET.get("date_to"),
    )
    scoped_clinic_site_ids = get_scoped_clinic_site_ids(request.user)
    report = build_accounting_report(
        date_from=date_from,
        date_to=date_to,
        scoped_clinic_site_ids=scoped_clinic_site_ids,
        report_mode=report_mode,
        ausfallhonorar_yes=resolve_accounting_ausfallhonorar_yes(request),
    )
    page, page_size = _parse_pagination(request)
    total = len(report.rows)
    page = clamp_page_to_total(page, page_size=page_size, total=total)
    start = (page - 1) * page_size
    end = start + page_size
    page_rows = report.rows[start:end]

    get_copy = request.GET.copy()

    def pagination_url(target_page: int) -> str:
        q = get_copy.copy()
        q["page"] = str(target_page)
        return "?" + q.urlencode()

    def export_querystring() -> str:
        q = get_copy.copy()
        q.pop("page", None)
        q.pop("page_size", None)
        q["report_mode"] = report_mode
        encoded = q.urlencode()
        return f"?{encoded}" if encoded else ""

    previous_page_url = pagination_url(page - 1) if page > 1 else None
    next_page_url = pagination_url(page + 1) if end < total else None

    return {
        **admin.site.each_context(request),
        "title": get_admin_translation(
            request,
            "administration.accounting_report_title",
            "Buchhaltungsbericht",
        ),
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "report_mode": report_mode,
        "report_mode_published": REPORT_MODE_PUBLISHED,
        "report_mode_attended": REPORT_MODE_ATTENDED,
        "report_mode_ausfall": REPORT_MODE_AUSFALL,
        "doctor_counts": report.doctor_counts,
        "items": page_rows,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
        },
        "previous_page_url": previous_page_url,
        "next_page_url": next_page_url,
        **changelist_page_size_context(request),
        "export_querystring": export_querystring(),
        "report_total_rows": total,
    }


@staff_member_required
def accounting_report_dashboard_view(request: HttpRequest) -> HttpResponse:
    if not accounting_report_access_ok(request.user):
        return _accounting_report_forbidden_response(request)
    report_mode = _parse_report_mode_param(request)
    if isinstance(report_mode, HttpResponseBadRequest):
        return report_mode
    return TemplateResponse(
        request,
        "admin/operations/accounting_report.html",
        _report_context(request, report_mode=report_mode),
    )


def _export_filename(date_from: str, date_to: str, report_mode: str, ext: str) -> str:
    return f"accounting_report_{report_mode}_{date_from}_{date_to}.{ext}"


def _build_export_response(
    request: HttpRequest, export_format: ExportFormat
) -> HttpResponse:
    report_mode = _parse_report_mode_param(request)
    if isinstance(report_mode, HttpResponseBadRequest):
        return report_mode
    date_from, date_to = resolve_report_date_range(
        date_from_raw=request.GET.get("date_from"),
        date_to_raw=request.GET.get("date_to"),
    )
    scoped_clinic_site_ids = get_scoped_clinic_site_ids(request.user)
    report = build_accounting_report(
        date_from=date_from,
        date_to=date_to,
        scoped_clinic_site_ids=scoped_clinic_site_ids,
        report_mode=report_mode,
        ausfallhonorar_yes=resolve_accounting_ausfallhonorar_yes(request),
    )
    create_audit_event(
        event_type="ACCOUNTING_REPORT_EXPORT",
        actor_user_id=request.user.id,
        metadata={
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "format": export_format,
            "row_count": len(report.rows),
            "report_mode": report_mode,
        },
    )
    headers = resolve_accounting_report_export_headers(request, report_mode=report_mode)
    include_ausfall = report_mode == REPORT_MODE_AUSFALL
    if export_format == "csv":
        body = render_accounting_report_csv(
            report.rows,
            headers=headers,
            include_ausfallhonorar=include_ausfall,
        )
    else:
        body = render_accounting_report_xlsx(
            report.rows,
            headers=headers,
            sheet_title=resolve_accounting_report_export_sheet_title(request),
            include_ausfallhonorar=include_ausfall,
        )
    response = HttpResponse(body, content_type=_EXPORT_CONTENT_TYPES[export_format])
    response["Content-Disposition"] = (
        'attachment; filename="'
        f'{_export_filename(date_from.isoformat(), date_to.isoformat(), report_mode, export_format)}"'
    )
    return response


@staff_member_required
def accounting_report_export_csv_view(request: HttpRequest) -> HttpResponse:
    if not accounting_report_access_ok(request.user):
        return _accounting_report_forbidden_response(request)
    return _build_export_response(request, "csv")


@staff_member_required
def accounting_report_export_xlsx_view(request: HttpRequest) -> HttpResponse:
    if not accounting_report_access_ok(request.user):
        return _accounting_report_forbidden_response(request)
    return _build_export_response(request, "xlsx")
