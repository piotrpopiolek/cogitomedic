from .forms import RegisterCreationForm, RegisterChangeForm
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin, Group


class RegisterAdmin(BaseUserAdmin):
    
    form = RegisterChangeForm
    add_form = RegisterCreationForm
    
    list_display = ['username', 'last_name', 'first_name', 'date_joined', 'date_last_login']
    list_filter = ['date_joined']
    search_fields = ['username', 'last_name', 'first_name']
    ordering = ['-date_joined']
    
    fieldsets = [
        ('Dane logowania', {
            'fields': ['username', 'password1', 'password2'],
        }),
        ('Dane podstawowe', {
            'fields': ['first_name', 'last_name'],
        })
    ]
    
    add_fieldsets = [
        ('Dane logowania', {
            'fields': ['username', 'password1', 'password2'],
        }),
        ('Dane podstawowe', {
            'fields': ['first_name', 'last_name'],
        })
    ]
    
    def get_queryset(self, request):
        return super().get_queryset(request).filter(groups__name='Rejestracja')
    
    def save_model(self, request, obj, form, change):
        obj.is_staff = True
        obj.is_superuser = True
        super().save_model(request, obj, form, change)
        if not change:  # Nowy użytkownik
            register_group = Group.objects.get(name='Rejestracja')
            obj.groups.add(register_group)
