#!/usr/bin/env bash
#
# Executable mirror of .github/workflows/ci.yml.
#
# There is no GitHub runner available locally, so the workflow is the artifact you
# read and edit while this script is what actually runs -- by `make ci`, and by the
# grading harness. Change one and you must change the other.
set -euo pipefail

export TZ=UTC
export PYTHONHASHSEED=random
export CI=true

step() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }

step "Python version"
python --version

step "Installing the package"
pip install --quiet --no-deps --force-reinstall .

step "Import smoke test"
python -c "import edakit; print('edakit', edakit.__version__)"

step "Running the test suite"
python -m pytest -p no:cacheprovider -q

step "Running the docstring examples"
python -m pytest -p no:cacheprovider -q --doctest-modules src/edakit

step "CLI smoke test"
edakit profile datasets/tiny.csv > /dev/null
edakit missing datasets/customers.csv --threshold 0.2 > /dev/null

step "Profiling benchmark"
python bench/bench_profile.py --json > /dev/null

echo
echo "CI passed."
