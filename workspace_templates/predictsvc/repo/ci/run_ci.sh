#!/usr/bin/env bash
#
# Executable mirror of .github/workflows/ci.yml.
#
# There is no GitHub runner available locally, so the workflow is the artifact you read
# and edit while this script is what actually runs -- by `make ci`, and by the grading
# harness. Change one and you must change the other.
set -euo pipefail

export TZ=UTC
export PYTHONHASHSEED=random
export CI=true
export PYTHONPATH=/app
export ARTIFACT_DIR=${ARTIFACT_DIR:-artifacts}

step() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }

step "Python version"
python --version

step "Artifact compatibility"
python -c "from svc.model.registry import get_loaded_model; m = get_loaded_model(); print(m.identifier, 'spec', m.spec.version)"

step "Running the test suite"
python -m pytest -p no:cacheprovider -q

step "Running the API contract suite"
python -m pytest -p no:cacheprovider -q -m contract

step "Evaluating the model against the held-out set"
python eval/run_eval.py --assert-f1 0.80

step "Scoring benchmark"
python bench/bench_predict.py --json > /dev/null

echo
echo "CI passed."
