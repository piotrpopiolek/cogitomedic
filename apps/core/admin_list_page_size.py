"""Django admin changelist: configurable page size (10/20/50/100) via ``?page_size=``."""

from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.http import HttpRequest, HttpResponse

from apps.core.constants import DEFAULT_LIST_LIMIT
from apps.core.list_pagination import (
    effective_default_page_size,
    page_size_switch_items,
    parse_page_size,
)
from apps.core.translation_service import get_admin_translation

try:
    from unfold.admin import ModelAdmin as UnfoldModelAdmin
except ImportError:
    UnfoldModelAdmin = admin.ModelAdmin

ADMIN_LIST_PAGE_SIZE_SESSION_KEY = "admin_list_page_size"


def persist_admin_list_page_size(request: HttpRequest) -> None:
    """Store ``page_size`` from GET in session (admin may redirect and strip the query)."""
    if "page_size" in request.GET:
        request.session[ADMIN_LIST_PAGE_SIZE_SESSION_KEY] = parse_page_size(
            request.GET.get("page_size")
        )


def resolve_admin_list_page_size(request: HttpRequest) -> int:
    """Current admin changelist page size (GET → session → default)."""
    if "page_size" in request.GET:
        return parse_page_size(request.GET.get("page_size"))
    session_value = request.session.get(ADMIN_LIST_PAGE_SIZE_SESSION_KEY)
    if session_value is not None:
        return parse_page_size(session_value)
    return effective_default_page_size()


def changelist_page_size_context(request: HttpRequest) -> dict[str, Any]:
    """Context fragment for page-size selector (custom admin HTML lists)."""
    current = resolve_admin_list_page_size(request)
    return {
        "page_size_options": page_size_switch_items(
            request.GET, current_page_size=current
        ),
        "page_size_label": get_admin_translation(
            request,
            "administration.pagination_page_size",
            "Wierszy na stronę:",
        ),
    }


class ListPageSizeAdminMixin:
    """Mixin for ``ModelAdmin``: ``page_size`` query param + footer switcher."""

    list_per_page = DEFAULT_LIST_LIMIT

    def changelist_view(
        self,
        request: HttpRequest,
        extra_context: dict[str, Any] | None = None,
    ) -> HttpResponse:
        persist_admin_list_page_size(request)
        previous_list_per_page = self.list_per_page
        self.list_per_page = resolve_admin_list_page_size(request)
        extra_context = {
            **(extra_context or {}),
            **changelist_page_size_context(request),
        }
        try:
            return super().changelist_view(request, extra_context=extra_context)  # type: ignore[misc]
        finally:
            self.list_per_page = previous_list_per_page


class CogitomedicaModelAdmin(ListPageSizeAdminMixin, UnfoldModelAdmin):
    """Project ``ModelAdmin`` base (Unfold + list page-size switcher)."""
