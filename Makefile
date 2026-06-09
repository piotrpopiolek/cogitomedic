.PHONY: up down logs ps build rebuild migrate superuser shell check-translations test-ci pytest mutmut-smoke mutmut-name-normalize mutmut-name-normalize-results

# Pełna weryfikacja testów (pytest w Dockerze) z coverage gate z pyproject.toml.
DOCKER_PYTEST = pip install --no-cache-dir -q -r requirements-dev.txt && python -m pytest -q --tb=short --cov --cov-report=xml --cov-report=term-missing

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

# Mutation testing pilot: pure logic module, SimpleTestCase (no DB). Linux/Docker only (fork).
mutmut-smoke:
	docker compose run --rm web sh -c "pip install --no-cache-dir -q -r requirements-dev.txt && sh scripts/mutmut_smoke.sh"

mutmut-name-normalize:
	docker compose run --rm web sh -c "pip install --no-cache-dir -q -r requirements-dev.txt && rm -rf mutants && mutmut run 'apps.medical.name_normalize*'"

mutmut-name-normalize-results:
	docker compose run --rm web sh -c "pip install --no-cache-dir -q -r requirements-dev.txt && mutmut results"
