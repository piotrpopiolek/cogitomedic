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
            "Einträge pro Seite:",
        ),
    }


class ListPageSizeAdminMixin:
    """Mixin for ``ModelAdmin``: ``page_size`` query param + footer switcher."""

    list_per_page = DEFAULT_LIST_LIMIT

    def get_list_per_page(self, request: HttpRequest) -> int:
        """Per-request page size; avoids mutating ``self.list_per_page`` on the admin singleton."""
        return resolve_admin_list_page_size(request)

    def get_changelist_instance(self, request):
        """Pass resolved page size into ``ChangeList`` (thread-safe vs ``self.list_per_page``)."""
        list_display = self.get_list_display(request)
        list_display_links = self.get_list_display_links(request, list_display)
        if self.get_actions(request):
            list_display = ["action_checkbox", *list_display]
        sortable_by = self.get_sortable_by(request)
        ChangeList = self.get_changelist(request)
        return ChangeList(
            request,
            self.model,
            list_display,
            list_display_links,
            self.get_list_filter(request),
            self.date_hierarchy,
            self.get_search_fields(request),
            self.get_list_select_related(request),
            self.get_list_per_page(request),
            self.list_max_show_all,
            self.list_editable,
            self,
            sortable_by,
            self.search_help_text,
        )

    def changelist_view(
        self,
        request: HttpRequest,
        extra_context: dict[str, Any] | None = None,
    ) -> HttpResponse:
        persist_admin_list_page_size(request)
        extra_context = {
            **(extra_context or {}),
            **changelist_page_size_context(request),
        }
        return super().changelist_view(request, extra_context=extra_context)  # type: ignore[misc]


class CogitomedicaModelAdmin(ListPageSizeAdminMixin, UnfoldModelAdmin):
    """Project ``ModelAdmin`` base (Unfold + list page-size switcher)."""
