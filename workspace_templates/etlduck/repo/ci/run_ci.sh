#!/usr/bin/env bash
#
# Executable mirror of .github/workflows/ci.yml.
#
# There is no GitHub runner available locally, so the workflow is the artifact you read and
# edit while this script is what actually runs -- by `make ci`, and by the grading harness.
# Change one and you must change the other.
set -euo pipefail

export TZ=UTC
export PYTHONHASHSEED=random
export CI=true
export ETLDUCK_ROOT=${ETLDUCK_ROOT:-/app}

step() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }

step "Python version"
python --version

step "Installing the package"
pip install --quiet --no-deps --force-reinstall .

step "Import smoke test"
python -c "import etlduck; print('etlduck', etlduck.__version__)"

step "Running the test suite"
python -m pytest -p no:cacheprovider -q

step "Job definitions parse"
python -c "
import pathlib, yaml
for path in sorted(pathlib.Path('jobs').glob('*.yaml')):
    spec = yaml.safe_load(path.read_text())
    assert spec.get('name'), f'{path}: no name'
    assert spec.get('tasks'), f'{path}: no tasks'
    print(f'  {path.name}: {spec[\"name\"]} ({len(spec[\"tasks\"])} task(s))')
"

step "Cluster policy parses and pins UTC"
python -c "
import json, pathlib
policy = json.loads(pathlib.Path('dbx_conf/cluster_policy.json').read_text())
zone = policy['spark_conf.spark.sql.session.timeZone']
assert zone['type'] == 'fixed' and zone['value'] == 'UTC', zone
print('  session timeZone is fixed to UTC')
"

step "Notebooks are cell-delimited and importable as scripts"
python -c "
import ast, pathlib
for path in sorted(pathlib.Path('notebooks').glob('*.py')):
    text = path.read_text()
    assert text.startswith('# Databricks notebook source'), f'{path}: missing header'
    assert '# COMMAND ----------' in text, f'{path}: no cell delimiters'
    ast.parse(text)
    print(f'  {path.name}: {text.count(\"# COMMAND ----------\")} cells')
"

step "Pipeline runs end to end on the committed landing zone"
bash ci/pipeline_smoke.sh

step "Pipeline benchmark"
python bench/bench_pipeline.py --json > /dev/null

echo
echo "CI passed."
