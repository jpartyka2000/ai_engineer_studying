#!/usr/bin/env bash
#
# Executable mirror of .github/workflows/ci.yml.
#
# There is no GitHub runner available locally, so the workflow is the artifact you read
# and edit while this script is what actually runs -- by `make ci`, and by the grading
# harness. Change one and you must change the other; a fix applied to only one of them
# is an incomplete fix.
set -euo pipefail

export TZ=UTC
export PYTHONHASHSEED=random
export CI=true
export RAGQA_ROOT=${RAGQA_ROOT:-/app}

step() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }

step "Python version"
python --version

step "Installing the package"
pip install --quiet --no-deps --force-reinstall .

step "Import smoke test"
python -c "import ragqa; print('ragqa', ragqa.__version__)"

step "Retrieval, generation and scoring run with no database and no network"
# Both pointed at dead ports on purpose. If anything in the RAG or eval path has quietly
# acquired a connection or an HTTP call, it surfaces here rather than in production as a
# timeout nobody can explain.
DATABASE_URL=postgresql://nobody@127.0.0.1:1/nothing \
HTTP_PROXY=http://127.0.0.1:1 HTTPS_PROXY=http://127.0.0.1:1 \
    python -m pytest -p no:cacheprovider -q -m "not db"

step "Waiting for PostgreSQL"
python - <<'PY'
import sys, time
import psycopg
from ragqa.config import SETTINGS

for attempt in range(30):
    try:
        with psycopg.connect(SETTINGS.database_url, connect_timeout=2):
            print(f"  postgres answered on attempt {attempt + 1}")
            sys.exit(0)
    except psycopg.OperationalError:
        time.sleep(1)
print("  postgres never answered", file=sys.stderr)
sys.exit(1)
PY

step "Applying migrations"
ragqa migrate

step "Running the full test suite"
python -m pytest -p no:cacheprovider -q

step "Index shape"
ragqa index

step "Scoring the labelled evaluation set"
# The gate. Every metric is 1.0 on a healthy build, so anything less is a regression
# rather than a judgement call about what is good enough.
ragqa --json eval > /tmp/ragqa-eval.json
python - <<'PY'
import json, sys

report = json.load(open("/tmp/ragqa-eval.json"))
print(json.dumps(report, indent=2, sort_keys=True))
required = (
    "exact_match",
    "token_f1",
    "citation_precision",
    "citation_recall",
    "refusal_balanced_accuracy",
)
below = {name: report[name] for name in required if report[name] < 1.0}
if below:
    print(f"\nFAIL: metrics below their baseline: {below}", file=sys.stderr)
    sys.exit(1)
print("\n  all five metrics at baseline")
PY

step "Answering one question end to end"
ragqa ask "How long is probation?"

echo
echo "CI passed."
