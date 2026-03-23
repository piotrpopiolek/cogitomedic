.PHONY: up down logs ps build rebuild migrate superuser shell check-translations test-ci

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

test-ci:
	docker compose run --rm web sh -c "python manage.py migrate && python manage.py load_default_translations && python manage.py check_translations_completeness && python manage.py test apps.core.tests apps.integrations.hidrive.tests apps.medical.api_tests apps.outbox.tests apps.operations.api_tests apps.patient_results.tests apps.patient_results.api_tests"
