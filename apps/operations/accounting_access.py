"""Access control for accounting weekly report (admin HTML + Unfold sidebar)."""

from __future__ import annotations

from typing import Any


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
