from results.models import User

class Register(User):
    
    class Meta:
        proxy = True
        verbose_name = 'Rejestrator'
        verbose_name_plural = 'Rejestratorzy'
    
    def save(self, *args, **kwargs):
        self.is_staff = True  # Automatycznie ustaw jako rejestrator
        super().save(*args, **kwargs)
        
