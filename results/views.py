from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LogoutView
from django.shortcuts import render
from .models import LabResults
from django.http import FileResponse, Http404, HttpResponseForbidden
from django.conf import settings
import os
from django.utils import translation
from django.contrib.auth.views import LoginView
from django.contrib.auth.forms import AuthenticationForm
import sentry_sdk
from django.utils import timezone

class CustomGermanAuthenticationForm(AuthenticationForm):
    error_messages = {
        "invalid_login": (
            "Ungültige Telefonnummer oder falscher Zugangscode"
        )
    }

class GermanLoginView(LoginView):
    template_name = 'registration/login.html'
    authentication_form = CustomGermanAuthenticationForm

    def dispatch(self, request, *args, **kwargs):
        with translation.override('de'):
            response = super().dispatch(request, *args, **kwargs)
            return response

class logoutView(LogoutView):
    next_page = 'accounts:login'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.user.is_staff:
            self.template_name = settings.LOGOUT_TEMPLATE_ADMIN
        return super().dispatch(request, *args, **kwargs)

@login_required
def index(request):
    user = request.user
    print(user.first_name)
    file = LabResults.objects.filter(owner=user).last()

    # Logowanie do Sentry
    sentry_sdk.capture_message(f"Użytkownik {user.username} wszedł na główny widok", level="info")
    
    # Aktualizacja pola date_last_login w modelu User
    user.date_last_login = timezone.now()
    user.save()

    context = {
        'user': user
    }

    if file:
        context['file'] = file.file

    return render(request, "results.html", context)

@login_required
def download_file(request, path):
    try:
        lab_result = LabResults.objects.get(file=path)
    except LabResults.DoesNotExist:
        raise Http404("Plik nie istnieje.")

    user = request.user
    # Sprawdź, czy użytkownik jest właścicielem lub twórcą wyniku
    if lab_result.owner != user and lab_result.creator != user and not user.is_staff:
        return HttpResponseForbidden("Nie masz uprawnień do pobrania tego pliku.")

    # Logowanie do Sentry
    sentry_sdk.capture_message(f"Użytkownik {user.username} pobrał plik: {path}", level="info")
    
    # Aktualizacja pola date_last_download w modelu
    lab_result.date_last_download = timezone.now()
    lab_result.save()

    response = FileResponse(open(os.path.join(settings.MEDIA_ROOT, path), 'rb'), content_type='application/pdf')
    return response