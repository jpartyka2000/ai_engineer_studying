# Convenience targets for the etlduck exercise.
#
# `make test` is exactly what the grading harness runs.

.DEFAULT_GOAL := help
COMPOSE := docker compose

.PHONY: help up down shell test test-fast run bronze silver gold check profile watermark seed bench ci reset

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

up: ## Build and start the container
	$(COMPOSE) up -d --build --wait

down: ## Stop and remove the container
	$(COMPOSE) down --remove-orphans

shell: ## Open a shell in the container
	$(COMPOSE) exec app bash

test: ## Run the full suite (this is what grading runs)
	$(COMPOSE) exec -T app python -m pytest -v

test-fast: ## Stop at the first failure
	$(COMPOSE) exec -T app python -m pytest -x -q

run: ## Run the whole pipeline over the landing zone
	$(COMPOSE) exec -T app etlduck run

bronze: ## Ingest the landing zone only
	$(COMPOSE) exec -T app etlduck bronze

silver: ## Rebuild silver from bronze
	$(COMPOSE) exec -T app etlduck silver

gold: ## Rebuild gold from silver
	$(COMPOSE) exec -T app etlduck gold

check: ## Run the data-quality gates
	$(COMPOSE) exec -T app etlduck check

profile: ## Describe the landing-zone files before ingesting them
	$(COMPOSE) exec -T app etlduck profile

watermark: ## Show the current watermark
	$(COMPOSE) exec -T app etlduck watermark

seed: ## Regenerate the committed landing-zone files
	$(COMPOSE) exec -T app python tools/gen_seed_data.py --out raw

bench: ## Measure how much work the pipeline does
	$(COMPOSE) exec -T app python bench/bench_pipeline.py

ci: ## Run the same steps the CI pipeline runs
	bash ci/run_ci.sh

reset: down up ## Rebuild from scratch
