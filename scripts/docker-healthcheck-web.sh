#!/bin/sh
set -e
cd /app
python -c "import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','cogitomedica.settings'); import django; django.setup(); from django.db import connection; connection.ensure_connection()"
