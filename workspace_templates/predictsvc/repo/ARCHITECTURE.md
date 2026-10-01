# Architecture

## Layers

```
HTTP request
  │
  ├─ svc/schemas.py            pydantic validation; unknown fields are REJECTED
  │
  ├─ svc/routers/predict.py    HTTP concerns only: status codes, batching
  │
  ├─ svc/features/pipeline.py  raw payload -> numeric vector, driven by the spec
  │
  └─ svc/model/scorer.py       dot product + sigmoid over a coefficient artifact
       ▲
       └─ svc/model/registry.py  loads and cross-validates the two artifacts
```

Routers contain no business logic. The pipeline contains no HTTP. That separation is
what lets the scorer be tested against hand-computed numbers with no server running.

## Train/serve skew is the thing to protect against

Everything about the feature layer is shaped by it.

**The spec is data, not code.** Every scale, default, clipping bound and category list
lives in `artifacts/feature_spec.json`. Changing how a feature is computed is therefore
an artifact change that bumps a version, not a quiet code edit that silently diverges
from what training did.

**The registry cross-validates.** `assert_compatible` checks two independent things:

1. `model.feature_spec_version == spec.version` — catches "somebody shipped a new spec
   without retraining".
2. Every coefficient name is emitted by the spec — catches "a spec edit forgot to bump
   the version", which the first check would miss.

**What those two checks cannot see.** Both compare *names*. Neither looks at a single
feature *value*, so an edited `scale`, `default`, `clip_min` or `clip_max` passes both
and the service goes on reporting itself ready. Every deployed spec version is archived
under `artifacts/archive/` so the contract a stored prediction was made under can always
be recovered — but nothing compares the active spec against its archived copy, which
means a spec that disagrees with the version it claims to be is detectable only by its
effect on the metrics.

**Nothing is silently defaulted.** A missing required field, an unparseable number and
an unknown category all raise. Substituting a plausible value produces a confident wrong
prediction, which is far worse than a 422.

**A missing feature raises rather than scoring as zero.** Zero is a meaningful value for
most of these features, so treating absence as zero is not a safe default — it is a
wrong answer that looks right.

## Feature width is fixed by the spec

`FeatureSpec.output_names` is determined by the spec alone. Categorical features emit
one column per declared category, always, so the vector a model receives cannot change
shape because of which value happened to arrive.

Lookup into the vector is **by name**, never by position, so a reordered pipeline cannot
misalign weights against features. `test_feature_order_does_not_affect_the_score` pins
this.

## Numeric choices

- **Sigmoid is branched.** `1/(1+exp(-x))` raises `OverflowError` for strongly negative
  inputs, so the negative branch uses `exp(x)/(1+exp(x))`.
- **Threshold comparison is `>=`.** A threshold of 0.0 therefore predicts the positive
  class for everything, which is what someone asking for that would expect.
- **Probabilities are rounded to 6 places in responses** so stored predictions are
  stable across platforms, while scoring itself stays full precision.

## Batching

One unscoreable account does not fail a batch: it is counted in `rejected` and omitted
from `predictions`. A nightly job of 500 should not lose 499 good rows to one bad one.
The count is reported rather than hidden, so a caller can tell "all scored" from "most
scored".

Batches are capped at 500 so a single request cannot occupy a worker indefinitely.

## Testing

- `tests/test_scorer_and_features.py` — hand-computed scores and every pipeline
  rejection path. Marked `model`.
- `tests/test_api_and_eval.py` — request/response contract including the 422s, plus
  metric arithmetic against countable confusion matrices. Marked `contract` and `model`.

The metric tests include a case with 95% accuracy and F1 of 0.0, because that is the
shape of a model that has learned to always say "no".
