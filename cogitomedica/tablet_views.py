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
from django.views.decorators.http import require_http_methods

from apps.intake.models import PatientIntakeForm
from apps.intake.services import get_intake_form_context
from apps.reception.models import DailyQueue, QueueEntry
from apps.reception.services import get_or_create_tablet_device_by_android_id, issue_tablet_session_latest_wins

from cogitomedica.tablet_i18n import get_form_ui_strings

TABLET_ALLOWED_ROLES = {"TABLET", "RECEPTION", "ADMIN"}


def _tablet_role_ok(request: HttpRequest) -> bool:
    return getattr(request.user, "role", None) in TABLET_ALLOWED_ROLES


@require_http_methods(["GET", "POST"])
def tablet_login_view(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated and _tablet_role_ok(request):
        return redirect("tablet:home")
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)
        if user is not None and getattr(user, "role", None) in TABLET_ALLOWED_ROLES:
            login(request, user)
            return redirect(request.GET.get("next") or "tablet:home")
        return render(request, "tablet/login.html", {"error": "Nieprawidłowy login lub brak uprawnień tabletu."})
    return render(request, "tablet/login.html", {})


@require_http_methods(["GET", "POST"])
def tablet_logout_view(request: HttpRequest) -> HttpResponse:
    logout(request)
    return redirect("tablet:login")


@login_required(login_url="tablet:login")
def tablet_home_view(request: HttpRequest) -> HttpResponse:
    if not _tablet_role_ok(request):
        return redirect("tablet:login")
    today = timezone.now().date()
    queues = DailyQueue.objects.filter(queue_date=today).select_related(
        "clinic_site", "consulting_room"
    ).order_by("clinic_site__name", "consulting_room__name")
    return render(request, "tablet/home.html", {"queues": queues, "today": today})


@login_required(login_url="tablet:login")
def tablet_queue_entries_view(request: HttpRequest, daily_queue_id: UUID) -> HttpResponse:
    if not _tablet_role_ok(request):
        return redirect("tablet:login")
    try:
        queue = DailyQueue.objects.select_related("clinic_site", "consulting_room").get(
            id=daily_queue_id
        )
    except ObjectDoesNotExist:
        return render(request, "tablet/error.html", {"message": "Kolejka nie istnieje."}, status=404)
    entries = (
        QueueEntry.objects.filter(daily_queue_id=daily_queue_id)
        .select_related("patient")
        .order_by("position_no")
    )
    return render(
        request,
        "tablet/queue_entries.html",
        {"queue": queue, "entries": entries},
    )


@require_http_methods(["GET", "POST"])
@login_required(login_url="tablet:login")
def tablet_entry_start_view(request: HttpRequest, queue_entry_id: UUID) -> HttpResponse:
    if not _tablet_role_ok(request):
        return redirect("tablet:login")
    try:
        entry = QueueEntry.objects.select_related("daily_queue", "patient").get(
            id=queue_entry_id
        )
    except ObjectDoesNotExist:
        return render(request, "tablet/error.html", {"message": "Wpis kolejki nie istnieje."}, status=404)
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
            return render(
                request,
                "tablet/entry_started.html",
                {
                    "entry": entry,
                    "intake_form_id": result.intake_form_id,
                    "session_id": result.session_id,
                },
            )
        except ObjectDoesNotExist:
            return render(request, "tablet/error.html", {"message": "Nie można utworzyć sesji."}, status=404)
    return render(request, "tablet/entry_start.html", {"entry": entry})


@login_required(login_url="tablet:login")
def tablet_form_view(request: HttpRequest, intake_form_id: UUID) -> HttpResponse:
    """Widok formularza intake dla pacjenta (zgody, anamneza, podpis, submit). Język: ?locale=de|en."""
    if not _tablet_role_ok(request):
        return redirect("tablet:login")
    try:
        intake_form = (
            PatientIntakeForm.objects.select_related("session", "queue_entry", "queue_entry__patient")
            .get(id=intake_form_id)
        )
    except ObjectDoesNotExist:
        return render(request, "tablet/error.html", {"message": "Formularz nie istnieje lub brak dostępu."}, status=404)
    session = intake_form.session
    locale_param = request.GET.get("locale", "").strip().lower()
    if locale_param in ("de", "en"):
        session.form_locale = "en-GB" if locale_param == "en" else "de-DE"
        session.save(update_fields=["form_locale"])
    form_locale = session.form_locale or "de-DE"
    is_tablet = getattr(request.user, "role", None) == "TABLET"
    try:
        context = get_intake_form_context(
            intake_form_id=intake_form_id,
            form_locale=form_locale,
            tablet_restrict_to_today=is_tablet,
        )
    except ObjectDoesNotExist:
        return render(request, "tablet/error.html", {"message": "Formularz nie istnieje lub brak dostępu."}, status=404)
    if context["form_status"] == "SUBMITTED":
        ui = get_form_ui_strings(form_locale)
        locale_param = "en" if form_locale.startswith("en") else "de"
        return render(
            request,
            "tablet/form_submitted.html",
            {"intake_form_id": intake_form_id, "ui": ui, "form_locale": form_locale, "locale_param": locale_param},
        )
    context["intake_form_id"] = str(intake_form_id)
    context["ui"] = get_form_ui_strings(form_locale)
    context["form_locale"] = form_locale
    context["locale_param"] = "en" if form_locale.startswith("en") else "de"
    return render(request, "tablet/form.html", context)
