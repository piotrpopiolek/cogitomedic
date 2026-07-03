"""Access control for accounting weekly report (admin HTML + Unfold sidebar)."""

from __future__ import annotations

from typing import Any

from django.urls import reverse


def accounting_report_access_ok(user: Any) -> bool:
    """Admin, Manager, or Accounting role may open the report and exports."""
    return bool(
        user
        and user.is_authenticated
        and (
            getattr(user, "is_admin_role", False)
            or getattr(user, "is_manager", False)
            or getattr(user, "is_accounting", False)
        )
    )


def is_accounting_report_role(request: Any) -> bool:
    """Unfold sidebar permission callback (``request.user`` wrapper)."""
    return accounting_report_access_ok(getattr(request, "user", None))


def is_accounting_only_staff(user: Any) -> bool:
    """Accounting role without Admin/Manager — no Django model permissions on ``/admin/``."""
    return bool(
        user
        and user.is_authenticated
        and getattr(user, "is_accounting", False)
        and not getattr(user, "is_admin_role", False)
        and not getattr(user, "is_manager", False)
    )


def staff_admin_login_redirect(request: Any) -> str:
    """Post-login URL for Unfold admin login; also used when ``/admin/`` has nothing to show."""
    if is_accounting_only_staff(getattr(request, "user", None)):
        return reverse("admin_accounting_report")
    return reverse("admin:index")
