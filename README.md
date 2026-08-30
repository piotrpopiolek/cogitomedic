# CogitoMedica

Clinic web application for **digital patient intake**, **consent signing**, **medical documentation (Befund)**, and a **patient results portal** — with cloud archiving, SMS logistics, audit trail, and production observability.

**Current release:** [`v1.8.0`](https://github.com/piotrpopiolek/cogitomedic/releases/tag/v1.8.0) · UI languages: **German**, **English**, **Polish**

## Table of contents

- [Overview](#overview)
- [Main capabilities](#main-capabilities)
- [Architecture](#architecture)
- [Tech stack](#tech-stack)
- [API documentation](#api-documentation)
- [Getting started (local)](#getting-started-local)
- [Docker (development)](#docker-development)
- [Production](#production)
- [Quality & CI](#quality--ci)
- [Available commands](#available-commands)
- [Project scope](#project-scope)
- [Project status](#project-status)
- [License](#license)

---

## Overview

CogitoMedica replaces paper-heavy clinic workflows with:

- a **tablet** experience for patients (consents, body map, e-signature),
- **reception** tools for the daily waiting room and intake documents,
- a **doctor** panel for drafts, publish, revise, and concurrent-edit protection,
- a **patient results portal** (verified identity → one-time code → secure PDF download),
- an asynchronous pipeline: **generate PDF → archive upload → SMS notification** (Transactional Outbox + Django 6 Tasks).

Translations are managed in Django Admin and loaded from the database as the runtime source of truth.

Clinic user manuals and internal runbooks are maintained **outside the public repository**. Product behaviour for integrators is described here and in the OpenAPI schema of a running instance.

---

## Main capabilities

| Area | What it does |
|------|----------------|
| **Reception** | Daily waiting room (CRUD + spreadsheet import), start tablet sessions, browse generated intake PDFs in the staff panel |
| **Paper intake** | Controlled paper path for selected queue entries (staff authorization in admin / API) |
| **Patient (tablet)** | Touch-optimized form: read-only demographics, consents, interactive body map, electronic signature |
| **Doctor** | Medical section, draft / publish / amend; shared draft work queue; published documents scoped by ownership rules |
| **Edit session lock** | Concurrent-edit protection for doctor Befund editing (session token + revision checks; external-upload path excluded) |
| **External upload** | Separate flow for lab / external PDFs with staff verification before publish |
| **Backend pipeline** | Outbox-driven PDF generation, archive upload, and SMS; SMS carries a link to the public portal only (not a direct PDF URL); configurable local file retention |
| **Patient results portal** | Phone + date of birth → one-time code → HTTPS download; staff can revoke publication |
| **Accounting** | Weekly first-publication report with per-doctor aggregates and CSV/XLSX export |
| **Audit** | Operational event log with durable entity references for compliance after anonymization |

Access to queue and document APIs is scoped by clinic assignment and staff role.

---

## Architecture

Django project package `cogitomedica/` with domain apps under `apps/`:

| App | Responsibility |
|-----|----------------|
| `reception` | Waiting room, tablet devices, import |
| `intake` | Patient tablet consents / body map / signature |
| `medical` | Befund documents, edit sessions, PDF build, external upload |
| `patient_results` | Patient portal and downloads |
| `outbox` | Transactional outbox |
| `integrations` | External archive and SMS adapters |
| `operations` | Audit events |
| `core` | i18n, shared API helpers |
| `users` | Staff roles and auth |

Deploy configuration lives in `deploy/`. Production Compose: [`docker-compose.prod.yml`](docker-compose.prod.yml).

---

## Tech stack

| Layer | Technologies |
|-------|----------------|
| **Runtime** | Python **3.13**, Django **6.0.8**, Gunicorn (prod) |
| **API** | Django REST Framework, drf-spectacular (OpenAPI) |
| **Database** | PostgreSQL 16 |
| **Admin UI** | django-unfold |
| **PDF** | WeasyPrint |
| **Background work** | Django 6 Tasks (`django.tasks`) + Transactional Outbox |
| **Integrations** | HiDrive (archive), SMSApi (SMS) |
| **Observability** | Sentry, Prometheus, Grafana, Alertmanager, OpenTelemetry |
| **Frontend** | Django templates, HTMX, Alpine.js, SignaturePad.js |
| **Other** | Pillow, bleach, openpyxl, phonenumbers |

---

## API documentation

With the app running locally:

| URL | Description |
|-----|-------------|
| http://127.0.0.1:8000/api/docs/swagger/ | Swagger UI |
| http://127.0.0.1:8000/api/docs/redoc/ | ReDoc |
| http://127.0.0.1:8000/api/schema/ | OpenAPI schema |

Staff list endpoints use offset pagination with a bounded page size (see OpenAPI / `apps/core` helpers). Prefer the schema over hard-coded client assumptions.

---

## Getting started (local)

### Prerequisites

- **Python 3.13** (matches Docker images and CI)
- **PostgreSQL 16** (or use Docker for the database)
- **pip** and a virtual environment

### Setup

1. **Clone**

   ```bash
   git clone https://github.com/piotrpopiolek/cogitomedic.git
   cd cogitomedic
   ```

2. **Virtual environment**

   ```bash
   python -m venv .venv
   # Windows
   .venv\Scripts\activate
   # Linux/macOS
   source .venv/bin/activate
   ```

3. **Dependencies**

   ```bash
   pip install -r requirements.txt
   pip install -r requirements-dev.txt   # lint, typecheck, pytest
   ```

4. **Environment**

   ```bash
   cp .env.example .env
   ```

   (PowerShell: `Copy-Item .env.example .env`)

   Fill secrets and connection settings from [`.env.example`](.env.example). At minimum you need a Django `SECRET_KEY`, database settings, and `ALLOWED_HOSTS`. For real HiDrive / SMS in non-mock mode, supply the credentials documented in that file. **Never commit a filled `.env`.**

   Use `DEBUG=1` only on a local machine. Production must run with `ENVIRONMENT=prod` and debug disabled.

5. **Migrate and run**

   ```bash
   python manage.py migrate
   python manage.py createsuperuser   # optional
   python manage.py runserver
   ```

   App: http://127.0.0.1:8000/ · staff login and Django admin are available after creating a user.

6. **Tablet waiting room**

   Assign each tablet device to a clinic site in Django Admin (**Reception → Tablet devices**). Without assignment the tablet shows an empty queue.

### Static files

- `python manage.py collectstatic` when you need a production-like static tree
- Ensure the process can write under `MEDIA_ROOT` for generated PDFs

---

## Docker (development)

[`docker-compose.yml`](docker-compose.yml) + [`Dockerfile`](Dockerfile) (Python 3.13):

- **`web`** — Django development server on port **8000**
- **`db`** — PostgreSQL 16
- **`scheduler`** — periodic task enqueue loop
- **Observability stack** — metrics, dashboards, and tracing sidecars (default Compose profile)
- Optional Compose profiles for local manual-asset generation (output stays on disk; not part of the public docs tree)

### Start

```bash
cp .env.example .env   # if needed
docker compose up --build
```

App: http://127.0.0.1:8000

Local monitoring UIs (Grafana, Prometheus, etc.) listen on the ports defined in Compose — change default passwords before any shared or exposed environment. Trace export to the collector is off by default; enable it only via `.env` when you need it.

Provisioning configs: [`deploy/`](deploy/).

### Common commands

```bash
docker compose down
docker compose logs -f web
docker compose run --rm web python manage.py migrate
docker compose run --rm web python manage.py createsuperuser
```

Make shortcuts (Git Bash / WSL / Linux):

```bash
make up
make down
make logs
make migrate
make superuser
make pytest
make test-ci
```

### Notes

- Keep secrets in `.env` only.
- Compose sets the database host for app containers automatically.
- Authentication endpoints are rate-limited.
- Reset local DB volumes: `docker compose down -v && docker compose up --build`

---

## Production

**Default stack** ([`docker-compose.prod.yml`](docker-compose.prod.yml)): PostgreSQL, Gunicorn app, background scheduler, and Nginx TLS reverse proxy. Application media is **not** exposed as a public static alias — downloads go through authenticated application flows.

Deploy from **immutable git tags** (e.g. `v1.8.0`) with a clean tree. Images bake the application code (no live bind-mount of the source tree).

Optional **`--profile observability`** starts the metrics/tracing sidecars. Bind them to loopback on the host and reach them only through a trusted channel; do not publish monitoring ports to the public internet.

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml --profile observability up -d --build
```

Production TLS, proxy trust, and related settings are documented as comments in [`.env.example`](.env.example) and the Nginx template under [`deploy/nginx/`](deploy/nginx/). Prefer Let’s Encrypt (or equivalent) certificates mounted from the host.

One-off management (migrations also run when the `web` container starts):

```bash
docker compose -f docker-compose.prod.yml run --rm --entrypoint python web manage.py createsuperuser
```

Operational hardening (backups, tag checkout after history rewrites, smoke checks) belongs in private runbooks — not in this README.

---

## Quality & CI

| Gate | Tooling |
|------|---------|
| Lint | ruff + black ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) |
| Types | mypy |
| Tests | pytest + coverage |
| Mutation pilot | mutmut (`make mutmut-smoke`) |
| Dependencies | scheduled `pip-audit` ([`.github/workflows/security.yml`](.github/workflows/security.yml)) |

CI runs on **push** and **pull_request** to `main`.

Document publishing is designed to be idempotent. Each publication stores an immutable locale for auditable PDF language.

---

## Available commands

Run from the project root (venv activated, or via `docker compose run --rm web …` / `make`).

| Command | Description |
|---------|-------------|
| `python manage.py runserver` | Development server |
| `python manage.py migrate` | Apply migrations |
| `make pytest` | Full pytest suite in Docker `web` |
| `make test-ci` | Migrate + translation checks + pytest |
| `make mutmut-smoke` | Mutation-testing smoke |
| `python manage.py collectstatic` | Collect static files |
| `python manage.py createsuperuser` | Create admin user |
| `python manage.py load_default_translations` | Seed translations from JSON baselines |
| `python manage.py check_translations_completeness` | Validate `de` / `en` / `pl` completeness |
| `python manage.py enqueue_tasks` | One-shot background enqueue |
| `python manage.py run_periodic_tasks` | Periodic enqueue loop |

Background contract: **Django Tasks + Transactional Outbox**. Local default backend favours deterministic development.

---

## Project scope

### In scope

- Reception: daily list (CRUD + spreadsheet import), intake PDF viewer for staff
- Tablet patient app: consents, body map, e-signature
- Doctor module: medical data, draft/publish/amend, edit-session locking
- External PDF upload and verification
- PDF generation and archive upload
- SMS logistics + patient results portal
- Audit trail and accounting first-publication report
- Observability and error tracking
- UI languages: German, English, Polish

### Out of scope

- Patients completing the full medical questionnaire
- Complex BI / data-warehouse reporting
- Direct EMR / vendor queue APIs (import is file-based)
- Integrations beyond the supported archive and SMS providers

---

## Project status

| Phase | Focus | Status |
|-------|--------|--------|
| **1** | Tablets, digital consents, body schema, e-signature; waiting room | Done |
| **2** | Doctor panel, archive upload, SMS, results portal | Done |
| **3** | Spreadsheet import, live archive API, ops hardening | Done (core) |

**In production use** with tagged releases (current: **v1.8.0**).

Scheduled clock-triggered daily import remains a placeholder; spreadsheet import via the staff upload path is available.

---

## License

All rights reserved.

This software and its source code are proprietary. You may not use, copy, modify, distribute, or deploy this project (in whole or in part) without prior written permission from the project owner. For licensing or collaboration inquiries, contact the repository owner.

---

*Internal manuals and VPS runbooks stay out of the public tree. Use this README, OpenAPI docs on a running instance, and tagged releases as the public source of truth.*
