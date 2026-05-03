from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from django import forms
from django.contrib import admin as django_admin
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import QuerySet
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.core.exceptions import DomainError
from apps.core.staff_custom_admin import ensure_admin_manager_staff
from apps.core.translation_service import resolve_other_message
from apps.medical.constants import (
    PAPER_INTAKE_HUB_QUEUE_ENTRY_LOOKBACK_DAYS,
    PAPER_INTAKE_MIN_HOURS_AFTER_APPOINTMENT,
)
from apps.medical.paper_intake_policy import paper_intake_authorize_eligibility
from apps.medical.services import (
    authorize_paper_intake,
    revoke_paper_intake_authorization,
)
from apps.reception.models import QueueEntry, QueueEntryStatus

try:
    from unfold.widgets import UnfoldAdminSelectWidget
except ImportError:
    UnfoldAdminSelectWidget = forms.Select


def _paper_intake_hub_queue_entries_queryset() -> QuerySet[QueueEntry]:
    """Hub pick list: all clinic sites; last *N* days; only WAITING (same gate as ``authorize_paper_intake``).

    No clinic-site filter on the hub for ADMIN or MANAGER (oversight / shared pick list).
    The entry page and ``queue_entry_paper_intake_authorization_view`` likewise do not gate
    on assigned clinic sites for ADMIN/MANAGER. Other reception queue APIs may still return
    ``queue_entry_not_in_scope`` for users with a finite clinic scope.

    Revoke does not require WAITING; entries with active paper auth but non-WAITING status
    are omitted here and are reachable only by direct URL or Django admin queue entry.
    """
    cutoff = timezone.now().date() - timedelta(
        days=PAPER_INTAKE_HUB_QUEUE_ENTRY_LOOKBACK_DAYS
    )
    return (
        QueueEntry.objects.filter(
            daily_queue__queue_date__gte=cutoff,
            entry_status=QueueEntryStatus.WAITING,
        )
        .select_related("patient", "daily_queue", "daily_queue__clinic_site")
        .order_by("-daily_queue__queue_date", "daily_queue_id", "position_no")
    )


