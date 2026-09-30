# Convenience targets for the predictsvc exercise.
#
# `make test` is exactly what the grading harness runs.

.DEFAULT_GOAL := help
COMPOSE := docker compose

.PHONY: help up down logs shell test test-fast eval bench serve ci reset

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-11s\033[0m %s\n", $$1, $$2}'

up: ## Start the service and wait for readiness
	$(COMPOSE) up -d --wait

down: ## Stop and remove the service
	$(COMPOSE) down --remove-orphans

logs: ## Tail the service logs
	$(COMPOSE) logs -f app

shell: ## Open a shell in the container
	$(COMPOSE) exec app bash

test: ## Run the full suite (this is what grading runs)
	$(COMPOSE) exec -T app python -m pytest -v

test-fast: ## Stop at the first failure
	$(COMPOSE) exec -T app python -m pytest -x -q

eval: ## Evaluate the model against the held-out set
	$(COMPOSE) exec -T app python eval/run_eval.py

bench: ## Measure scoring throughput
	$(COMPOSE) exec -T app python bench/bench_predict.py

serve: ## Show the URL the API is published on
	@echo "http://localhost:$${WS_APP_PORT:-55810}/docs"

ci: ## Run the same steps the CI pipeline runs
	bash ci/run_ci.sh

reset: down up ## Rebuild from scratch
