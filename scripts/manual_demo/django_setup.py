"""Django bootstrap for standalone scripts under scripts/."""
from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def setup_django() -> None:
    sys.path.insert(0, str(_REPO_ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cogitomedica.settings")
    import django

    django.setup()
