# Cogitomedica Digital Consents

## Table of Contents

- [Project Description](#project-description)
- [API Documentation](#api-documentation)
- [Tech Stack](#tech-stack)
- [Getting Started Locally](#getting-started-locally)
- [Docker Quick Start](#docker-quick-start)
- [Monitoring services](#monitoring-services)
- [Available Scripts](#available-scripts)
- [Project Scope](#project-scope)
- [Project Status](#project-status)
- [License](#license)

---

## Project Description

**Cogitomedica Digital Consents** is a web application that digitizes the patient intake process, consent signing, and medical documentation in a clinical setting. It replaces paper-based workflows with a tablet solution for patients and a management panel for staff.

**Goals:**

- Streamline reception and doctor workflows
- Ensure data security and compliance
- Automate archiving and patient notifications

**User manuals (Polish):** step-by-step guides for Reception, Tablet, Doctor, Manager, Admin, and the patient results portal — see [`docs/manual/README.md`](docs/manual/README.md).

**Main capabilities:**

- **Reception:** Manage the daily patient list (waiting room), add patients manually or via daily file import, start tablet form sessions without one-time token links; browse generated intake PDFs (list, filters, detail, inline preview) in the panel at `/admin/intake-documents/`
- **Admin / Manager (paper path):** Authorize or revoke the paper-intake path for a queue entry from **`/admin/paper-intake/`** (Unfold HTML under `/admin/`); REST clients use `/api/v1/queue-entries/<uuid>/paper-intake-authorization` with clinic-site scope
- **Patient (tablet):** Touch-optimized form with read-only personal data, consent checkboxes, interactive body map, and electronic signature
- **Doctor/Staff:** View completed forms, fill medical section, save as draft or publish, edit published documents and resend. **Doctor panel:** all doctors share the **DRAFT** work queue (and queue entries awaiting first document creation); **PUBLISHED** documents are scoped to the **creator** of the medical record and optionally the **assigned doctor** on the daily queue when that field is used.
- **Backend:** Asynchronous pipeline (`GENERATE_PDF` -> `HIDRIVE_UPLOAD` -> `SMS_SEND`) processed through Django 6 Tasks (`django.tasks`) + Transactional Outbox, HiDrive API archiving (OAuth2 refresh token; mock switchable), SMS (logistic-only: „Nowa dokumentacja w Cogito“) via SMSApi, 30-day retention policy for local PDFs
- **Patient results portal:** 4-step process implemented in `apps/patient_results`: SMS logistic → portal login by phone+DOB → OTP (15 min) → PDF download via HTTPS (RODO/BÄK compliant; doctor can revoke publication)

The user interface and translation layer support **German**, **English**, and **Polish**.

Translations are managed in Django Admin and loaded from the database as the single runtime source of truth (DB-only, no code fallback at runtime).

---

## API Documentation

- **Interactive docs (OpenAPI/Swagger):** [http://127.0.0.1:8000/api/docs/swagger/](http://127.0.0.1:8000/api/docs/swagger/) (Swagger UI) and [http://127.0.0.1:8000/api/docs/redoc/](http://127.0.0.1:8000/api/docs/redoc/) (ReDoc). Schema: `/api/schema/`.
- **List pagination (staff API):** offset lists use `page` (default `1`) and `page_size` (default **20**, max **100**). List endpoints that take `limit` (recepcja, outbox, intake-outbox, import batches, …) use the same defaults and cap via `parse_list_limit` → `DEFAULT_LIST_LIMIT` / `MAX_LIST_LIMIT` defined in **`apps/core/constants.py`** (importowalne także z `apps.core.api_utils` dla kompatybilności wstecznej).
- **Written plans:** Polish [`.ai/api-plan-pl.md`](.ai/api-plan-pl.md), English [`.ai/api-plan.md`](.ai/api-plan.md).

---

## Tech Stack

| Layer | Technologies |
|-------|--------------|
| **Backend** | Python, Django 6.0.2 |
| **Database** | PostgreSQL |
| **PDF** | WeasyPrint (HTML/CSS → PDF; Unicode, embed images as base64). |
| **Scheduling** | Django 6 Tasks (`django.tasks`) with command-driven enqueueing (`manage.py enqueue_tasks`) |
| **SMS** | smsapi-client |
| **Monitoring & Observability** | Sentry, Prometheus OSS, Grafana OSS, Alertmanager |
| **Config** | python-dotenv |
| **Frontend** | Django templates, HTMX, Alpine.js, SignaturePad.js, Tailwind CSS (per implementation plan) |
| **Other** | Pillow, pycryptodome, requests, bleach |

---

## Getting Started Locally

### Prerequisites

- **Python** 3.9+ (recommended: 3.9–3.12)
- **PostgreSQL** (running and accessible)
- **pip** and a virtual environment

### Setup

1. **Clone the repository**

   ```bash
   git clone <repository-url>
   cd cogitomedica
   ```

2. **Create and activate a virtual environment**

   ```bash
   python -m venv venv
   # Windows
   venv\Scripts\activate
   # Linux/macOS
   source venv/bin/activate
   ```

3. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

   For local development and QA tooling:

   ```bash
   pip install -r requirements-dev.txt
   ```

4. **Configure environment**

   Copy `.env.example` to `.env`, then fill in your values:

   ```bash
   cp .env.example .env
   ```

   (On Windows PowerShell: `Copy-Item .env.example .env`)

   Required variables:

   | Variable | Description |
   |----------|-------------|
   | `SECRET_KEY` | Django secret key (sessions, CSRF). **Mandatory in production** – app will not start without it when `ENVIRONMENT=prod`. |
   | `DB_NAME` | PostgreSQL database name |
   | `DB_USER` | PostgreSQL user |
   | `DB_PASSWORD` | PostgreSQL password |
   | `DB_HOST` | Database host (e.g. `localhost`) |
   | `DB_PORT` | Database port (e.g. `5432`) |
   | `ALLOWED_HOSTS` | Comma-separated list of allowed `Host` header values. **Mandatory in production** – if empty, Django rejects all requests. In dev, set e.g. `localhost,127.0.0.1`. |
   | `SENTRY_DSN` | (Optional) Sentry DSN for error tracking |
| `HIDRIVE_USE_MOCK` | HiDrive switch (`0` = real API, `1` = mock/no HTTP). |
| `HIDRIVE_CLIENT_ID` | HiDrive OAuth client id (required in production when `HIDRIVE_USE_MOCK=0`). |
| `HIDRIVE_CLIENT_SECRET` | HiDrive OAuth client secret (required in production when `HIDRIVE_USE_MOCK=0`). |
| `HIDRIVE_REFRESH_TOKEN` | HiDrive refresh token obtained via OAuth code flow (required in production when `HIDRIVE_USE_MOCK=0`). |
| `HIDRIVE_INCOMING_PATH` | (Optional) Logical path to the lab PDF inbox; default `/incoming`. Under HiDrive *Common*, often e.g. `/public/incoming`. |
| `HIDRIVE_PROCESSED_PATH` | (Optional) Logical path for archived lab PDFs after publish; default `/processed`. |
| `HIDRIVE_PATIENTS_DIR_PREFIX` | (Optional) Logical directory root for Befund/intake PDFs; default `/patients` (files under `…/{patient_uuid}/`). |
| `HIDRIVE_USERS_ROOT_PREFIX` | (Optional) Absolute HiDrive path beginning with `/users/…` (no trailing slash). When set, logical `HIDRIVE_*` paths are appended here instead of `/users/<OAuth user/me alias>/` — for team/Common API roots. |

   Example (replace with your values):

   ```env
   SECRET_KEY=your-secret-key
   DB_NAME=cogitomedica
   DB_USER=postgres
   DB_PASSWORD=your-password
   DB_HOST=localhost
   DB_PORT=5432
   ALLOWED_HOSTS=localhost,127.0.0.1
   ```

   For local development you may set `DEBUG=1` and `ALLOWED_HOSTS=localhost,127.0.0.1`. Do not use `DEBUG=1` in production.

5. **Create the database and run migrations**

   ```bash
   python manage.py migrate
   ```

6. **Create a superuser (optional)**

   ```bash
   python manage.py createsuperuser
   ```

7. **Run the development server**

   ```bash
   python manage.py runserver
   ```

   The app will be available at `http://127.0.0.1:8000/`. Log in via `/accounts/login/`; admin at `/admin/`.

8. **Tablet (waiting room):** To show queues on a tablet, assign the device to a clinic site: in Django Admin go to **Reception → Tablet devices**, edit the device and set **Clinic site**; or use the API (PATCH `/api/v1/tablet-devices/{id}` with `clinic_site_id`). Without assignment, the tablet displays an empty queue list and a message to contact the administrator.

### Static and media (production-like)

- Collect static files: `python manage.py collectstatic`
- PDFs are stored under `MEDIA_ROOT` (`pdf_files/` by default); ensure the app has write access.

---

## Docker Quick Start

Minimal Docker setup is available via `Dockerfile` and `docker-compose.yml`:

- `web` service: Django app (`runserver` on port `8000`)
- `db` service: PostgreSQL 16 (persistent volume `postgres_data`)

### 1) Start stack

PowerShell / CMD:

```bash
docker compose up --build
```

If `.env` does not exist yet, create it from the template first:

```bash
cp .env.example .env
```

(On Windows PowerShell: `Copy-Item .env.example .env`)

App URL: `http://127.0.0.1:8000`

### 2) Usługi monitorowania (adresy)

Po uruchomieniu `docker compose up` dostępne są następujące usługi (na `localhost`; w innym środowisku zamień host):

| Usługa | Adres | Opis |
|--------|--------|------|
| **Health (aplikacja)** | http://localhost:8000/api/v1/observability/health | Health check (GET, bez auth). Odpowiedź: status DB itd. |
| **Metryki Prometheus (aplikacja)** | http://localhost:8000/api/v1/observability/metrics | Eksport metryk w formacie Prometheus. Wymaga nagłówka `Authorization: Bearer <PROMETHEUS_METRICS_TOKEN>` lub sesji ADMIN. |
| **Grafana** | http://localhost:3000 | Dashboardy (metryki, trace’y). Logowanie: `admin` / `admin`. |
| **Prometheus** | http://localhost:9090 | UI zapytań PromQL, lista targetów: http://localhost:9090/targets |
| **Alertmanager** | http://localhost:9093 | Zarządzanie alertami i powiadomieniami |
| **Grafana Tempo** | http://localhost:3200 | Backend trace’ów (OpenTelemetry); dostęp głównie z poziomu Grafany (Explore → Tempo) |
| **OpenTelemetry Collector** | localhost:4317 (gRPC), localhost:4318 (HTTP) | Odbiera trace’y z aplikacji; nie ma interfejsu web – używany wewnętrznie przez `web` i `scheduler` |

Szczegóły konfiguracji, dashboard-as-code i rozwiązywanie problemów: [docs/observability-setup.md](docs/observability-setup.md).

### 3) Aplikacja i dokumentacja API (Swagger)

| Adres | Opis |
|--------|------|
| http://localhost:8000 | Aplikacja (logowanie: `/accounts/login/`, panel admin: `/admin/`) |
| http://localhost:8000/api/docs/swagger/ | **Swagger UI** – interaktywna dokumentacja OpenAPI |
| http://localhost:8000/api/docs/redoc/ | **ReDoc** – dokumentacja API (czytelny układ) |
| http://localhost:8000/api/schema/ | Schemat OpenAPI (JSON/YAML) |

W środowisku innym niż Docker zamień `localhost:8000` na adres serwera deweloperskiego (np. `http://127.0.0.1:8000`).

### 4) Common commands

PowerShell / CMD:

```bash
docker compose down
docker compose logs -f web
docker compose run --rm web python manage.py migrate
docker compose run --rm web python manage.py createsuperuser
```

If you use `make` (e.g. Git Bash / WSL), shortcuts are available:

```bash
make up
make down
make logs
make migrate
make superuser
```

### 5) Notes

- Keep secrets in `.env` (do not commit real credentials).
- In Docker, `DB_HOST` is overridden to `db` automatically by `docker-compose.yml`.
- For production: set `ENVIRONMENT=prod`, and **must** set `SECRET_KEY` and `ALLOWED_HOSTS` (app will not start in prod without `SECRET_KEY`). Docker prod: [docker-compose.prod.yml](docker-compose.prod.yml) (Gunicorn + Nginx + scheduler; observability opcjonalnie `--profile observability`) — sekcja poniżej.
- Login is rate-limited (5 POSTs per IP per minute); 429 is returned when exceeded. For multi-worker production, configure a shared cache (e.g. Redis) in `CACHES` so the limit applies across processes.
- For a clean database state:

  ```bash
  docker compose down -v
  docker compose up --build
  ```

### 6) Produkcja na VPS (`docker-compose.prod.yml`)

**Domyślny** stack: **db** (Postgres 16, **bez** publikacji 5432 na host), **web** ([Dockerfile.prod](Dockerfile.prod) instaluje [requirements.txt](requirements.txt), Gunicorn `--workers 1`), **scheduler** (`run_periodic_tasks` co 300 s, `--skip-import`), **nginx** (reverse proxy, `/static/` i `/media/` z wolumenów) — tylko port **80** na hoście. Kod w obrazie (brak `.:/app`). Obrazy: **`cogitomedica-web:prod`** / **`cogitomedica-scheduler:prod`** (dev: `:dev` w [docker-compose.yml](docker-compose.yml)).

**Observability** (Prometheus, postgres_exporter, Alertmanager, Tempo, OTel Collector, Grafana — jak w dev, [docs/observability-setup.md](docs/observability-setup.md)): profil Compose `observability`. Porty **3000, 9090, 9093, 3200, 4317–4318, 8889** na hoście są domyślnie związane z **`127.0.0.1`** (brak nasłuchu na publicznym IP — dostęp z zewnątrz przez SSH tunnel, np. `ssh -L 3000:127.0.0.1:3000 user@vps`). Świadome wystawienie na LAN/Internet: **`OBSERVABILITY_BIND_ADDR=0.0.0.0`** w `.env` + firewall. Ustaw **`PROMETHEUS_METRICS_TOKEN`** i **`web` w `ALLOWED_HOSTS`** (scraping), **`GF_SECURITY_ADMIN_PASSWORD`** dla Grafany oraz **`OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318/v1/traces`**, jeśli chcesz trace’y do Tempo.

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml --profile observability up -d --build
```

Domyślnie HTTP na porcie **80** (Nginx). Przy `ENVIRONMENT=prod` i TLS na Nginx ustaw m.in. `USE_TRUSTED_REVERSE_PROXY=1` oraz `CSRF_TRUSTED_ORIGINS`; przy pierwszym teście wyłącznie po HTTP możesz tymczasowo ustawić `SECURE_SSL_REDIRECT=0` (komentarze w [.env.example](.env.example)). Healthcheck kontenera `web` uruchamia [scripts/docker-healthcheck-web.sh](scripts/docker-healthcheck-web.sh) (połączenie z bazą przez `django.setup()` — bez HTTP, żeby uniknąć przekierowania HTTPS przy `SECURE_SSL_REDIRECT`). Przy dalszym `unhealthy` zobacz `docker compose -f docker-compose.prod.yml logs web` (np. `ImproperlyConfigured` z `.env` prod). Jeśli w logu jest **`exec /docker-entrypoint-prod.sh: no such file or directory`**, to zwykle **CRLF w `scripts/*.sh`** z Windows — w [Dockerfile.prod](Dockerfile.prod) jest `sed` usuwający `\r`; zrób `docker compose -f docker-compose.prod.yml build --no-cache web`.

Jednorazowe `manage.py` bez pełnego entrypointa `web` (migracje uruchamiają się przy starcie kontenera `web`):

```bash
docker compose -f docker-compose.prod.yml run --rm --entrypoint python web manage.py createsuperuser
```

TLS: dopisz `listen 443 ssl` i zamontuj certyfikaty w [deploy/nginx/nginx.prod.conf](deploy/nginx/nginx.prod.conf), potem odkomentuj mapowanie `443:443` w compose. Operacyjnie: [.cursor/plans/produkcja_vps_cogitomedica.plan.md](.cursor/plans/produkcja_vps_cogitomedica.plan.md).

---

## Available Scripts

All commands are run from the project root with the virtual environment activated.

| Command | Description |
|---------|-------------|
| `python manage.py runserver` | Start the Django development server |
| `python manage.py migrate` | Apply database migrations |
| `python manage.py makemigrations [app]` | Create migrations for model changes |
| `make pytest` | **Canonical test suite:** Docker `web` + `requirements-dev` + full `pytest` (same as CI gate after migrations/translations) |
| `make test-ci` | Migrations, translation seed + completeness check, then same `pytest` as `make pytest` |
| `python manage.py test` | Legacy Django runner (subset only; prefer `make pytest`) |
| `python manage.py collectstatic` | Gather static files for deployment |
| `python manage.py createsuperuser` | Create an admin/superuser account |
| `python manage.py load_default_translations` | Idempotent seed from all `apps/core/translation_data/*.json` (baseline in migration `0024`; model field labels + login strings in `administration_fields.json`, applied in `0025`) |
| `python manage.py check_translations_completeness` | Validate active translations completeness for `de/en/pl` |
| `python manage.py enqueue_tasks` | Enqueue background tasks once (outbox, retention, import) |
| `python manage.py run_periodic_tasks --interval-seconds 300` | Run periodic enqueue loop (every 5 minutes) |

Scheduled work is defined with Django 6 `@task` (`django.tasks`) and enqueued via `python manage.py enqueue_tasks` (one-shot) or `python manage.py run_periodic_tasks` (loop). In this project we use one background-work contract: **Django Tasks + Transactional Outbox**. The default backend in this repository is `ImmediateBackend` for deterministic local development.

Publishing is designed to be idempotent: repeated "publish/send" actions for the same document do not create duplicate asynchronous chains.
Publishing also persists immutable `publish_locale` per version, so generated PDF language is auditable and stable for that publication.

---

## Project Scope

### In scope

- Reception module: daily list (CRUD + daily file import), read-only intake PDF viewer (list/detail/preview) for RECEPTION/ADMIN at `/admin/intake-documents/`
- Patient web app (RWD/tablet) for consent signing, body map, and e-signature
- Doctor module: medical section, draft/publish, edit and resend
- PDF generation (consents, body map, signature)
- HiDrive mock (Phases 1–2) and HiDrive API integration (Phase 3)
- Daily patient/visit list import from **XLSX** (admin upload + background batch via Django Tasks); optional `doctolib_patient_id` field when present in data (no external queue-system API)
- SMS notifications (logistic text only; patient retrieves PDF via the results portal, not via SMS link)
- Audit trail (operations): event log with immutable entity refs in `metadata._ref` for compliance after anonymization; filters by patient, document, clinic site, actor, outbox event, and time range
- Logging (e.g. OpenTelemetry as per PRD)
- Operational dashboards: simplified reception/doctor view in Django + advanced maintenance view in Grafana OSS
- UI languages: German, English, Polish

### Out of scope

- Patients filling the full medical questionnaire
- Complex business reporting (BI)
- Direct API integration with external queueing/EMR systems (import uses **XLSX**, not vendor PDF exports)
- Integrations other than HiDrive and SMSApi

---

## Project Status

The product is developed in **three phases**:

| Phase | Focus |
|-------|--------|
| **1** | Tablets, digital consents, body schema, patient e-signature; waiting room managed manually or via daily file import |
| **2** | Doctor panel for medical data and document approval; automated archive upload and SMS |
| **3** | Scheduled daily import (when implemented) + **XLSX** import path + HiDrive API (archiving) |

Current implementation includes Django backend, PostgreSQL, PDF generation, HiDrive API integration (with optional mock mode), SMS (SMSApi), **XLSX import** (`run_patient_xlsx_import`), patient results portal, observability stack (Prometheus/Grafana/Alertmanager/Tempo) documented in `docs/observability-setup.md`, Sentry, and Django 6 Tasks as the single background-processing solution. **Not yet implemented:** automatic daily scheduler hook (`run_daily_import` is still a placeholder in `apps/reception/tasks.py`).

---

## License

License terms are not specified in this repository. For usage and redistribution rights, please contact the project maintainers or refer to the repository owner.

---

For detailed requirements and user stories, see the product documentation (e.g. `.ai/prd.md` and related planning documents in the repository).
