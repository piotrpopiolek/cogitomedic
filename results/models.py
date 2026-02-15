from django.db import models
from django.contrib.auth.models import AbstractUser

class User(AbstractUser):
    first_name = models.CharField(max_length=50, verbose_name='Imię')
    last_name = models.CharField(max_length=100, verbose_name='Nazwisko')
    phone_number = models.CharField(max_length=15, null=True, blank=True, verbose_name='Numer telefonu')
    date_last_login = models.DateTimeField(null=True, verbose_name='Ostatnie logowanie')
    is_staff = models.BooleanField(default=False, verbose_name='Konto administracji')
    code = models.CharField(max_length=50, default='', verbose_name='Kod dostępu')

    def __str__(self):
        return "{} {} {}".format(self.first_name, self.last_name, self.username)


class Patient(User):
    
    class Meta:
        proxy = True
        verbose_name = 'Pacjent'
        verbose_name_plural = 'Pacjenci'
    
    def save(self, *args, **kwargs):
        self.is_staff = False
        super().save(*args, **kwargs)

class LabResults(models.Model):
    date_created = models.DateTimeField(auto_now_add=True, verbose_name='Data dodania')
    date_last_readed = models.DateTimeField(null=True, verbose_name='Ostatnie odczytanie')
    date_last_download = models.DateTimeField(null=True, verbose_name='Ostatnie pobranie')
    creator = models.ForeignKey(User, related_name='creator', on_delete=models.PROTECT, verbose_name='Pracownik')
    owner = models.ForeignKey(User, related_name='owner', on_delete=models.CASCADE, verbose_name='Pacjent')
    file = models.FileField(null=True, blank=True, upload_to='results_files/', verbose_name='Wyniki')
    is_sms_sent = models.BooleanField(default=False, verbose_name='Wysłano SMS')

    class Meta:
        verbose_name = 'Wynik badania'
        verbose_name_plural = 'Wyniki badań'

    def __str__(self):
        return "{} {}".format(self.owner, self.file)