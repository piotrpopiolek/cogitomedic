"""Default OUTBOX_MAX_RETRIES when env is unset."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

_REPO_ROOT = Path(__file__).resolve().parents[2]


class OutboxMaxRetriesDefaultTests(SimpleTestCase):
    def test_settings_default_outbox_max_retries_is_three_without_env(self) -> None:
        code = """
import os
import sys

import dotenv

dotenv.load_dotenv = lambda *args, **kwargs: None
os.environ.pop("OUTBOX_MAX_RETRIES", None)
os.environ["DJANGO_SETTINGS_MODULE"] = "cogitomedica.settings"

for mod in list(sys.modules):
    if mod == "django.conf" or mod.startswith("cogitomedica.settings"):
        del sys.modules[mod]

import django

django.setup()
from django.conf import settings as s

assert s.OUTBOX_MAX_RETRIES == 3, s.OUTBOX_MAX_RETRIES
"""
        env = os.environ.copy()
        env.pop("OUTBOX_MAX_RETRIES", None)
        env["PYTHONPATH"] = str(_REPO_ROOT)
        subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(_REPO_ROOT),
            env=env,
            check=True,
        )
