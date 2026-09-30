# predictsvc

Churn-risk scoring over HTTP. **Serving only** — training happens elsewhere and lands
here as a JSON artifact.

## Getting started

```bash
docker compose up -d --wait   # or: make up
make test
make eval
```

The API is published on the host port in your `.env` (`WS_APP_PORT`); `make serve`
prints the URL. Interactive docs are at `/docs`.

## Common tasks

| Command | What it does |
|---|---|
| `make test` | Full suite. **This is what grading runs.** |
| `make eval` | Score the held-out set and report metrics |
| `make bench` | Measure scoring work per request |
| `make ci` | Run the CI pipeline locally (`ci/run_ci.sh`) |
| `make logs` | Tail the service logs |

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/healthz` | Liveness. Does not touch the model. |
| GET | `/readyz` | Readiness: can this instance actually serve? |
| POST | `/predict` | Score one account |
| POST | `/predict/batch` | Score up to 500 accounts |

`/healthz` and `/readyz` are deliberately different. Liveness says the process is up;
readiness says the artifacts loaded *and* validated against each other. A deployment
that conflates them will route traffic to a container whose model failed to load.

## The model

`artifacts/model_v3.json` is a logistic-regression coefficient set;
`artifacts/feature_spec.json` declares how a raw request becomes the feature vector.
Scoring is a dot product and a sigmoid in `svc/model/scorer.py`.

**No scikit-learn, numpy or scipy**, on purpose:

- Predictions are reproducible across platforms and Python versions.
- The weights are reviewable in a pull-request diff.
- Nothing is unpickled, so the model registry is not a code-execution path.

The registry refuses to serve a model whose `feature_spec_version` does not match the
loaded spec. A model trained against one feature contract and served against another
produces confident nonsense, and it is the easiest way to break this service invisibly.

## Evaluation

```bash
make eval
python eval/run_eval.py --assert-f1 0.80
```

**F1 is the primary metric, not accuracy.** The evaluation set is 17% positive, so
always predicting "no churn" scores 83%. The evaluator prints that majority baseline
next to accuracy so the comparison is unavoidable. CI enforces F1 ≥ 0.80; the shipped
model scores 0.8806.

Rows the feature pipeline rejects are counted as `skipped` and reported, never dropped
silently — hiding them would inflate every metric.

## CI

`.github/workflows/ci.yml` is what GitHub runs; `ci/run_ci.sh` is an executable mirror
and is what runs locally and in grading. **Change one and you must change the other.**

See `ARCHITECTURE.md` for the train/serve-skew rules.
