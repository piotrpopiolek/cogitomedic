import pytest
from django.test import Client

from apps.core.api_utils import assign_group_to_test_user
from apps.users.models import StaffUser


@pytest.fixture
def staff_user(db):
    return StaffUser.objects.create_user(username="testuser", password="testpass")


@pytest.fixture
def reception_user(staff_user):
    assign_group_to_test_user(staff_user, "Reception")
    return staff_user


@pytest.fixture
def doctor_user(staff_user):
    assign_group_to_test_user(staff_user, "Doctor")
    return staff_user


@pytest.fixture
def admin_user(staff_user):
    assign_group_to_test_user(staff_user, "Admin")
    return staff_user


@pytest.fixture
def tablet_user(staff_user):
    assign_group_to_test_user(staff_user, "Tablet")
    return staff_user


@pytest.fixture
def auth_client(staff_user):
    client = Client()
    client.force_login(staff_user)
    return client


@pytest.fixture
def tmp_media(tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path / "media")
    return tmp_path / "media"
