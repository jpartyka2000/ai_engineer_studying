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
export SQLGENIE_ROOT=${SQLGENIE_ROOT:-/app}

step() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }

step "Python version"
python --version

step "Installing the package"
pip install --quiet --no-deps --force-reinstall .

step "Import smoke test"
python -c "import sqlgenie; print('sqlgenie', sqlgenie.__version__)"

step "The rewriter runs with no database and no network"
# Pointed at a dead database and a dead proxy on purpose. If anything in the policy or
# cassette layer has quietly acquired a connection or an HTTP call, this is where it
# surfaces -- rather than in production, as a timeout nobody can explain.
DATABASE_URL=postgresql://nobody@127.0.0.1:1/nothing \
MIGRATION_DATABASE_URL=postgresql://nobody@127.0.0.1:1/nothing \
HTTP_PROXY=http://127.0.0.1:1 HTTPS_PROXY=http://127.0.0.1:1 \
    python -m pytest -p no:cacheprovider -q -m "not db"

step "Waiting for PostgreSQL"
python - <<'PY'
import sys, time
import psycopg
from sqlgenie.config import SETTINGS

for attempt in range(30):
    try:
        with psycopg.connect(SETTINGS.migration_url, connect_timeout=2):
            print(f"  postgres answered on attempt {attempt + 1}")
            sys.exit(0)
    except psycopg.OperationalError:
        time.sleep(1)
print("  postgres never answered", file=sys.stderr)
sys.exit(1)
PY

step "Applying migrations"
sqlgenie migrate

step "Seeding the two-tenant development data"
sqlgenie seed

step "Running the full test suite"
python -m pytest -p no:cacheprovider -q

step "Running the cross-tenant suite on its own"
# Run again in isolation so a failure here reads as "isolation broke" rather than as one
# red dot among two hundred. Cheap, and it is the result anybody looks at first.
python -m pytest -p no:cacheprovider -q -m security

step "Replaying the adversarial corpus through the policy"
sqlgenie --json replay

step "Every cassette is reachable and every question is recorded"
python -m pytest -p no:cacheprovider -q tests/test_cassettes.py

step "Answering a question end to end"
sqlgenie ask --tenant acme "How many orders are in each status?"

step "Query cost benchmark"
python bench/bench_ask.py --json > /dev/null

echo
echo "CI passed."
