.PHONY: up down logs ps build rebuild migrate superuser shell

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
