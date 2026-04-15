"""Covers settings branch when USE_TRUSTED_REVERSE_PROXY is set (fresh settings import)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

_REPO_ROOT = Path(__file__).resolve().parents[2]


class TrustedReverseProxyEnvTests(SimpleTestCase):
    def test_use_trusted_reverse_proxy_sets_secure_proxy_headers(self) -> None:
        code = """
import os
import django

os.environ["DJANGO_SETTINGS_MODULE"] = "cogitomedica.settings"
os.environ["USE_TRUSTED_REVERSE_PROXY"] = "1"
django.setup()
from django.conf import settings as s

assert s.SECURE_PROXY_SSL_HEADER == ("HTTP_X_FORWARDED_PROTO", "https")
assert s.USE_X_FORWARDED_HOST is True
"""
        env = os.environ.copy()
        env["PYTHONPATH"] = str(_REPO_ROOT)
        subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(_REPO_ROOT),
            env=env,
            check=True,
        )
