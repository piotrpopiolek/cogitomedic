"""
ASGI config for cogitomedica project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cogitomedica.settings')

try:
    from cogitomedica.telemetry import setup_telemetry
    setup_telemetry()
except Exception:
    pass

application = get_asgi_application()
