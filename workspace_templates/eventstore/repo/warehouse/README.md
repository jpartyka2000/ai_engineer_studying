# warehouse/

The DuckDB file lives here. It is **derived state**: every table in it can be rebuilt
from the MongoDB event stream with

```bash
eventstore rollup --full
```

which is why `warehouse/*.duckdb` is gitignored. Committing it would mean committing
something that goes stale the moment anybody ingests anything, and a stale warehouse is
worse than an absent one because it still answers.

This README exists so the directory is tracked, since the application expects it to be
there before the first run.
