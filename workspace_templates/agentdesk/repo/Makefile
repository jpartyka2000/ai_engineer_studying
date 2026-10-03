# Convenience targets for the agentdesk exercise.
#
# `make test` is exactly what the grading harness runs.

.DEFAULT_GOAL := help
COMPOSE := docker compose

.PHONY: help up down shell logs test test-fast test-unit test-latency bench dashboard plan ask seed migrate cassettes ci reset

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

up: ## Build and start Postgres and the API
	$(COMPOSE) up -d --build --wait

down: ## Stop and remove the containers
	$(COMPOSE) down --remove-orphans

shell: ## Open a shell in the app container
	$(COMPOSE) exec app bash

logs: ## Tail the API logs
	$(COMPOSE) logs -f app

migrate: ## Apply pending SQL migrations
	$(COMPOSE) exec -T app agentdesk migrate

seed: ## Load the seeded tickets
	$(COMPOSE) exec -T app agentdesk seed

test: ## Run the full suite (this is what grading runs)
	$(COMPOSE) exec -T app python -m pytest -v

test-fast: ## Stop at the first failure
	$(COMPOSE) exec -T app python -m pytest -x -q

test-unit: ## Run only the tests that need no database
	$(COMPOSE) exec -T app python -m pytest -q -m "not db"

test-latency: ## Run only the tests that assert a latency mechanism
	$(COMPOSE) exec -T app python -m pytest -q -m latency

ask: ## Draft a reply: make ask ID=2 Q="what should I tell them?"
	$(COMPOSE) exec -T app agentdesk ask $(ID) "$(Q)"

dashboard: ## Print the queue digest and how many model calls it took
	$(COMPOSE) exec -T app agentdesk dashboard

plan: ## Print the serving plan for the configured card
	$(COMPOSE) exec -T app agentdesk plan

bench: ## Time the dashboard and one draft (reported, never asserted)
	$(COMPOSE) exec -T app agentdesk bench

cassettes: ## Regenerate cassettes from the recording transcript
	$(COMPOSE) exec -T app agentdesk cassettes

ci: ## Run the same steps the CI pipeline runs
	$(COMPOSE) exec -T app bash ci/run_ci.sh

reset: down up migrate seed ## Rebuild from scratch, discarding the database volume
