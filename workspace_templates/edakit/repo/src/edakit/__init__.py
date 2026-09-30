"""edakit -- exploratory data analysis and preprocessing for tabular data.

Deliberately dependency-free: the standard library only, no pandas and no numpy. That
keeps it importable anywhere, makes every number testable against a hand-computed
constant, and means the whole pipeline is readable Python rather than a stack of
vectorised calls.

A typical session:

    >>> from edakit import load_csv, profile_dataset, render_text
    >>> rows, columns = load_csv("datasets/customers.csv")
    >>> profile = profile_dataset(rows, columns)
    >>> profile.row_count > 0
    True
    >>> "signup_date" in profile.columns
    True

Every transformer follows fit-then-transform, and ``transform`` never inspects the
data it is transforming -- that is what stops a scaler applied to one row producing
different numbers than the same scaler applied to a batch.
"""

from edakit.corr import (
    Summary,
    correlation_matrix,
    highly_correlated_pairs,
    pearson,
    spearman,
    summarise,
)
from edakit.encode import (
    OneHotEncoder,
    OrdinalEncoder,
    UnseenPolicy,
    fit_one_hot,
    fit_ordinal,
)
from edakit.missing import (
    Imputer,
    MissingReport,
    Strategy,
    analyse_missing,
    fit_imputer,
)
from edakit.outliers import Method, OutlierReport, detect_outliers, quantile, winsorize
from edakit.profile import DatasetProfile, load_csv, numeric_values, profile_dataset
from edakit.report import render_markdown, render_text
from edakit.scale import Scaler, ScalerKind, fit_scaler
from edakit.schema_infer import ColumnProfile, ColumnType, infer_schema, is_null

__version__ = "0.4.0"

__all__ = [
    "ColumnProfile",
    "ColumnType",
    "DatasetProfile",
    "Imputer",
    "Method",
    "MissingReport",
    "OneHotEncoder",
    "OrdinalEncoder",
    "OutlierReport",
    "Scaler",
    "ScalerKind",
    "Strategy",
    "Summary",
    "UnseenPolicy",
    "analyse_missing",
    "correlation_matrix",
    "detect_outliers",
    "fit_imputer",
    "fit_one_hot",
    "fit_ordinal",
    "fit_scaler",
    "highly_correlated_pairs",
    "infer_schema",
    "is_null",
    "load_csv",
    "numeric_values",
    "pearson",
    "profile_dataset",
    "quantile",
    "render_markdown",
    "render_text",
    "spearman",
    "summarise",
    "winsorize",
]
