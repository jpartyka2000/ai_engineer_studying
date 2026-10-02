# Convenience targets for the eventstore exercise.
#
# `make test` is exactly what the grading harness runs.

.DEFAULT_GOAL := help
COMPOSE := docker compose

.PHONY: help up down shell logs test test-fast test-unit indexes load rollup backfill status report bench ci reset

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

up: ## Build and start MongoDB and the API
	$(COMPOSE) up -d --build --wait

down: ## Stop and remove the containers
	$(COMPOSE) down --remove-orphans

shell: ## Open a shell in the app container
	$(COMPOSE) exec app bash

logs: ## Tail the API logs
	$(COMPOSE) logs -f app

test: ## Run the full suite (this is what grading runs)
	$(COMPOSE) exec -T app python -m pytest -v

test-fast: ## Stop at the first failure
	$(COMPOSE) exec -T app python -m pytest -x -q

test-unit: ## Run only the tests that need no database
	$(COMPOSE) exec -T app python -m pytest -q -m "not mongo"

indexes: ## Create the Mongo indexes
	$(COMPOSE) exec -T app eventstore indexes

load: ## Load the committed event exports into Mongo
	$(COMPOSE) exec -T app sh -c 'eventstore load data/*.jsonl'

rollup: ## Advance the Mongo -> DuckDB rollup
	$(COMPOSE) exec -T app eventstore rollup

backfill: ## Rebuild the warehouse from scratch
	$(COMPOSE) exec -T app eventstore rollup --full

status: ## Show store counts and the rollup watermark
	$(COMPOSE) exec -T app eventstore status

report: ## Print a latency and error report for the checkout service
	$(COMPOSE) exec -T app eventstore report --service checkout --minutes 1440

seed: ## Regenerate the committed event exports
	$(COMPOSE) exec -T app python tools/gen_seed_data.py --out data

bench: ## Measure how much work the recent-window query does
	$(COMPOSE) exec -T app python bench/bench_query.py

ci: ## Run the same steps the CI pipeline runs
	$(COMPOSE) exec -T app bash ci/run_ci.sh

reset: down up ## Rebuild from scratch, discarding the Mongo volume
