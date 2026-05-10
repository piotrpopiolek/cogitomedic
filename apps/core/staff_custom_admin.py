"""
Shared access control for custom HTML views mounted under ``/admin/...``
(outside Django ``ModelAdmin``): staff login, ADMIN/MANAGER role, clinic scope.

Use with ``@staff_member_required`` on the view, then call ``ensure_*`` at the top
and return the response if not ``None``.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.http import HttpResponseForbidden

from apps.core.api_utils import get_scoped_clinic_site_ids
from apps.core.translation_service import resolve_other_message


def is_admin_or_manager_staff(user: Any) -> bool:
    """True if *user* is authenticated staff acting as administrator or manager."""
    return bool(
        user
        and user.is_authenticated
        and (
            getattr(user, "is_admin_role", False) or getattr(user, "is_manager", False)
        )
    )


def staff_admin_manager_forbidden_response(request: Any) -> HttpResponseForbidden:
    """HTTP 403 plain body when the user is not ADMIN/MANAGER."""
    return HttpResponseForbidden(
        resolve_other_message(
            request,
            "administration.staff_custom_admin_admin_manager_only",
            "Only administrators or managers can use this page.",
        )
    )


def staff_clinic_site_scope_forbidden_response(request: Any) -> HttpResponseForbidden:
    """HTTP 403 when the user's clinic scope excludes the target site."""
    return HttpResponseForbidden(
        resolve_other_message(
            request,
            "other.api.queue_entry_not_in_scope",
            "Queue entry is not in your assigned scope.",
        )
    )


def ensure_admin_manager_staff(request: Any) -> HttpResponseForbidden | None:
    """Return 403 response if the user is not ADMIN/MANAGER; otherwise ``None``."""
    if not is_admin_or_manager_staff(request.user):
        return staff_admin_manager_forbidden_response(request)
    return None


def is_reception_admin_or_manager_staff(user: Any) -> bool:
    """True for staff who may use the external-upload hub (same roles as the REST API)."""
    return bool(
        user
        and user.is_authenticated
        and (
            getattr(user, "is_reception", False)
            or getattr(user, "is_admin_role", False)
            or getattr(user, "is_manager", False)
        )
    )


def ensure_reception_admin_manager_staff(request: Any) -> HttpResponseForbidden | None:
    """Return 403 if the user is not Reception, Admin, or Manager."""
    if not is_reception_admin_or_manager_staff(request.user):
        return HttpResponseForbidden(
            resolve_other_message(
                request,
                "administration.external_upload_hub_staff_only",
                "Only reception, administrators, or managers can use this page.",
            )
        )
    return None


def ensure_clinic_site_visible_to_staff_user(
    request: Any, clinic_site_id: uuid.UUID
) -> HttpResponseForbidden | None:
    """
    Enforce clinic-site scope using ``get_scoped_clinic_site_ids`` (same rule as scoped APIs).

    Admins (``scope_ids is None``) pass. Other roles that carry site assignments—manager,
    reception, doctor, tablet—are limited to their assigned ``clinic_site`` ids; an
    empty scope never matches.

    Which roles may open a given custom admin page is enforced separately (e.g. the
    external-upload hub allows reception / admin / manager only). This helper does
    not imply doctor or tablet access to those pages; it only checks whether
    *clinic_site_id* lies in the user's scoped sites when scope applies.
    """
    scope_ids = get_scoped_clinic_site_ids(request.user)
    if scope_ids is not None and clinic_site_id not in scope_ids:
        return staff_clinic_site_scope_forbidden_response(request)
    return None
