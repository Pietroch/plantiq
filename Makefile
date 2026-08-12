# Makefile

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

run:	## Run the scheduler manually
	docker compose run --rm web python -m plantiq.run

schema:	## Apply db/schema.sql (drops and rebuilds the public schema)
	docker compose run --rm web python -m plantiq.schema

test:	## Run tests
	docker compose run --rm web pytest

lint:	## Lint code
	docker compose run --rm web ruff check .


