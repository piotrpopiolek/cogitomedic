"""
Root pytest conftest.

Repository runs: staff-user fixtures; Django via pytest-django (``pytest.ini``).

When copied to ``mutants/conftest.py`` by mutmut (``also_copy``), pins imports to the
mutant workspace and bootstraps Django idempotently across repeated ``pytest.main()``
calls (mutmut #504). Fixture definitions are skipped in that workspace.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_conftest_path = Path(__file__).resolve()
_mutmut_workspace = _conftest_path.parent
_in_mutmut_workspace = _mutmut_workspace.name == "mutants"


def _bootstrap_mutmut_workspace() -> None:
    """Isolate imports to ``mutants/`` and configure Django once per process."""
    mutants_root = str(_mutmut_workspace)
    repo_root = str(_mutmut_workspace.parent)

    # Stats / clean-run must import ``apps.*`` from mutants/, not ``/app/apps/``.
    sys.path = [mutants_root] + [
        entry for entry in sys.path if entry not in {repo_root, mutants_root, ""}
    ]
    if not sys.path or sys.path[0] != mutants_root:
        sys.path.insert(0, mutants_root)

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cogitomedica.settings")

    import django  # noqa: E402

    django.setup()

    from django.test.utils import _TestState  # noqa: E402
    from django.test.utils import setup_test_environment  # noqa: E402

    if not hasattr(_TestState, "saved_data"):
        setup_test_environment()
        # Targets using only ``SimpleTestCase`` do not need a test DB. Add
        # ``DiscoverRunner(keepdb=True).setup_databases()`` when mutating ORM code.


if _in_mutmut_workspace:
    _bootstrap_mutmut_workspace()
else:
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
