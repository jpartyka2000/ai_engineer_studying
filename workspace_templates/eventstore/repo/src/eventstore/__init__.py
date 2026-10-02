"""eventstore: request-event ingestion and the performance model built on it.

A gateway sends us one event per served HTTP request. We keep the raw stream in MongoDB
-- written constantly, read by id and by recent window -- and maintain minute-grain
rollups in DuckDB, which is where every chart, SLO report and deploy comparison is
answered from. :mod:`eventstore.perfmodel` holds the statistics, and holds them as pure
functions of numbers so they can be reviewed and tested on their own.

Read ``ARCHITECTURE.md`` for why the two stores exist and what belongs in each.
"""

from __future__ import annotations

__version__ = "0.4.0"

__all__ = ["__version__"]
