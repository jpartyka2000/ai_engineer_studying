#!/usr/bin/env bash
#
# Runs the whole pipeline over a copy of the committed landing zone, twice, and asserts the
# second run changes nothing.
#
# Extracted into its own file so `ci/run_ci.sh` and `.github/workflows/ci.yml` can both call
# it rather than each carrying their own copy of the same Python. Two inline copies of a
# check are two things to keep in step, and the one that drifts is always the one nobody
# runs locally.
set -euo pipefail

python - <<'PY'
import shutil
import tempfile
from pathlib import Path

from etlduck import connect, run_pipeline

scratch = Path(tempfile.mkdtemp(prefix="etlduck-ci-"))
try:
    (scratch / "raw").mkdir()
    (scratch / "warehouse").mkdir()
    for path in sorted(Path("raw").glob("*")):
        shutil.copy2(path, scratch / "raw" / path.name)

    connection = connect(scratch)
    try:
        first = run_pipeline(connection, scratch)
        second = run_pipeline(connection, scratch)
    finally:
        connection.close()

    assert first.ok, "quality gates failed on the committed data"
    assert second.files_loaded == 0, "a second run reloaded files; ingest is not idempotent"
    assert (
        first.gold.total_amount_cents == second.gold.total_amount_cents
    ), "two runs over the same input disagreed"
    print(
        f"  {first.silver.rows_written} silver rows, {first.gold.rows_written} gold rows, "
        f"{first.gold.total_amount_cents} cents, idempotent on rerun"
    )
finally:
    shutil.rmtree(scratch, ignore_errors=True)
PY
