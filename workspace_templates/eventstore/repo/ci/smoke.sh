#!/usr/bin/env bash
#
# End-to-end smoke: the committed exports go in one end and a report comes out the other.
#
# Separate from the test suite on purpose. The suite tests units against fixtures it
# built itself; this drives the actual CLI against the actual MongoDB and the actual
# warehouse, which is the only thing that catches a wiring mistake -- a command that
# does not exist, an argument that was renamed, a config value the container does not
# have.
#
# Idempotent: it can be run twice in a row. The second load reports duplicates and
# inserts nothing, which is itself worth seeing go past in the output.
set -euo pipefail

step() { printf '\n\033[1m--> %s\033[0m\n' "$1"; }

step "Creating indexes"
eventstore indexes

step "Loading the committed exports"
eventstore load data/events_*.jsonl

step "Rolling up into the warehouse"
eventstore --json rollup

step "Store counts and watermark"
eventstore status

step "Reporting on the checkout service over the seeded window"
eventstore report \
    --service checkout \
    --start 2026-04-01T11:00:00Z \
    --end 2026-04-01T14:00:00Z

step "Re-loading the same exports must insert nothing"
duplicates=$(eventstore --json load data/events_*.jsonl | python -c 'import json,sys; print(json.load(sys.stdin)["duplicates"])')
inserted=$(eventstore --json load data/events_*.jsonl | python -c 'import json,sys; print(json.load(sys.stdin)["inserted"])')
echo "  second load: ${duplicates} duplicate(s), ${inserted} inserted"
if [ "${inserted}" != "0" ]; then
    echo "FAIL: re-loading the same exports inserted ${inserted} event(s); dedupe is broken" >&2
    exit 1
fi

echo
echo "Smoke passed."
