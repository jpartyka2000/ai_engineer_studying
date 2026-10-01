"""A thin Spark-shaped façade over DuckDB.

**There is no Spark here and there is no Databricks here.** This warehouse runs on DuckDB in
a single process. The jobs in ``jobs/``, the cluster policy in ``dbx_conf/`` and the
cell-delimited scripts in ``notebooks/`` are shaped the way the platform team's real
Databricks assets are shaped, because that is the shape anyone working on this has to be
able to read -- but nothing in this repository talks to a cluster, and an exercise that
needs a real one is out of scope.

What this module is *for* is keeping the notebooks honest. They are written against a tiny
Spark-like surface, so the same text can be read by someone who knows Spark and executed
here without a JVM. The surface is deliberately minuscule: four methods. Anything more and
it becomes a half-reimplementation of a distributed engine, which is a far worse thing to
maintain than some SQL.

    >>> from etlduck.spark_compat import LocalSession
    >>> session = LocalSession.builder().appName("doctest").getOrCreate()
    >>> session.sql("SELECT 1 AS one, 'a' AS letter").columns
    ['one', 'letter']
    >>> session.sql("SELECT 42 AS answer").first()["answer"]
    42
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb

from etlduck.db import connect


class LocalDataFrame:
    """The result of a query, with just enough of a DataFrame's shape to read naturally."""

    def __init__(self, relation: duckdb.DuckDBPyRelation):
        self._relation = relation

    @property
    def columns(self) -> list[str]:
        """Column names, in order."""
        return list(self._relation.columns)

    def collect(self) -> list[dict[str, Any]]:
        """Return every row as a dict.

        Named ``collect`` to match the Spark idiom, and like Spark's it brings everything
        into memory -- which here is the only option, so the name is a reminder rather than
        a warning.
        """
        names = self.columns
        return [dict(zip(names, row, strict=True)) for row in self._relation.fetchall()]

    def first(self) -> dict[str, Any] | None:
        """Return the first row as a dict, or ``None`` when there are none."""
        rows = self.collect()
        return rows[0] if rows else None

    def count(self) -> int:
        """Return the number of rows."""
        return len(self._relation.fetchall())


class LocalSession:
    """A ``SparkSession``-shaped handle on the DuckDB warehouse."""

    def __init__(self, connection: duckdb.DuckDBPyConnection, app_name: str = "etlduck"):
        self.connection = connection
        self.app_name = app_name

    class _Builder:
        """Mimics ``SparkSession.builder`` so notebook preambles read the familiar way."""

        def __init__(self) -> None:
            self._app_name = "etlduck"
            self._root: str | Path | None = None

        def appName(self, name: str) -> LocalSession._Builder:  # noqa: N802 - Spark's name
            """Set the application name."""
            self._app_name = name
            return self

        def root(self, root: str | Path) -> LocalSession._Builder:
            """Point at a project root other than the default. Not a Spark method."""
            self._root = root
            return self

        def getOrCreate(self) -> LocalSession:  # noqa: N802 - Spark's name
            """Open the warehouse and return the session."""
            return LocalSession(connect(self._root), self._app_name)

    @classmethod
    def builder(cls) -> LocalSession._Builder:
        """Return a builder. ``LocalSession.builder()`` is a call here, unlike Spark's
        property, because a classmethod that returns a fresh builder is harder to misuse
        from two notebooks at once."""
        return cls._Builder()

    def sql(self, query: str, parameters: list[Any] | None = None) -> LocalDataFrame:
        """Run a query and return a :class:`LocalDataFrame`.

        Args:
            query: The SQL.
            parameters: Values for ``?`` placeholders. Present because the Spark façade is
                no excuse for string-formatting values into SQL.

        Returns:
            The result.
        """
        if parameters:
            return LocalDataFrame(self.connection.sql(query, params=parameters))
        return LocalDataFrame(self.connection.sql(query))

    def table(self, name: str) -> LocalDataFrame:
        """Return a whole table."""
        return LocalDataFrame(self.connection.table(name))

    def stop(self) -> None:
        """Close the connection. DuckDB locks the file, so this is not optional."""
        self.connection.close()
