from .models import Register
from django import forms
from django.contrib.auth.forms import ReadOnlyPasswordHashField
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
import re


login_validator = RegexValidator(
    regex=r'^[\w.]{3,15}$',
    message="Login musi składać się z 3 do 15 znaków."
)

class RegisterCreationForm(forms.ModelForm):

    username = forms.CharField(label='Login', required=True) 
    password1 = forms.CharField(label='Hasło')
    password2 = forms.CharField(label='Powtórz hasło')

    class Meta:
        model = Register
        fields = ['username', 'first_name', 'last_name', 'password1', 'password2']

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if not username:
            raise ValidationError('Login jest wymagany')
        return username

    def clean_last_name(self):
        last_name = self.cleaned_data.get('last_name', '')
        if last_name:
            return last_name.capitalize()
        return last_name

    def clean_first_name(self):
        first_name = self.cleaned_data.get('first_name', '')
        if first_name:
            return first_name.capitalize()
        return first_name

    def clean_password1(self):
        password1 = self.cleaned_data.get('password1')
        if not password1:
            raise ValidationError('Hasło jest wymagane')
        return password1

    def clean_password2(self):
        password2 = self.cleaned_data.get('password2')
        if not password2:
            raise ValidationError('Hasło jest wymagane')
        return password2

    def clean(self):
        cleaned_data = super().clean()
        username = self.cleaned_data.get('username')
     
        if not username:
            self.add_error('username', 'Login jest wymagany.')
            return cleaned_data

        if not re.match(login_validator.regex.pattern, username):
            self.add_error('username', login_validator.message)
            return cleaned_data

        password1 = self.cleaned_data.get('password1')
        if not password1:
            raise ValidationError('Hasło jest wymagane')

        password2 = self.cleaned_data.get('password2')
        if not password2:
            raise ValidationError('Hasło jest wymagane')

        if password1 and password2 and password1 != password2:
            self.add_error('password1', 'Hasła nie są zgodne')
            return cleaned_data

        try:
            validate_password(password1)
        except ValidationError as e:
            self.add_error('password1', e)
            return cleaned_data

        # Sprawdź unikalność
        if Register.objects.filter(username=username).exists():
           self.add_error('username', 'Rejestrator o tym loginie już istnieje.')
        
        return cleaned_data
        
    def save(self, commit=True):
        # Save the provided password in hashed format
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        if commit:
            user.save()
        return user


class RegisterChangeForm(forms.ModelForm):

    username = forms.CharField(label='Login')
    password1 = forms.CharField(label='Nowe hasło', widget=forms.PasswordInput, required=False)
    password2 = forms.CharField(label='Powtórz nowe hasło', widget=forms.PasswordInput, required=False)

    def clean_last_name(self):
        last_name = self.cleaned_data.get('last_name', '')
        if last_name:
            return last_name.capitalize()
        return last_name

    def clean_first_name(self):
        first_name = self.cleaned_data.get('first_name', '')
        if first_name:
            return first_name.capitalize()
        return first_name

    def clean(self):
        cleaned_data = super().clean()
        username = self.cleaned_data.get('username')
     
        if not username:
            self.add_error('username', 'Login jest wymagany.')
            return cleaned_data

        # Sprawdź unikalność username
        qs = Register.objects.filter(username=username)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('Rejestrator o tym loginie już istnieje.')
        
        # Walidacja haseł
        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')
        
        if password1 or password2:
            if not password1:
                self.add_error('password1', 'Hasło jest wymagane jeśli chcesz je zmienić.')
            elif not password2:
                self.add_error('password2', 'Powtórz hasło.')
            elif password1 != password2:
                self.add_error('password2', 'Hasła nie są zgodne.')

        try:
            validate_password(password1)
        except ValidationError as e:
            self.add_error('password1', e)
            return cleaned_data
        
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        
        # Ustaw nowe hasło jeśli zostało podane
        password1 = self.cleaned_data.get('password1')
        if password1:
            user.set_password(password1)
        
        if commit:
            user.save()
        return user

    class Meta:
        model = Register
        fields = ['username', 'first_name', 'last_name']