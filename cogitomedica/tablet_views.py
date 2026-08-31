"""
Minimalny interfejs tabletu (poczekalnia): logowanie, wybór kolejki, lista pacjentów, start formularza.
Dostęp: rola TABLET, RECEPTION lub ADMIN.
"""

from __future__ import annotations

from uuid import UUID

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods

from apps.core.api_utils import (
    get_scoped_clinic_site_ids,
    get_tablet_scope_clinic_site_ids,
)
from apps.intake.models import PatientIntakeForm
from apps.intake.services import get_intake_form_context
from apps.reception.models import DailyQueue, QueueEntry, TabletDevice
from apps.reception.process_types import ProcessType
from apps.reception.services import (
    get_or_create_tablet_device_by_android_id,
    issue_tablet_session_latest_wins,
    record_tablet_login_for_android_id,
)

from apps.core.translation_service import get_form_ui_strings, get_staff_ui_strings

TABLET_ALLOWED_ROLES = {"TABLET", "RECEPTION", "ADMIN"}


def _staff_context(request: HttpRequest) -> dict:
    """Return staff_locale and staff_ui for waiting room templates. Persists ?locale= in session."""
    locale = (request.GET.get("locale") or "").strip().lower() or request.session.get(
        "tablet_staff_locale", "de"
    )
    if locale not in ("de", "en", "pl"):
        locale = "de"
    if request.GET.get("locale"):
        request.session["tablet_staff_locale"] = locale
    return {"staff_locale": locale, "staff_ui": get_staff_ui_strings(locale)}


def _tablet_role_ok(request: HttpRequest) -> bool:
    user = request.user
    return user.is_authenticated and (
        user.is_tablet or user.is_reception or user.is_admin_role
    )


def _get_tablet_device_from_session(request: HttpRequest) -> TabletDevice | None:
    """Return active TabletDevice from session or None."""
    device_id_str = request.session.get("tablet_device_id")
    if not device_id_str:
        return None
    try:
        device_id = UUID(device_id_str)
    except (ValueError, TypeError):
        return None
    try:
        return TabletDevice.objects.select_related("clinic_site").get(
            id=device_id, is_active=True
        )
    except ObjectDoesNotExist:
        return None


def _resolve_tablet_area_scope_ids(request: HttpRequest) -> list[UUID] | None:
    """Resolve clinic scope for tablet-area pages: ADMIN sees all, others are scoped."""
    scoped_ids = get_scoped_clinic_site_ids(request.user)
    if request.user.is_tablet:
        tablet_scope_ids = get_tablet_scope_clinic_site_ids(request)
        if tablet_scope_ids is not None:
            return tablet_scope_ids
    return scoped_ids


@require_http_methods(["GET", "POST"])
def tablet_login_view(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated and _tablet_role_ok(request):
        return redirect("tablet:home")
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)
        if user is not None and (
            user.is_tablet or user.is_reception or user.is_admin_role
        ):
            login(request, user)
            android_id = (request.POST.get("android_id") or "").strip()
            if android_id:
                device = record_tablet_login_for_android_id(android_id=android_id)
                request.session["tablet_device_id"] = str(device.id)
            else:
                request.session.pop("tablet_device_id", None)
            next_url = (request.GET.get("next") or "").strip()
            if next_url and not url_has_allowed_host_and_scheme(
                next_url, request.get_host()
            ):
                next_url = ""
            return redirect(next_url or "tablet:home")
        ctx = _staff_context(request)
        ctx["error"] = ctx["staff_ui"]["login_error"]
        return render(request, "tablet/login.html", ctx)
    return render(request, "tablet/login.html", _staff_context(request))


@require_http_methods(["GET", "POST"])
def tablet_logout_view(request: HttpRequest) -> HttpResponse:
    request.session.pop("tablet_device_id", None)
    logout(request)
    return redirect("tablet:login")