class PaperIntakeHubPickForm(forms.Form):
    queue_entry = forms.ModelChoiceField(
        queryset=QueueEntry.objects.none(),
        required=True,
        label="",
        widget=UnfoldAdminSelectWidget(attrs={"required": True}),
    )

    def __init__(
        self,
        *args: Any,
        queryset: QuerySet[QueueEntry],
        empty_label: str,
        invalid_choice_message: str,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        f = self.fields["queue_entry"]
        f.queryset = queryset
        f.empty_label = empty_label
        f.error_messages["invalid_choice"] = invalid_choice_message


def _paper_intake_ui_state(*, request, entry: QueueEntry) -> dict[str, Any]:
    """Map ``paper_intake_authorize_eligibility`` into template context (resolved strings)."""
    elig = paper_intake_authorize_eligibility(entry=entry)
    blocking_messages = [
        resolve_other_message(
            request,
            b.message_key,
            b.default_message,
            **b.format_params,
        )
        for b in elig.blocking_blocks
    ]
    return {
        "has_document": elig.has_document,
        "authorization": elig.active_authorization,
        "can_authorize": elig.can_authorize,
        "can_revoke": elig.can_revoke,
        "blocking_messages": blocking_messages,
        "earliest_authorize_at": elig.earliest_authorize_at,
        "paper_intake_min_hours_after_appointment": (
            PAPER_INTAKE_MIN_HOURS_AFTER_APPOINTMENT
        ),
    }


@staff_member_required
@require_http_methods(["GET", "HEAD"])
def paper_intake_admin_hub_view(request):
    """Pick a queue entry from the hub list, then redirect to the authorization form."""
    if (denied := ensure_admin_manager_staff(request)) is not None:
        return denied

    qs = _paper_intake_hub_queue_entries_queryset()
    empty_label = resolve_other_message(
        request,
        "administration.paper_intake_admin_hub_queue_entry_empty",
        "Select value",
    )
    invalid_choice = resolve_other_message(
        request,
        "administration.paper_intake_admin_hub_invalid_queue_entry",
        "Select a valid queue entry from the list.",
    )

    raw_pick = (request.GET.get("queue_entry") or "").strip()
    raw_legacy = (request.GET.get("queue_entry_id") or "").strip()
    error_invalid = None

    if raw_pick:
        form = PaperIntakeHubPickForm(
            request.GET,
            queryset=qs,
            empty_label=empty_label,
            invalid_choice_message=invalid_choice,
        )
        if form.is_valid():
            entry = form.cleaned_data["queue_entry"]
            return HttpResponseRedirect(
                reverse(
                    "admin_paper_intake_entry",
                    kwargs={"queue_entry_id": entry.pk},
                )
            )
        err = form.errors.get("queue_entry")
        if err:
            error_invalid = err[0]
    elif raw_legacy:
        try:
            qid = uuid.UUID(raw_legacy)
        except ValueError:
            error_invalid = resolve_other_message(
                request,
                "administration.paper_intake_admin_invalid_uuid",
                "Enter a valid queue entry UUID.",
            )
        else:
            return HttpResponseRedirect(
                reverse("admin_paper_intake_entry", kwargs={"queue_entry_id": qid})
            )
        form = PaperIntakeHubPickForm(
            queryset=qs,
            empty_label=empty_label,
            invalid_choice_message=invalid_choice,
        )
    else:
        form = PaperIntakeHubPickForm(
            queryset=qs,
            empty_label=empty_label,
            invalid_choice_message=invalid_choice,
        )

    context = {
        **django_admin.site.each_context(request),
        "title": resolve_other_message(
            request,
            "administration.paper_intake_admin_hub_title",
            "Paper intake authorization",
        ),
        "error_invalid": error_invalid,
        "form": form,
        "hub_queue_entries_empty": not qs.exists(),
    }
    return TemplateResponse(request, "admin/reception/paper_intake_hub.html", context)


@staff_member_required
@require_http_methods(["GET", "HEAD", "POST"])
def paper_intake_admin_entry_view(request, queue_entry_id: uuid.UUID):
    """
    ADMIN/MANAGER only. No clinic-site gate (same global oversight model as the hub and
    ``queue_entry_paper_intake_authorization_view``). Other queue HTTP APIs may still use
    ``queue_entry_not_in_scope`` for scoped roles.
    """
    if (denied := ensure_admin_manager_staff(request)) is not None:
        return denied

    entry = get_object_or_404(
        QueueEntry.objects.select_related("patient", "daily_queue"),
        id=queue_entry_id,
    )

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        reason = (request.POST.get("reason") or "").strip()
        try:
            if action == "authorize":
                authorize_paper_intake(
                    queue_entry_id=entry.id,
                    authorized_by_user_id=request.user.id,
                    reason=reason,
                )
                messages.success(
                    request,
                    resolve_other_message(
                        request,
                        "administration.paper_intake_admin_success_authorized",
                        "Paper intake path has been authorized.",
                    ),
                )
            elif action == "revoke":
                revoke_paper_intake_authorization(
                    queue_entry_id=entry.id,
                    revoked_by_user_id=request.user.id,
                    reason=reason,
                )
                messages.success(
                    request,
                    resolve_other_message(
                        request,
                        "administration.paper_intake_admin_success_revoked",
                        "Paper intake authorization has been revoked.",
                    ),
                )
            else:
                messages.error(
                    request,
                    resolve_other_message(
                        request,
                        "administration.staff_custom_admin_invalid_action",
                        "Invalid action.",
                    ),
                )
        except DomainError as exc:
            msg = resolve_other_message(
                request,
                exc.api_message_key or "other.domain.error",
                str(exc),
                **(exc.api_message_params or {}),
            )
            messages.error(request, msg)
        return HttpResponseRedirect(
            reverse("admin_paper_intake_entry", kwargs={"queue_entry_id": entry.id})
        )

    ui = _paper_intake_ui_state(request=request, entry=entry)
    context = {
        **django_admin.site.each_context(request),
        "title": resolve_other_message(
            request,
            "administration.paper_intake_admin_entry_title",
            "Paper intake authorization",
        ),
        "entry": entry,
        "patient": entry.patient,
        "daily_queue": entry.daily_queue,
        "admin_queue_entry_url": reverse(
            "admin:reception_queueentry_change", args=[entry.id]
        ),
        **ui,
    }
    return TemplateResponse(request, "admin/reception/paper_intake_entry.html", context)
