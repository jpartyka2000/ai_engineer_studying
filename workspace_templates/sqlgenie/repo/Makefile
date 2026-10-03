# Convenience targets for the sqlgenie exercise.
#
# `make test` is exactly what the grading harness runs.

.DEFAULT_GOAL := help
COMPOSE := docker compose

.PHONY: help up down shell logs test test-fast test-unit security migrate seed ask replay cassettes psql bench ci reset

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

up: ## Build and start PostgreSQL and the API
	$(COMPOSE) up -d --build --wait

down: ## Stop and remove the containers
	$(COMPOSE) down --remove-orphans

shell: ## Open a shell in the app container
	$(COMPOSE) exec app bash

logs: ## Tail the API logs
	$(COMPOSE) logs -f app

migrate: ## Apply pending SQL migrations
	$(COMPOSE) exec -T app sqlgenie migrate

seed: ## Load the two-tenant development data
	$(COMPOSE) exec -T app sqlgenie seed

test: ## Run the full suite (this is what grading runs)
	$(COMPOSE) exec -T app python -m pytest -v

test-fast: ## Stop at the first failure
	$(COMPOSE) exec -T app python -m pytest -x -q

test-unit: ## Run only the tests that need no database
	$(COMPOSE) exec -T app python -m pytest -q -m "not db"

security: ## Run only the cross-tenant suite
	$(COMPOSE) exec -T app python -m pytest -q -m security

ask: ## Ask a question as acme: make ask Q="how many orders did we take last month?"
	$(COMPOSE) exec -T app sqlgenie ask --tenant acme "$(Q)"

replay: ## Run the adversarial corpus through the policy
	$(COMPOSE) exec -T app sqlgenie replay

cassettes: ## Regenerate the cassette set from the recording transcript
	$(COMPOSE) exec -T app python tools/gen_cassettes.py

psql: ## Open psql as the owner role
	$(COMPOSE) exec db psql -U postgres -d sqlgenie

bench: ## Measure how much work answering a question costs
	$(COMPOSE) exec -T app python bench/bench_ask.py

ci: ## Run the same steps the CI pipeline runs
	$(COMPOSE) exec -T app bash ci/run_ci.sh

reset: down up migrate seed ## Rebuild from scratch, discarding the database volume