@login_required(login_url="tablet:login")
def tablet_home_view(request: HttpRequest) -> HttpResponse:
    if not _tablet_role_ok(request):
        return redirect("tablet:login")
    today = timezone.localdate()
    qs = (
        DailyQueue.objects.filter(queue_date=today)
        .select_related("clinic_site", "consulting_room")
        .order_by("clinic_site__name", "consulting_room__name")
    )
    tablet_unassigned = False
    scope_ids = _resolve_tablet_area_scope_ids(request)
    if scope_ids is not None:
        qs = qs.filter(clinic_site_id__in=scope_ids)
        if request.user.is_tablet and not scope_ids:
            tablet_unassigned = True
    device = _get_tablet_device_from_session(request)
    if device is not None:
        if device.clinic_site_id is not None:
            qs = qs.filter(clinic_site_id=device.clinic_site_id)
        else:
            qs = qs.none()
            tablet_unassigned = True
    ctx = {
        **_staff_context(request),
        "queues": qs,
        "today": today,
        "tablet_unassigned": tablet_unassigned,
    }
    return render(request, "tablet/home.html", ctx)


@login_required(login_url="tablet:login")
def tablet_queue_entries_view(
    request: HttpRequest, daily_queue_id: UUID
) -> HttpResponse:
    if not _tablet_role_ok(request):
        return redirect("tablet:login")
    today = timezone.localdate()
    try:
        queue = DailyQueue.objects.select_related("clinic_site", "consulting_room").get(
            id=daily_queue_id
        )
    except ObjectDoesNotExist:
        ctx = {**_staff_context(request)}
        ctx["message"] = ctx["staff_ui"]["err_queue_not_found"]
        return render(request, "tablet/error.html", ctx, status=404)
    device = _get_tablet_device_from_session(request)
    scope_ids = _resolve_tablet_area_scope_ids(request)
    if scope_ids is not None and queue.clinic_site_id not in scope_ids:
        ctx = {**_staff_context(request)}
        ctx["message"] = ctx["staff_ui"]["err_queue_access_denied"]
        return render(request, "tablet/error.html", ctx, status=403)
    if device is not None and device.clinic_site_id is not None:
        if queue.clinic_site_id != device.clinic_site_id:
            ctx = {**_staff_context(request)}
            ctx["message"] = ctx["staff_ui"]["err_queue_access_denied"]
            return render(request, "tablet/error.html", ctx, status=403)
    if queue.queue_date != today:
        ctx = {**_staff_context(request)}
        ctx["message"] = ctx["staff_ui"]["queue_not_today"]
        return render(request, "tablet/error.html", ctx, status=400)
    entries = (
        QueueEntry.objects.filter(daily_queue_id=daily_queue_id)
        .select_related("patient")
        .order_by("position_no")
    )
    ctx = {**_staff_context(request), "queue": queue, "entries": entries}
    return render(request, "tablet/queue_entries.html", ctx)


