.PHONY: up down logs ps build rebuild migrate superuser shell check-translations test-ci pytest

# Pełna weryfikacja testów (pytest w Dockerze) — uznajemy za źródło prawdy w tym repo.
DOCKER_PYTEST = pip install --no-cache-dir -q -r requirements-dev.txt && python -m pytest -q --tb=short

up:
	docker compose up

down:
	docker compose down

logs:
	docker compose logs -f web

ps:
	docker compose ps

build:
	docker compose build web

rebuild:
	docker compose down
	docker compose build --no-cache web
	docker compose up

migrate:
	docker compose run --rm web python manage.py migrate

superuser:
	docker compose run --rm web python manage.py createsuperuser

shell:
	docker compose run --rm web python manage.py shell

check-translations:
	docker compose run --rm web sh -c "python manage.py migrate && python manage.py load_default_translations && python manage.py check_translations_completeness"

# CI / bramka: migracje + tłumaczenia + ten sam pytest co `make pytest` (cały zbiór z pytest.ini).
test-ci:
	docker compose run --rm web sh -c "python manage.py migrate && python manage.py load_default_translations && python manage.py check_translations_completeness && $(DOCKER_PYTEST)"

pytest:
	docker compose run --rm web sh -c "$(DOCKER_PYTEST)"
