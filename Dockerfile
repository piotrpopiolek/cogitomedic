FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# Large wheels (e.g. playwright) can hit transient TLS/stream errors on slow or flaky links.
ENV PIP_DEFAULT_TIMEOUT=300

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        gettext \
        libpq-dev \
        libcairo2 \
        libglib2.0-0 \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libgdk-pixbuf-2.0-0 \
        libffi-dev \
        shared-mime-info \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --retries 15 --timeout 300 -r requirements.txt

COPY . /app

# gettext: compile locale/*/LC_MESSAGES/django.po for AppConfig.verbose_name and Django/Unfold UI strings.
RUN python manage.py compilemessages

EXPOSE 8000