@require_http_methods(["GET", "POST"])
@login_required(login_url="tablet:login")
def tablet_entry_start_view(request: HttpRequest, queue_entry_id: UUID) -> HttpResponse:
    if not _tablet_role_ok(request):
        return redirect("tablet:login")
    today = timezone.localdate()
    try:
        entry = QueueEntry.objects.select_related("daily_queue", "patient").get(
            id=queue_entry_id
        )
    except ObjectDoesNotExist:
        ctx = {**_staff_context(request)}
        ctx["message"] = ctx["staff_ui"]["err_entry_not_found"]
        return render(request, "tablet/error.html", ctx, status=404)
    if entry.daily_queue.queue_date != today:
        ctx = {**_staff_context(request)}
        ctx["message"] = ctx["staff_ui"]["queue_not_today"]
        return render(request, "tablet/error.html", ctx, status=400)
    device = _get_tablet_device_from_session(request)
    scope_ids = _resolve_tablet_area_scope_ids(request)
    if scope_ids is not None and entry.daily_queue.clinic_site_id not in scope_ids:
        ctx = {**_staff_context(request)}
        ctx["message"] = ctx["staff_ui"]["err_entry_access_denied"]
        return render(request, "tablet/error.html", ctx, status=403)
    if device is not None and device.clinic_site_id is not None:
        if entry.daily_queue.clinic_site_id != device.clinic_site_id:
            ctx = {**_staff_context(request)}
            ctx["message"] = ctx["staff_ui"]["err_entry_access_denied"]
            return render(request, "tablet/error.html", ctx, status=403)
    if request.method == "POST":
        tablet_device_id = None
        tablet_device_id_raw = (request.POST.get("tablet_device_id") or "").strip()
        android_id = (request.POST.get("android_id") or "").strip()
        if tablet_device_id_raw:
            try:
                tablet_device_id = UUID(tablet_device_id_raw)
            except (ValueError, TypeError):
                pass
        if tablet_device_id is None and android_id:
            device, _ = get_or_create_tablet_device_by_android_id(android_id=android_id)
            tablet_device_id = device.id
        try:
            result = issue_tablet_session_latest_wins(
                queue_entry_id=queue_entry_id,
                created_by_user_id=request.user.id,
                form_locale="de-DE",
                expires_in_minutes=120,
                tablet_device_id=tablet_device_id,
            )
            ctx = {
                **_staff_context(request),
                "entry": entry,
                "intake_form_id": result.intake_form_id,
                "session_id": result.session_id,
            }
            return render(request, "tablet/entry_started.html", ctx)
        except ObjectDoesNotExist:
            ctx = {**_staff_context(request)}
            ctx["message"] = ctx["staff_ui"]["err_session_create_failed"]
            return render(request, "tablet/error.html", ctx, status=404)
    ctx = {**_staff_context(request), "entry": entry}
    return render(request, "tablet/entry_start.html", ctx)


@login_required(login_url="tablet:login")
def tablet_form_view(request: HttpRequest, intake_form_id: UUID) -> HttpResponse:
    """Widok formularza intake dla pacjenta (zgody, anamneza, podpis, submit). Język: ?locale=de|en."""
    if not _tablet_role_ok(request):
        return redirect("tablet:login")
    try:
        intake_form = PatientIntakeForm.objects.select_related(
            "session", "queue_entry", "queue_entry__patient"
        ).get(id=intake_form_id)
    except ObjectDoesNotExist:
        ctx = {**_staff_context(request)}
        ctx["message"] = ctx["staff_ui"]["err_intake_form_not_found"]
        return render(request, "tablet/error.html", ctx, status=404)
    session = intake_form.session
    locale_param = request.GET.get("locale", "").strip().lower()
    if locale_param in ("de", "en", "pl"):
        session.form_locale = (
            "en-GB"
            if locale_param == "en"
            else "pl-PL" if locale_param == "pl" else "de-DE"
        )
        session.save(update_fields=["form_locale"])
    form_locale = session.form_locale or "de-DE"
    is_tablet = request.user.is_tablet
    try:
        context = get_intake_form_context(
            intake_form_id=intake_form_id,
            form_locale=form_locale,
            tablet_restrict_to_today=is_tablet,
            allowed_clinic_site_ids=_resolve_tablet_area_scope_ids(request),
        )
    except ObjectDoesNotExist:
        ctx = {**_staff_context(request)}
        ctx["message"] = ctx["staff_ui"]["err_intake_form_not_found"]
        return render(request, "tablet/error.html", ctx, status=404)
    if context["form_status"] == "SUBMITTED":
        ui = get_form_ui_strings(form_locale)
        locale_param = (
            "en"
            if form_locale.startswith("en")
            else "pl" if form_locale.startswith("pl") else "de"
        )
        return render(
            request,
            "tablet/form_submitted.html",
            {
                "intake_form_id": intake_form_id,
                "ui": ui,
                "form_locale": form_locale,
                "locale_param": locale_param,
            },
        )
    context["intake_form_id"] = str(intake_form_id)
    context["ui"] = get_form_ui_strings(form_locale)
    context["form_locale"] = form_locale
    context["locale_param"] = (
        "en"
        if form_locale.startswith("en")
        else "pl" if form_locale.startswith("pl") else "de"
    )
    template_name = (
        "tablet/form_telederm.html"
        if context.get("process_type") == ProcessType.TELEDERM
        else "tablet/form.html"
    )
    return render(request, template_name, context)
