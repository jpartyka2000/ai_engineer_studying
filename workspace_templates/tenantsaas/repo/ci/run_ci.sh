#!/usr/bin/env bash
#
# Executable mirror of .github/workflows/ci.yml.
#
# Why both exist: there is no GitHub runner available locally, so the workflow file
# is the artifact you read and edit while this script is what actually gets run --
# by you via `make ci`, and by the grading harness. The two must stay in step; a fix
# applied to only one of them is an incomplete fix.
set -euo pipefail

# Match the CI environment, not your shell. PYTHONHASHSEED in particular makes
# ordering-dependent tests fail here the way they fail in CI.
export TZ=UTC
export PYTHONHASHSEED=random
export CI=true
export DJANGO_SETTINGS_MODULE=config.settings

step() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }

step "Python version"
python --version

step "Checking for missing migrations"
python manage.py makemigrations --check --dry-run

step "Applying migrations to a clean database"
python manage.py migrate --noinput

step "Running the test suite"
python -m pytest -p no:cacheprovider -q

step "Running the security suite"
python -m pytest -p no:cacheprovider -q -m security

step "Checking reporting does not regress into an N+1"
python -m pytest -p no:cacheprovider -q -m perf

echo
echo "CI passed."
