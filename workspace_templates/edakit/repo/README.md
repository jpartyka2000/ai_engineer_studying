# edakit

Exploratory data analysis and preprocessing for tabular data. **Standard library
only** — no pandas, no numpy.

That constraint is deliberate. It means the package drops into any environment without
a dependency negotiation, every number is testable against a hand-computed constant,
and the whole pipeline is readable Python rather than a stack of vectorised calls a
reviewer has to take on trust.

## Getting started

```bash
docker compose up -d --wait   # or: make up
make test
make profile
```

## What it does

| Module | Purpose |
|---|---|
| `schema_infer` | Infer column types from raw CSV text; recognise the dozen spellings of "missing" |
| `profile` | Load a CSV and build a whole-dataset profile with findings |
| `missing` | Missing-value analysis and fit/transform imputation |
| `outliers` | IQR, z-score and modified z-score detection; winsorizing |
| `scale` | Standard, min-max and robust scalers |
| `encode` | One-hot and ordinal encoding with explicit unseen-category handling |
| `corr` | Pearson and Spearman correlation, descriptive summaries |
| `report` | Render a profile as text or Markdown |
| `cli` | `edakit profile` and `edakit missing` |

`bench/bench_profile.py` measures how much work profiling does. It reports **operation
counts** next to the wall clock, and the counts are the figure to hold to a threshold:
`cell_reads_per_cell` is how many times each cell is examined over one
`profile_dataset` call. For a profiler that walks the table a fixed number of times it is
a small constant and does not change with the column count.

## Using it

```python
from edakit import load_csv, profile_dataset, render_text

rows, columns = load_csv("datasets/customers.csv")
profile = profile_dataset(rows, columns)
print(render_text(profile))

for finding in profile.warnings():
    print(finding)
```

From the shell:

```bash
edakit profile datasets/customers.csv --format markdown
edakit missing datasets/customers.csv --threshold 0.3
```

## The datasets

`datasets/` holds deliberately messy files — mixed null spellings (`N/A`, `none`, `-`,
empty), unicode names, an entirely-empty column, a constant column, a free-text column,
and a data-entry error in `monthly_spend`. They exist so tests exercise the cases a
synthetic fixture would let through.

## Conventions

**Everything is fit-then-transform, and `transform` never inspects the data it is
transforming.** If it did, applying a scaler to one row would produce different numbers
than applying it to a batch — which is exactly how train/serve skew gets introduced.
The tests assert this property directly.

**Nothing guesses silently.** The loader keeps every cell as a string; type inference
is a separate, inspectable step. Ties are broken deterministically, so two runs of the
same code give the same answer.

## CI

`.github/workflows/ci.yml` is what GitHub runs; `ci/run_ci.sh` is an executable mirror
and is what runs locally and in grading. **Change one and you must change the other.**
