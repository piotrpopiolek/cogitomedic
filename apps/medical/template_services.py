from __future__ import annotations

import uuid
from dataclasses import dataclass

from django.db.models import Q

from apps.core.exceptions import DomainError
from apps.medical.models import DoctorTextTemplate
from apps.users.models import StaffRole, StaffUser


class TemplatePermissionError(DomainError):
    """Raised when user has insufficient permissions for template operation."""


class TemplateNotFoundError(DomainError):
    """Raised when requested template does not exist."""


@dataclass(frozen=True)
class TemplateListFilters:
    actor_user_id: uuid.UUID
    template_locale: str | None = None
    include_inactive: bool = False


def _get_actor(actor_user_id: uuid.UUID) -> StaffUser:
    return StaffUser.objects.get(id=actor_user_id, is_active=True)


def list_templates(*, filters: TemplateListFilters) -> list[DoctorTextTemplate]:
    actor = _get_actor(filters.actor_user_id)
    queryset = DoctorTextTemplate.objects.all().order_by("-is_global", "name")

    if actor.role != StaffRole.ADMIN:
        queryset = queryset.filter(is_global=True) | queryset.filter(owner_user_id=actor.id)
        queryset = queryset.distinct()
    if filters.template_locale:
        locale = (filters.template_locale or "").strip()
        base = locale.split("-")[0] if locale else ""
        if base:
            queryset = queryset.filter(
                Q(template_locale=locale)
                | Q(template_locale=base)
                | Q(template_locale__startswith=base + "-")
            )
    if not filters.include_inactive:
        queryset = queryset.filter(is_active=True)
    return list(queryset)


def get_template(*, template_id: uuid.UUID, actor_user_id: uuid.UUID) -> DoctorTextTemplate:
    """Return a single template by id if it exists and actor is allowed to see it. Raises TemplateNotFoundError."""
    actor = _get_actor(actor_user_id)
    try:
        template = DoctorTextTemplate.objects.get(id=template_id)
    except DoctorTextTemplate.DoesNotExist as exc:
        raise TemplateNotFoundError("Template not found.") from exc

    if actor.role != StaffRole.ADMIN:
        if not template.is_global and template.owner_user_id != actor.id:
            raise TemplateNotFoundError("Template not found.")
    return template


def create_template(
    *,
    actor_user_id: uuid.UUID,
    name: str,
    template_locale: str,
    template_body: str,
    lesion_group_favorites: list[dict] | None = None,
    summary_favorites: list[dict] | None = None,
    is_global: bool = False,
    is_active: bool = True,
) -> DoctorTextTemplate:
    actor = _get_actor(actor_user_id)
    if is_global and actor.role != StaffRole.ADMIN:
        raise TemplatePermissionError("Only ADMIN can create global templates.")

    owner_user_id = None if is_global else actor.id
    return DoctorTextTemplate.objects.create(
        owner_user_id=owner_user_id,
        name=name,
        template_locale=template_locale,
        template_body=template_body,
        lesion_group_favorites=lesion_group_favorites or [],
        summary_favorites=summary_favorites or [],
        is_global=is_global,
        is_active=is_active,
    )


def update_template(
    *,
    template_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    name: str | None = None,
    template_locale: str | None = None,
    template_body: str | None = None,
    lesion_group_favorites: list[dict] | None = None,
    summary_favorites: list[dict] | None = None,
    is_active: bool | None = None,
) -> DoctorTextTemplate:
    actor = _get_actor(actor_user_id)
    try:
        template = DoctorTextTemplate.objects.get(id=template_id)
    except DoctorTextTemplate.DoesNotExist as exc:
        raise TemplateNotFoundError("Template not found.") from exc

    if template.is_global and actor.role != StaffRole.ADMIN:
        raise TemplatePermissionError("Only ADMIN can modify global templates.")
    if not template.is_global and template.owner_user_id != actor.id:
        raise TemplatePermissionError("Only template owner can modify private template.")

    if name is not None:
        template.name = name
    if template_locale is not None:
        template.template_locale = template_locale
    if template_body is not None:
        template.template_body = template_body
    if lesion_group_favorites is not None:
        template.lesion_group_favorites = lesion_group_favorites
    if summary_favorites is not None:
        template.summary_favorites = summary_favorites
    if is_active is not None:
        template.is_active = is_active
    template.save()
    return template
