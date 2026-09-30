# Architecture

## The pipeline

```
CSV file
  │
  ├─ profile.load_csv          everything stays a string; nothing is coerced
  │
  ├─ schema_infer.infer_schema types inferred as a separate, inspectable step
  │
  ├─ missing / outliers        analyse, then fit a transformer
  │  scale / encode
  │
  └─ profile.profile_dataset   assembles the whole picture
       └─ report.render_*      text or Markdown
```

## Fit then transform

Every transformer -- `Imputer`, `Scaler`, `OneHotEncoder`, `OrdinalEncoder` -- is
produced by a `fit_*` function and then applied with `.transform()`.

**`transform` must never look at the data it is transforming.** The learned values live
on the object. This is not stylistic: a scaler that recomputed its mean at transform
time would map the same row to different numbers depending on what else was in the
batch, and a model trained on one and served the other would silently degrade.
`test_transform_is_independent_of_the_batch` asserts it.

A corollary: `transform` returns new objects and never mutates its input, so a caller
can diff before against after.

## Determinism

Hash randomisation is on by default in Python, so anything that depends on set or dict
iteration order gives different answers between runs. Every place a choice could be
arbitrary resolves it explicitly:

- One-hot categories are **sorted**, so column order is stable.
- Mode imputation sorts before counting, so ties resolve the same way every run.
- `highly_correlated_pairs` and `columns_above` return sorted results.
- Spearman averages tied ranks rather than breaking ties by position.

## Widths are fixed at fit time

`OneHotEncoder.width` is determined when it is fitted and cannot change. The missing
bucket always exists; the other bucket exists whenever the policy uses it. A consumer
that allocated N columns will always receive N columns, whatever categories transform
actually meets.

`UnseenPolicy` makes the unknown-category decision explicit rather than defaulted:
fold into `__other__`, raise, or encode as all zeros. There is no "just ignore it"
option, because that is what silently changes the output width.

## Numeric choices worth knowing

- **Quantiles** use linear interpolation, implemented here rather than taken from
  `statistics.quantiles`, because libraries disagree on the convention and a silent
  change of convention shifts every outlier bound.
- **Standard deviation** is the population form (`pstdev`) throughout. Mixing sample
  and population forms between fit and transform would be a subtle scaling bug.
- **Skew** is flagged by `|mean - median|` normalised by **IQR**, not standard
  deviation. The standard deviation is inflated by the very outliers that cause skew,
  so using it makes the check least sensitive exactly when it matters most.
- **Correlation** returns `0.0` for a constant series rather than `NaN`, and clamps to
  `[-1, 1]` because float error can push a perfect correlation past 1.0.

## Testing

`tests/` runs against the real files in `datasets/`, not synthetic fixtures. Numeric
expectations are hand-computed with the derivation in the test docstring, so a test
failing means the maths changed rather than that a snapshot drifted.

Docstring examples in `src/edakit/` are executed by CI, so the usage shown in `__init__`
cannot rot.
