from .forms import PatientCreationForm, PatientChangeForm, LabResultsCreationForm, LabResultsChangeForm
from .models import Patient, LabResults
from PIL import Image
from PyPDF2 import PdfFileMerger, PdfReader, PdfWriter
from administrations.admin import RegisterAdmin
from administrations.models import Register
from django.contrib import admin
from django.contrib.admin import AdminSite
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin, Group
from django.core.files.base import ContentFile
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from smsapi.client import SmsApiPlClient
from smsapi.exception import SmsApiException
from django.urls import path
from django.http import FileResponse, Http404, HttpResponseForbidden
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.utils.html import format_html
import datetime
import io
import os
import unicodedata

class LabAdminSite(AdminSite):
    site_header = "Panel administracyjny"
    site_title = "Panel administracyjny"
    index_title = "Witaj w panelu administracyjnym"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('pdf/<path:path>/', self.admin_view(self.download_pdf), name='admin_download_pdf'),
        ]
        return custom_urls + urls

    def download_pdf(self, request, path):
        """Custom view do pobierania plików PDF z autoryzacją admin"""
        if not request.user.is_staff:
            return HttpResponseForbidden("Brak uprawnień administratora.")
        
        try:
            lab_result = LabResults.objects.get(file=path)
        except LabResults.DoesNotExist:
            raise Http404("Plik nie istnieje.")

        # Sprawdź czy plik fizycznie istnieje
        file_path = os.path.join(settings.MEDIA_ROOT, path)
        if not os.path.exists(file_path):
            raise Http404("Plik nie został znaleziony na serwerze.")

        # Sprawdź czy ścieżka nie zawiera niebezpiecznych elementów
        if '..' in path or path.startswith('/'):
            return HttpResponseForbidden("Nieprawidłowa ścieżka do pliku.")

        try:
            response = FileResponse(
                open(file_path, 'rb'), 
                content_type='application/pdf',
                filename=os.path.basename(path)
            )
            return response
        except IOError:
            raise Http404("Błąd podczas otwierania pliku.")


class PatientAdmin(BaseUserAdmin):
   
    form = PatientChangeForm
    add_form = PatientCreationForm
    
    list_display = ['last_name', 'first_name', 'phone_number', 'date_joined', 'date_last_login']
    list_filter = ['date_joined', 'date_last_login']
    search_fields = ['phone_number', 'last_name', 'first_name']
    ordering = ['-date_joined']
    
    fieldsets = [
        ('Dane logowania', {
            'fields': ['phone_number', 'code'],
        }),
        ('Dane podstawowe', {
            'fields': ['first_name', 'last_name'],
        })
    ]
    
    add_fieldsets = [
        ('Dane logowania', {
            'fields': ['phone_number', 'password1', 'password2'],
        }),
        ('Dane podstawowe', {
            'fields': ['first_name', 'last_name'],
        }),
    ]
    
    def get_queryset(self, request):
        return super().get_queryset(request).filter(groups__name='Pacjent')
    
    def save_model(self, request, obj, form, change):
        if not change:  # Nowy użytkownik
            obj.is_staff = False
            obj.username = obj.phone_number
        super().save_model(request, obj, form, change)
        if not change:  # Tylko dla nowych użytkowników
            patient_group = Group.objects.get(name='Pacjent')
            obj.groups.add(patient_group)


