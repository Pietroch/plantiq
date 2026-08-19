# Makefile

# Read only this one line rather than including .env, whose values may contain #
BACKUP_PATH := $(shell grep -E '^BACKUP_PATH=' .env | cut -d= -f2-)

up:		## Start the stack
	docker compose up -d

down:	## Stop the stack
	docker compose down

build:	## Rebuild image
	docker compose build

logs:	## Tail logs
	docker compose logs -f

sh:		## Shell into web
	docker compose run --rm web bash

run:	## Run the daily batch: weather, reminders, notifications
	docker compose run --rm web python -m plantiq.run

preview: ## Show what the batch would send, without sending or writing
	docker compose run --rm web python -m plantiq.run --preview

schema:	## Apply db/schema.sql (drops and rebuilds the public schema)
	docker compose run --rm web python -m plantiq.schema

backup:	## Export every table to JSON in BACKUP_PATH
	@mkdir -p "$(BACKUP_PATH)"
	docker compose run --rm -v "$(BACKUP_PATH):/backups" web python -m plantiq.backup

restore: ## Reload the latest JSON backup from BACKUP_PATH
	docker compose run --rm -v "$(BACKUP_PATH):/backups" web python -m plantiq.restore

weather: ## Fetch and store today's weather for every open site
	docker compose run --rm web python -m plantiq.weather

weather-fields: ## List every field the OpenWeatherMap API returns
	docker compose run --rm web python -m plantiq.adapters.probe

test:	## Run tests
	docker compose run --rm web pytest

lint:	## Lint code
	docker compose run --rm web ruff check .


