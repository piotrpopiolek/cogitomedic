from .models import User, LabResults
from django import forms
from django.contrib.auth.forms import ReadOnlyPasswordHashField
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django_select2.forms import Select2Widget
import os
import re

phone_validator = RegexValidator(
    regex=r'^\d{9,11}$',
    message="Numer telefonu musi być w formacie: '01511234567'. Maksymalnie 11 cyfr."
)

class PatientCreationForm(forms.ModelForm):

    phone_number = forms.CharField(label='Numer telefonu', required=True) 
    password1 = forms.CharField(label='Kod dostępu')
    password2 = forms.CharField(label='Powtórz kod dostępu')

    class Meta:
        model = User
        fields = ['phone_number', 'password1', 'password2']

    def clean_phone_number(self):
        phone_number = self.cleaned_data.get('phone_number')
        if not phone_number:
            raise ValidationError('Numer telefonu jest wymagany')
        return phone_number

    def clean_last_name(self):
        last_name = self.cleaned_data.get('last_name').capitalize()
        return last_name

    def clean_first_name(self):
        first_name = self.cleaned_data.get('first_name').capitalize()
        return first_name

    def clean_password1(self):
        password1 = self.cleaned_data.get('password1')
        if not password1:
            raise ValidationError('Kod dostępu jest wymagany')
        return password1

    def clean_password2(self):
        password2 = self.cleaned_data.get('password2')
        if not password2:
            raise ValidationError('Kod dostępu jest wymagany')
        return password2

    def clean(self):
        cleaned_data = super().clean()
        phone_number = self.cleaned_data.get('phone_number')
     
        if not phone_number:
            self.add_error('phone_number', 'Numer telefonu jest wymagany.')
            return cleaned_data

        if not re.match(phone_validator.regex.pattern, phone_number):
            self.add_error('phone_number', phone_validator.message)
            return cleaned_data
                
        qs = User.objects.filter(username=phone_number)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('Użytkownik o tym numerze telefonu już istnieje.')
        
        # Walidacja haseł
        password1 = self.cleaned_data.get('password1')
        if not password1:
            raise ValidationError('Kod dostępu jest wymagany')

        password2 = self.cleaned_data.get('password2')
        if not password2:
            raise ValidationError('Kod dostępu jest wymagany')

        if password1 and password2 and password1 != password2:
            self.add_error('password1', 'Kody dostępu nie są zgodne')
        
        # Ustaw username na phone_number
        cleaned_data['username'] = phone_number
        
        return cleaned_data
        
    def save(self, commit=True):
        # Save the provided password in hashed format
        user = super().save(commit=False)
        user.phone_number = self.cleaned_data['phone_number']
        user.username = self.cleaned_data['phone_number']
        user.code = self.cleaned_data['password1']
        user.set_password(self.cleaned_data['password1'])
        if commit:
            user.save()
        return user


class PatientChangeForm(forms.ModelForm):

    phone_number = forms.CharField(label='Numer telefonu')
    password = ReadOnlyPasswordHashField()
    code = forms.CharField(
        label='Kod dostępu',
        widget=forms.PasswordInput(
            render_value=True,
            attrs={'onfocus': "this.type='text'", 'readonly': 'readonly'}
        )
    )

    def clean_last_name(self) -> str:
        last_name: str = self.cleaned_data.get('last_name', '')
        return last_name.capitalize()

    def clean_first_name(self):
        first_name = self.cleaned_data.get('first_name').capitalize()
        return first_name

    def clean(self):
        cleaned_data = super().clean()
        phone_number = self.cleaned_data.get('phone_number')
     
        if not phone_number:
            self.add_error('phone_number', 'Numer telefonu jest wymagany.')

        if not re.match(phone_validator.regex.pattern, phone_number):
            self.add_error('phone_number', phone_validator.message)
                
        qs = User.objects.filter(username=phone_number)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('Użytkownik o tym numerze telefonu już istnieje.')

        # Ustaw username na phone_number
        cleaned_data['username'] = phone_number
        
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self.cleaned_data['phone_number']
        if commit:
            user.save()
        return user

    class Meta:
        model = User
        fields = ['phone_number']

    
class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True

class MultipleFileField(forms.FileField):
    widget = MultipleFileInput

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        allowed_extensions = ['.pdf', '.jpg', '.jpeg', '.png', '.webp']
        if isinstance(data, (list, tuple)):
            result = []
            for d in data:
                ext = os.path.splitext(d.name)[1].lower()
                if ext not in allowed_extensions:
                    raise ValidationError(f"Niedozwolony format pliku: {ext}. Dozwolone: PDF, JPG, PNG, WEBP.")
                result.append(single_file_clean(d, initial))
        else:
            ext = os.path.splitext(data.name)[1].lower()
            if ext not in allowed_extensions:
                raise ValidationError(f"Niedozwolony format pliku: {ext}. Dozwolone: PDF, JPG, PNG, WEBP.")
            result = single_file_clean(data, initial)
        return result

class LabResultsChangeForm(forms.ModelForm):

    owner = forms.ModelChoiceField(
        label='Pacjent',
        queryset=User.objects.filter(groups__name='Pacjent').exclude(owner__isnull=False).order_by('last_name'),
        widget=Select2Widget
    )
    files = MultipleFileField(
        label='Wyniki',
        required=True
    )

    class Meta:
        model = LabResults
        fields = ['owner']


class LabResultsCreationForm(forms.ModelForm):

    owner = forms.ModelChoiceField(
        label='Pacjenci bez wyników',
        queryset=User.objects.filter(groups__name='Pacjent').exclude(owner__isnull=False).order_by('last_name'),
        widget=Select2Widget
    )
    files = MultipleFileField(
        label='Wyniki',
        required=True
    )

    class Meta:
        model = LabResults
        fields = ['owner']


