# Convenience targets for the edakit exercise.
#
# `make test` is exactly what the grading harness runs.

.DEFAULT_GOAL := help
COMPOSE := docker compose

.PHONY: help up down shell test test-fast doctest install lint ci profile reset

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

up: ## Build and start the container
	$(COMPOSE) up -d --wait

down: ## Stop and remove the container
	$(COMPOSE) down --remove-orphans

shell: ## Open a shell in the container
	$(COMPOSE) exec app bash

test: ## Run the full suite (this is what grading runs)
	$(COMPOSE) exec -T app python -m pytest -v

test-fast: ## Stop at the first failure
	$(COMPOSE) exec -T app python -m pytest -x -q

doctest: ## Run only the docstring examples
	$(COMPOSE) exec -T app python -m pytest --doctest-modules src/edakit -q

install: ## Verify the package installs and imports cleanly
	$(COMPOSE) exec -T app pip install --no-deps --force-reinstall .
	$(COMPOSE) exec -T app python -c "import edakit; print(edakit.__version__)"

profile: ## Profile the sample dataset
	$(COMPOSE) exec -T app edakit profile datasets/customers.csv

ci: ## Run the same steps the CI pipeline runs
	bash ci/run_ci.sh

reset: down up ## Rebuild from scratch
