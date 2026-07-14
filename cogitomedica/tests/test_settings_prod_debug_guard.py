"""Covers DEBUG guard when ENVIRONMENT=prod (fresh settings import)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_settings_snippet(code: str) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_REPO_ROOT)
    subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(_REPO_ROOT),
        env=env,
        check=True,
    )


class ProdDebugGuardTests(SimpleTestCase):
    def test_prod_forces_debug_false_even_when_env_debug_one(self) -> None:
        code = """
import os
import django

os.environ["DJANGO_SETTINGS_MODULE"] = "cogitomedica.settings"
os.environ["ENVIRONMENT"] = "prod"
os.environ["SECRET_KEY"] = "test-secret-for-prod"
os.environ["PATIENT_RESULTS_OTP_PEPPER"] = "test-pepper"
os.environ["HIDRIVE_USE_MOCK"] = "1"
os.environ["DEBUG"] = "1"
django.setup()
from django.conf import settings as s

assert s.DEBUG is False
"""
        _run_settings_snippet(code)

    def test_dev_respects_debug_env_one(self) -> None:
        code = """
import os
import django

os.environ["DJANGO_SETTINGS_MODULE"] = "cogitomedica.settings"
os.environ["ENVIRONMENT"] = "dev"
os.environ["DEBUG"] = "1"
django.setup()
from django.conf import settings as s

assert s.DEBUG is True
"""
        _run_settings_snippet(code)

    def test_dev_respects_debug_env_zero(self) -> None:
        code = """
import os
import django

os.environ["DJANGO_SETTINGS_MODULE"] = "cogitomedica.settings"
os.environ["ENVIRONMENT"] = "dev"
os.environ["DEBUG"] = "0"
django.setup()
from django.conf import settings as s

assert s.DEBUG is False
"""
        _run_settings_snippet(code)
