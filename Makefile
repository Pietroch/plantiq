# Makefile

.PHONY: up down build logs sh run test lint simulate log deploy help

up:       ## Start the stack
	docker compose up -d

down:     ## Stop the stack
	docker compose down

build:    ## Rebuild image
	docker compose build

logs:     ## Tail logs
	docker compose logs -f

sh:       ## Shell into scheduler
	docker compose run --rm scheduler bash

run:      ## Run the scheduler manually
	docker compose run --rm scheduler python -m plantiq.run

test:     ## Run tests
	docker compose run --rm scheduler pytest

lint:     ## Lint code
	docker compose run --rm scheduler ruff check .

log:      ## Log une action ou snoozer une notification
	docker compose run --rm scheduler python -m plantiq.cli

simulate: ## Run notification engine simulation (no DB, no ntfy)
	docker compose run --rm scheduler python tests/test_simulation.py

deploy:   ## Deploy to Fly.io
	fly deploy

help:     ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-10s %s\n", $$1, $$2}'
