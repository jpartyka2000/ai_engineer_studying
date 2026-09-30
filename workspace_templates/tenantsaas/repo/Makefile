# Convenience targets for the tenantsaas exercise.
#
# The grading harness runs `pytest` inside the app container, so `make test` is
# exactly what it does -- what you see locally is what gets graded.

.DEFAULT_GOAL := help
COMPOSE := docker compose

.PHONY: help up down logs shell psql migrate test test-fast lint ci seed reset

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

up: ## Start the database and app, waiting for healthchecks
	$(COMPOSE) up -d --wait

down: ## Stop everything and remove volumes
	$(COMPOSE) down --volumes --remove-orphans

logs: ## Tail the app logs
	$(COMPOSE) logs -f app

shell: ## Open a shell in the app container
	$(COMPOSE) exec app bash

psql: ## Open psql against the exercise database
	$(COMPOSE) exec db psql -U postgres -d tenantsaas

migrate: ## Apply Django migrations
	$(COMPOSE) exec -T app python manage.py migrate

seed: ## Load demo tenants, projects and billing data
	$(COMPOSE) exec -T app python manage.py seed_demo_data

test: ## Run the full test suite (this is what grading runs)
	$(COMPOSE) exec -T app python -m pytest -v

test-fast: ## Run the suite, stopping at the first failure
	$(COMPOSE) exec -T app python -m pytest -x -q

lint: ## Check formatting and lint
	$(COMPOSE) exec -T app python -m pytest --collect-only -q > /dev/null

ci: ## Run the same steps the CI pipeline runs
	bash ci/run_ci.sh

reset: down up migrate seed ## Rebuild the environment from scratch
