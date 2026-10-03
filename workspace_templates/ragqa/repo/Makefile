# Convenience targets for the ragqa exercise.
#
# `make test` is exactly what the grading harness runs.

.DEFAULT_GOAL := help
COMPOSE := docker compose

.PHONY: help up down shell logs test test-fast test-unit eval evald ask index migrate cassettes ci reset

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

up: ## Build and start Postgres and the API
	$(COMPOSE) up -d --build --wait

down: ## Stop and remove the containers
	$(COMPOSE) down --remove-orphans

shell: ## Open a shell in the app container
	$(COMPOSE) exec app bash

logs: ## Tail the API logs
	$(COMPOSE) logs -f app

migrate: ## Apply pending SQL migrations
	$(COMPOSE) exec -T app ragqa migrate

test: ## Run the full suite (this is what grading runs)
	$(COMPOSE) exec -T app python -m pytest -v

test-fast: ## Stop at the first failure
	$(COMPOSE) exec -T app python -m pytest -x -q

test-unit: ## Run only the tests that need no database
	$(COMPOSE) exec -T app python -m pytest -q -m "not db"

eval: ## Score the system against the labelled evaluation set
	$(COMPOSE) exec -T app ragqa eval

evald: ## Score it, listing every question
	$(COMPOSE) exec -T app ragqa eval --detail

ask: ## Ask one question: make ask Q="how long is probation?"
	$(COMPOSE) exec -T app ragqa ask "$(Q)"

index: ## Report the index's shape
	$(COMPOSE) exec -T app ragqa index

cassettes: ## Regenerate cassettes from the recording transcript
	$(COMPOSE) exec -T app python tools/gen_cassettes.py

ci: ## Run the same steps the CI pipeline runs
	$(COMPOSE) exec -T app bash ci/run_ci.sh

reset: down up migrate ## Rebuild from scratch, discarding the database volume
