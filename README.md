# Cogitomedica Digital Consents

## Table of Contents

- [Project Description](#project-description)
- [API Documentation](#api-documentation)
- [Tech Stack](#tech-stack)
- [Getting Started Locally](#getting-started-locally)
- [Docker Quick Start](#docker-quick-start)
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

**Main capabilities:**

- **Reception:** Manage the daily patient list (waiting room), add patients manually or via daily file import, generate one-time links for tablet forms
- **Patient (tablet):** Touch-optimized form with read-only personal data, consent checkboxes, interactive body map, and electronic signature
- **Doctor/Staff:** View completed forms, fill medical section, save as draft or publish, edit published documents and resend
- **Backend:** Asynchronous pipeline (`GENERATE_PDF` -> `HIDRIVE_UPLOAD` -> `SMS_SEND`) processed through Django 6 Tasks (`django.tasks`) + Transactional Outbox, HiDrive (mock then API) archiving, SMS notifications via SMSApi, 30-day retention policy for local PDFs

The user interface is available in **English** and **German**.

---

## API Documentation

- **Interactive docs (OpenAPI/Swagger):** [http://127.0.0.1:8000/api/docs/swagger/](http://127.0.0.1:8000/api/docs/swagger/) (Swagger UI) and [http://127.0.0.1:8000/api/docs/redoc/](http://127.0.0.1:8000/api/docs/redoc/) (ReDoc). Schema: `/api/schema/`.
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
| **Monitoring** | Sentry |
| **Config** | python-dotenv |
| **Frontend** | Django templates, HTMX, Alpine.js, SignaturePad.js, Tailwind CSS (per implementation plan) |
| **Other** | Pillow, pycryptodome, requests |

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
   | `SECRET_KEY` | Django secret key |
   | `DB_NAME` | PostgreSQL database name |
   | `DB_USER` | PostgreSQL user |
   | `DB_PASSWORD` | PostgreSQL password |
   | `DB_HOST` | Database host (e.g. `localhost`) |
   | `DB_PORT` | Database port (e.g. `5432`) |
   | `SENTRY_DSN` | (Optional) Sentry DSN for error tracking |

   Example (replace with your values):

   ```env
   SECRET_KEY=your-secret-key
   DB_NAME=cogitomedica
   DB_USER=postgres
   DB_PASSWORD=your-password
   DB_HOST=localhost
   DB_PORT=5432
   ```

   For local development you may need to set `DEBUG=True` and adjust `ALLOWED_HOSTS` in `cogitomedica/settings.py` (do not use `DEBUG=True` in production).

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

### 2) Common commands

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

### 3) Notes

- Keep secrets in `.env` (do not commit real credentials).
- In Docker, `DB_HOST` is overridden to `db` automatically by `docker-compose.yml`.
- For a clean database state:

  ```bash
  docker compose down -v
  docker compose up --build
  ```

---

## Available Scripts

All commands are run from the project root with the virtual environment activated.

| Command | Description |
|---------|-------------|
| `python manage.py runserver` | Start the Django development server |
| `python manage.py migrate` | Apply database migrations |
| `python manage.py makemigrations [app]` | Create migrations for model changes |
| `python manage.py test` | Run the test suite (Django `TestCase`) |
| `python manage.py collectstatic` | Gather static files for deployment |
| `python manage.py createsuperuser` | Create an admin/superuser account |
| `python manage.py enqueue_tasks` | Enqueue background tasks (outbox, retention, import) |

Scheduled work is defined with Django 6 `@task` (`django.tasks`) and enqueued via `python manage.py enqueue_tasks`. In this project we use one background-work contract: **Django Tasks + Transactional Outbox**. The default backend in this repository is `ImmediateBackend` for deterministic local development.

Publishing is designed to be idempotent: repeated "publish/send" actions for the same document do not create duplicate asynchronous chains.

---

## Project Scope

### In scope

- Reception module: daily list (CRUD + daily file import)
- Patient web app (RWD/tablet) for consent signing, body map, and e-signature
- Doctor module: medical section, draft/publish, edit and resend
- PDF generation (consents, body map, signature)
- HiDrive mock (Phases 1–2) and HiDrive API integration (Phase 3)
- Daily import of patient/visit lists from files exported from Doctolib (no direct Doctolib API integration)
- SMS notifications (link to download document)
- Logging (e.g. OpenTelemetry as per PRD)
- Operational dashboards: simplified reception/doctor view + advanced admin/maintenance view
- UI languages: English and German

### Out of scope

- Advanced consent content versioning in an admin UI (changes require dev/config)
- Patients filling the full medical questionnaire
- Complex business reporting (BI)
- Direct API integration with Doctolib
- Integrations other than HiDrive and SMSApi

---

## Project Status

The product is developed in **three phases**:

| Phase | Focus |
|-------|--------|
| **1** | Tablets, digital consents, body schema, patient e-signature; waiting room managed manually or via daily file import |
| **2** | Doctor panel for medical data and document approval; automated archive upload and SMS |
| **3** | Improved daily import process for files exported from Doctolib + HiDrive API (archiving) |

Current implementation includes Django backend, PostgreSQL, PDF generation, SMS (SMSApi), Sentry, and Django 6 Tasks as the single background-processing solution. Further features (e.g. daily file import from Doctolib exports, HiDrive API, full tablet UI) are defined in the product and implementation plans.

---

## License

License terms are not specified in this repository. For usage and redistribution rights, please contact the project maintainers or refer to the repository owner.

---

For detailed requirements and user stories, see the product documentation (e.g. `.ai/prd.md` and related planning documents in the repository).
