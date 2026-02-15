from __future__ import annotations
from typing import Any
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from .models import LabResults

# Używamy get_user_model() zamiast importu
User = get_user_model()

class UserModelTest(TestCase):
    """Testy dla modelu User"""
    
    def setUp(self) -> None:
        """Przygotowanie danych testowych"""
        self.user: User = User.objects.create_user(
            username='testuser',
            password='testpass123!',
            first_name='Jan',
            last_name='Kowalski',
            phone_number='123456789'
        )
    
    def test_user_creation(self) -> None:
        """Test tworzenia użytkownika"""
        self.assertEqual(self.user.username, 'testuser')
        self.assertEqual(self.user.first_name, 'Jan')
        self.assertEqual(self.user.last_name, 'Kowalski')
        self.assertEqual(self.user.phone_number, '123456789')
    
    def test_user_str_representation(self) -> None:
        """Test reprezentacji string użytkownika"""
        expected: str = "Jan Kowalski testuser"
        self.assertEqual(str(self.user), expected)


class LabResultsModelTest(TestCase):
    """Testy dla modelu LabResults"""
    
    def setUp(self) -> None:
        """Przygotowanie danych testowych"""
        self.creator: User = User.objects.create_user(
            username='creator',
            password='testpass123!',
            first_name='Dr',
            last_name='Smith'
        )
        self.owner: User = User.objects.create_user(
            username='owner',
            password='testpass123!',
            first_name='John',
            last_name='Doe'
        )
        self.lab_result: LabResults = LabResults.objects.create(
            creator=self.creator,
            owner=self.owner
        )
    
    def test_lab_results_creation(self) -> None:
        """Test tworzenia wyniku badań"""
        self.assertEqual(self.lab_result.creator, self.creator)
        self.assertEqual(self.lab_result.owner, self.owner)
        self.assertIsNotNone(self.lab_result.date_created)


class ViewsTest(TestCase):
    """Testy dla widoków"""
    
    def setUp(self) -> None:
        """Przygotowanie danych testowych"""
        self.client: Client = Client()
        self.user: User = User.objects.create_user(
            username='testuser',
            password='testpass123!',
            first_name='Jan',
            last_name='Kowalski'
        )
    
    def test_index_view_requires_login(self) -> None:
        """Test że widok index wymaga logowania"""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 302)  # Redirect to login
    
    def test_index_view_with_login(self) -> None:
        """Test widoku index po zalogowaniu"""
        self.client.login(username='testuser', password='testpass123!')
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
