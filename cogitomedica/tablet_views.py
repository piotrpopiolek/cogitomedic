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

from apps.reception.models import DailyQueue, QueueEntry
from apps.reception.services import issue_tablet_session_latest_wins

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
        try:
            result = issue_tablet_session_latest_wins(
                queue_entry_id=queue_entry_id,
                created_by_user_id=request.user.id,
                form_locale="de-DE",
                expires_in_minutes=120,
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
