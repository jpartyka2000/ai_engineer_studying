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
export AGENTDESK_ROOT=${AGENTDESK_ROOT:-/app}
# Pinned, and load-bearing: tool output carries SLA state, SLA state reaches the cassette
# key. An unpinned clock would expire every recording overnight.
export AGENTDESK_NOW=${AGENTDESK_NOW:-2025-06-18T09:00:00+00:00}

step() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }

step "Python version"
python --version

step "Installing the package"
pip install --quiet --no-deps --force-reinstall .

step "Import smoke test"
python -c "import agentdesk; print('agentdesk', agentdesk.__version__)"

step "The assistant, the prompt layer and the serving planner run with no database and no network"
# Both pointed at dead ports on purpose. If anything outside agentdesk.db has quietly
# acquired a connection, or anything at all has acquired an HTTP call, it surfaces here
# rather than in production as a timeout nobody can explain.
DATABASE_URL=postgresql://nobody@127.0.0.1:1/nothing \
HTTP_PROXY=http://127.0.0.1:1 HTTPS_PROXY=http://127.0.0.1:1 \
    python -m pytest -p no:cacheprovider -q -m "not db"

step "Waiting for PostgreSQL"
python - <<'PY'
import sys, time
import psycopg
from agentdesk.config import SETTINGS

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
agentdesk migrate

step "Seeding tickets"
agentdesk seed

step "Running the full test suite"
python -m pytest -p no:cacheprovider -q

step "Serving plan"
agentdesk plan

step "The dashboard renders without calling a model"
# The gate for the N+1 class of regression, stated as a count rather than a duration.
agentdesk --json dashboard > /tmp/agentdesk-dashboard.json
python - <<'PY'
import json, sys

from agentdesk.assistant import digest
from agentdesk.clock import now
from agentdesk.obs import MODEL_START, tracing

with tracing() as trace:
    payload = digest.queue_digest(now=now())

calls = trace.count(MODEL_START)
print(f"  rows: {len(payload['rows'])}  model calls: {calls}")
if calls:
    print(f"\nFAIL: the dashboard made {calls} model call(s); it must make none", file=sys.stderr)
    sys.exit(1)
PY

step "One draft, end to end"
agentdesk ask 2 "What should I tell them about the VPN?"

echo
echo "CI passed."
