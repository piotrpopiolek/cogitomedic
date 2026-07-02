"""Admin views for accounting weekly report."""

from __future__ import annotations

from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.template.response import TemplateResponse

from apps.core.api_utils import get_scoped_clinic_site_ids, safe_parse_positive_int
from apps.core.constants import DEFAULT_LIST_LIMIT, MAX_LIST_LIMIT
from apps.core.translation_service import get_admin_translation, resolve_other_message
from apps.operations.accounting_report import (
    build_accounting_report,
    resolve_accounting_report_export_headers,
    resolve_accounting_report_export_sheet_title,
    resolve_report_date_range,
)
from apps.operations.export import (
    render_accounting_report_csv,
    render_accounting_report_xlsx,
)
from apps.operations.services import create_audit_event


def accounting_report_access_ok(user) -> bool:
    return bool(
        user
        and user.is_authenticated
        and (
            getattr(user, "is_admin_role", False)
            or getattr(user, "is_manager", False)
            or getattr(user, "is_accounting", False)
        )
    )


def _accounting_report_forbidden_response(
    request: HttpRequest,
) -> HttpResponseForbidden:
    return HttpResponseForbidden(
        resolve_other_message(
            request,
            "administration.accounting_access_forbidden",
            "You do not have permission to access the accounting report.",
        )
    )


def _parse_pagination(request: HttpRequest) -> tuple[int, int]:
    page = safe_parse_positive_int(
        request.GET.get("page"),
        default=1,
        maximum=10_000,
    )
    page_size = safe_parse_positive_int(
        request.GET.get("page_size"),
        default=DEFAULT_LIST_LIMIT,
        maximum=MAX_LIST_LIMIT,
    )
    return page, page_size


def _report_context(request: HttpRequest) -> dict:
    date_from, date_to = resolve_report_date_range(
        date_from_raw=request.GET.get("date_from"),
        date_to_raw=request.GET.get("date_to"),
    )
    scoped_clinic_site_ids = get_scoped_clinic_site_ids(request.user)
    report = build_accounting_report(
        date_from=date_from,
        date_to=date_to,
        scoped_clinic_site_ids=scoped_clinic_site_ids,
    )
    page, page_size = _parse_pagination(request)
    total = len(report.rows)
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
        encoded = q.urlencode()
        return f"?{encoded}" if encoded else ""

    previous_page_url = pagination_url(page - 1) if page > 1 else None
    next_page_url = pagination_url(page + 1) if end < total else None

    return {
        **admin.site.each_context(request),
        "title": get_admin_translation(
            request,
            "administration.accounting_report_title",
            "Accounting report",
        ),
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "doctor_counts": report.doctor_counts,
        "items": page_rows,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
        },
        "previous_page_url": previous_page_url,
        "next_page_url": next_page_url,
        "export_querystring": export_querystring(),
        "report_total_rows": total,
    }


@staff_member_required
def accounting_report_dashboard_view(request: HttpRequest) -> HttpResponse:
    if not accounting_report_access_ok(request.user):
        return _accounting_report_forbidden_response(request)
    return TemplateResponse(
        request,
        "admin/operations/accounting_report.html",
        _report_context(request),
    )


def _export_filename(date_from: str, date_to: str, ext: str) -> str:
    return f"accounting_report_{date_from}_{date_to}.{ext}"


@staff_member_required
def accounting_report_export_csv_view(request: HttpRequest) -> HttpResponse:
    if not accounting_report_access_ok(request.user):
        return _accounting_report_forbidden_response(request)
    date_from, date_to = resolve_report_date_range(
        date_from_raw=request.GET.get("date_from"),
        date_to_raw=request.GET.get("date_to"),
    )
    scoped_clinic_site_ids = get_scoped_clinic_site_ids(request.user)
    report = build_accounting_report(
        date_from=date_from,
        date_to=date_to,
        scoped_clinic_site_ids=scoped_clinic_site_ids,
    )
    create_audit_event(
        event_type="ACCOUNTING_REPORT_EXPORT",
        actor_user_id=request.user.id,
        metadata={
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "format": "csv",
            "row_count": len(report.rows),
        },
    )
    response = HttpResponse(
        render_accounting_report_csv(
            report.rows,
            headers=resolve_accounting_report_export_headers(request),
        ),
        content_type="text/csv; charset=utf-8",
    )
    response["Content-Disposition"] = (
        f'attachment; filename="{_export_filename(date_from.isoformat(), date_to.isoformat(), "csv")}"'
    )
    return response


@staff_member_required
def accounting_report_export_xlsx_view(request: HttpRequest) -> HttpResponse:
    if not accounting_report_access_ok(request.user):
        return _accounting_report_forbidden_response(request)
    date_from, date_to = resolve_report_date_range(
        date_from_raw=request.GET.get("date_from"),
        date_to_raw=request.GET.get("date_to"),
    )
    scoped_clinic_site_ids = get_scoped_clinic_site_ids(request.user)
    report = build_accounting_report(
        date_from=date_from,
        date_to=date_to,
        scoped_clinic_site_ids=scoped_clinic_site_ids,
    )
    create_audit_event(
        event_type="ACCOUNTING_REPORT_EXPORT",
        actor_user_id=request.user.id,
        metadata={
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "format": "xlsx",
            "row_count": len(report.rows),
        },
    )
    response = HttpResponse(
        render_accounting_report_xlsx(
            report.rows,
            headers=resolve_accounting_report_export_headers(request),
            sheet_title=resolve_accounting_report_export_sheet_title(request),
        ),
        content_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
    )
    response["Content-Disposition"] = (
        f'attachment; filename="{_export_filename(date_from.isoformat(), date_to.isoformat(), "xlsx")}"'
    )
    return response
