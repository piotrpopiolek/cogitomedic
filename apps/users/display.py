"""Display helpers for :class:`~apps.users.models.StaffUser` (UI, API metadata, locks)."""

from __future__ import annotations

from apps.users.models import StaffUser


def staff_user_display_name(user: StaffUser | None) -> str:
    """
    Prefer ``first_name`` + ``last_name`` (trimmed); fall back to ``username``.

    Returns an empty string when ``user`` is ``None``.
    """
    if user is None:
        return ""
    name = f"{user.first_name} {user.last_name}".strip()
    return name or (user.username or "")
