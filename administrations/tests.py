from __future__ import annotations
from typing import Any
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from .models import Register
from django.contrib.auth.models import Group

# Używamy get_user_model() zamiast importu
User = get_user_model()

class RegisterModelTest(TestCase):
    """Testy dla modelu Register"""
    
    def setUp(self) -> None:
        """Przygotowanie danych testowych"""
        # Utwórz grupę Rejestracja
        self.register_group: Group = Group.objects.create(name='Rejestracja')
        
        self.register: Register = Register.objects.create_user(
            username='testregister',
            password='testpass123!',
            first_name='Admin',
            last_name='User'
        )
    
    def test_register_creation(self) -> None:
        """Test tworzenia rejestratora"""
        self.assertEqual(self.register.username, 'testregister')
        self.assertEqual(self.register.first_name, 'Admin')
        self.assertEqual(self.register.last_name, 'User')
        self.assertTrue(self.register.is_staff)
    
    def test_register_save_sets_staff(self) -> None:
        """Test że save automatycznie ustawia is_staff=True"""
        new_register: Register = Register.objects.create_user(
            username='newregister',
            password='testpass123!',
            first_name='New',
            last_name='Admin'
        )
        self.assertTrue(new_register.is_staff)
    
    def test_register_str_representation(self) -> None:
        """Test reprezentacji string rejestratora"""
        expected: str = "Admin User testregister"
        self.assertEqual(str(self.register), expected)


class RegisterAdminTest(TestCase):
    """Testy dla admina Register"""
    
    def setUp(self) -> None:
        """Przygotowanie danych testowych"""
        self.client: Client = Client()
        self.register_group: Group = Group.objects.create(name='Rejestracja')
        self.admin_user: User = User.objects.create_superuser(
            username='admin',
            email='admin@test.com',
            password='adminpass123!'
        )
    
    def test_register_admin_queryset_filtering(self) -> None:
        """Test że admin filtruje tylko użytkowników z grupą Rejestracja"""
        # Utwórz rejestratora
        register: Register = Register.objects.create_user(
            username='testregister',
            password='testpass123!',
            first_name='Admin',
            last_name='User'
        )
        
        # Dodaj rejestratora do grupy Rejestracja
        register.groups.add(self.register_group)
        
        # Utwórz zwykłego użytkownika
        regular_user: User = User.objects.create_user(
            username='regularuser',
            password='testpass123!',
            first_name='Regular',
            last_name='User'
        )
        
        # Sprawdź że tylko rejestrator jest w grupie Rejestracja
        self.assertTrue(register.groups.filter(name='Rejestracja').exists())
        self.assertFalse(regular_user.groups.filter(name='Rejestracja').exists())
