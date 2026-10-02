#!/usr/bin/env bash
#
# Executable mirror of .github/workflows/ci.yml.
#
# There is no GitHub runner available locally, so the workflow is the artifact you read
# and edit while this script is what actually runs -- by `make ci`, and by the grading
# harness. Change one and you must change the other; a fix applied to only one of them
# is an incomplete fix.
set -euo pipefail

# Match the CI environment, not your shell. PYTHONHASHSEED in particular makes
# ordering-dependent tests fail here the way they fail in CI.
export TZ=UTC
export PYTHONHASHSEED=random
export CI=true
export EVENTSTORE_ROOT=${EVENTSTORE_ROOT:-/app}
export MONGO_URL=${MONGO_URL:-mongodb://db:27017}

step() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }

step "Python version"
python --version

step "Installing the package"
pip install --quiet --no-deps --force-reinstall .

step "Import smoke test"
python -c "import eventstore; print('eventstore', eventstore.__version__)"

step "Waiting for MongoDB"
python - <<'PY'
import sys, time
from pymongo.errors import PyMongoError
from eventstore.config import Settings
from eventstore import mongo

client = mongo.get_client(Settings())
for attempt in range(30):
    try:
        client.admin.command("ping")
        print(f"  mongo answered on attempt {attempt + 1}")
        sys.exit(0)
    except PyMongoError:
        time.sleep(1)
print("  mongo never answered", file=sys.stderr)
sys.exit(1)
PY

step "Running the test suite"
python -m pytest -p no:cacheprovider -q

step "The statistics run without any database at all"
# perfmodel must not have acquired a dependency on storage. If this starts failing, a
# pure function has reached for a connection and is no longer reviewable on its own.
MONGO_URL=mongodb://127.0.0.1:1 python -m pytest -p no:cacheprovider -q -m "not mongo" \
    tests/test_percentiles.py tests/test_apdex.py tests/test_intervals.py \
    tests/test_nonparametric.py tests/test_changepoint.py tests/test_baseline.py

step "Index declarations agree with the seed script"
python - <<'PY'
import pathlib
from eventstore import mongo

script = pathlib.Path("seed/001_indexes.js").read_text()
for spec in mongo.INDEX_SPECS:
    assert f'name: "{spec["name"]}"' in script, f'{spec["name"]} missing from seed/001_indexes.js'
    print(f'  {spec["name"]}: {spec["why"]}')
PY

step "Pipeline runs end to end on the committed exports"
bash ci/smoke.sh

step "Recent-window query stays index-served"
python bench/bench_query.py --events 5000 --json > /dev/null

step "Incremental rollup stays incremental"
python bench/bench_rollup.py --batches 10 --json > /dev/null

echo
echo "CI passed."