class LabResultsAdmin(admin.ModelAdmin):

    form = LabResultsChangeForm
    add_form = LabResultsCreationForm

    list_display = ['date_created', 'owner', 'file_link', 'date_last_download', 'is_sms_sent', 'creator']
    search_fields = ['owner', 'creator', 'is_sms_sent']
    ordering = ['-date_created', 'owner', 'creator', 'is_sms_sent']
    list_filter = ['date_created', 'creator', 'is_sms_sent']
    date_hierarchy = 'date_created'

    def file_link(self, obj):
        """Custom field wyświetlający link do pobierania PDF"""
        if obj.file:
            return format_html('<a href="/admin/pdf/{}" target="_blank">{}</a>', obj.file, obj.file)
        return '-'
    file_link.short_description = 'WYNIKI'
    file_link.admin_order_field = 'file'

    def get_form(self, request, obj=None, **kwargs):
        if obj is None:  # Formularz dodawania
            return self.add_form
        else:  # Formularz edycji
            return super().get_form(request, obj, **kwargs)

    def merge_pdfs(self, files):
        pdf_writer = PdfWriter()
        for file in files:
            file_name, extension = os.path.splitext(file.name)
            extension = extension.lower()
            if extension == '.pdf':
                pdf_reader = PdfReader(file)
                for page in pdf_reader.pages:
                    pdf_writer.add_page(page)
            else:
                # Otwórz obraz i przekonwertuj do PDF w pamięci
                img = Image.open(file)
                img_converted = img.convert('RGB')
                img_bytes = io.BytesIO()
                img_converted.save(img_bytes, format='PDF')
                img_bytes.seek(0)
                pdf_reader = PdfReader(img_bytes)
                for page in pdf_reader.pages:
                    pdf_writer.add_page(page)
        output = io.BytesIO()
        pdf_writer.write(output)
        output.seek(0)
        return output

    def slugify(self, value):
        value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
        return value.replace(' ', '_')

    def save_model(self, request, obj, form, change):
        if not change:  # Jeśli to jest dodawanie nowego obiektu

            form = LabResultsCreationForm(request.POST, request.FILES)
            files = request.FILES.getlist('files')

            # Posortuj listę plików według rozszerzeń (typów plików) w odwrotnej kolejności
            sorted_files = sorted(files, key=lambda x: os.path.splitext(x.name)[1], reverse=True)

            if form.is_valid():
                merged_pdf = self.merge_pdfs(sorted_files)
                lab_result = form.save(commit=False)
                lab_result.owner = form.cleaned_data['owner']
                lab_result.creator = request.user
                owner = form.cleaned_data['owner']
                filename = f"{self.slugify(owner.first_name)}_{self.slugify(owner.last_name)}_{owner.phone_number}.pdf"
                lab_result.file.save(filename, ContentFile(merged_pdf.read()))

                message = 'Ihre Untersuchungsergebnisse vom ' + datetime.datetime.now().strftime('%d.%m.%Y') + ' sind jetzt unter https://ergebnisse.cogitomedica.de/ zu finden. Zur Anmeldung nutzen Sie bitte den Abholcode und Ihre Handynummer.'
                if(owner.code):
                    message = 'Ihre Untersuchungsergebnisse vom ' + datetime.datetime.now().strftime('%d.%m.%Y') + ' sind jetzt unter https://ergebnisse.cogitomedica.de/ zu finden. Zur Anmeldung nutzen Sie bitte den Abholcode: ' + str(owner.code) + ' und Ihre Handynummer'
                if(owner.phone_number):
                    token = os.environ.get('SMS_API')
                    
                    if token:  # Sprawdź czy token istnieje
                        client = SmsApiPlClient(access_token=token)
                        
                        try:
                            # Usuń pierwszy znak '0' jeśli numer zaczyna się od tego znaku
                            phone_number = owner.phone_number[1:] if owner.phone_number.startswith('0') else owner.phone_number
                            
                            if(len(phone_number) > 9):
                                phone_number = '+49' + phone_number
                                send_results = client.sms.send(to=phone_number, message=message)
                            else:
                                send_results = client.sms.send(to=phone_number, message=message)
                            lab_result.is_sms_sent = True
                            for result in send_results:
                                print(result.id, result.points, result.error)
                        except SmsApiException as e:
                            print(e.message, e.code)
                    else:
                        print("Błąd: Brak tokenu SMS_API w zmiennych środowiskowych")
                lab_result.save()
        else:
            obj.creator = request.user
            super().save_model(request, obj, form, change)


# Rejestracja w customowym adminie
admin_site = LabAdminSite()
admin_site.register(Patient, PatientAdmin)
admin_site.register(LabResults, LabResultsAdmin)
admin_site.register(Register, RegisterAdmin)