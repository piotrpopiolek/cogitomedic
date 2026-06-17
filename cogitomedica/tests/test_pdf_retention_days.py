"""Default PDF retention window for patient portal / local MEDIA_ROOT cleanup."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

_REPO_ROOT = Path(__file__).resolve().parents[2]


class PdfRetentionDaysDefaultTests(SimpleTestCase):
    def test_settings_default_pdf_retention_days_is_sixty_without_env(self) -> None:
        code = """
import os
import sys
import importlib

import dotenv

dotenv.load_dotenv = lambda *args, **kwargs: None
os.environ.pop("PDF_RETENTION_DAYS", None)
os.environ["DJANGO_SETTINGS_MODULE"] = "cogitomedica.settings"

for mod in list(sys.modules):
    if mod == "django.conf" or mod.startswith("cogitomedica.settings"):
        del sys.modules[mod]

import django

django.setup()
from django.conf import settings as s

assert s.PDF_RETENTION_DAYS == 60, s.PDF_RETENTION_DAYS
"""
        env = os.environ.copy()
        env.pop("PDF_RETENTION_DAYS", None)
        env["PYTHONPATH"] = str(_REPO_ROOT)
        subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(_REPO_ROOT),
            env=env,
            check=True,
        )
