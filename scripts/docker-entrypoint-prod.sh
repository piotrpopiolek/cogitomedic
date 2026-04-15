#!/bin/sh
set -e
mkdir -p /app/media /app/staticfiles
python manage.py migrate --noinput
python manage.py collectstatic --noinput
exec "$@"
