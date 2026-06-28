# Makefile

.PHONY: up down build logs sh run test lint simulate log backup help

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

backup:   ## Export all DB tables to JSON (uses BACKUP_PATH from .env)
	$(eval DEST := $(or $(shell grep -E '^BACKUP_PATH=' .env 2>/dev/null | cut -d= -f2- | tr -d '\r'),$(CURDIR)))
	@mkdir -p "$(DEST)"
	docker compose run --rm -v "$(DEST):$(DEST)" -e BACKUP_PATH="$(DEST)" scheduler python -m plantiq.backup

help:     ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-10s %s\n", $$1, $$2}'
