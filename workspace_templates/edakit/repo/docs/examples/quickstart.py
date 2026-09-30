"""A worked example: profile a messy CSV and prepare it for modelling.

Run it with:

    python docs/examples/quickstart.py
"""

from edakit import (
    Method,
    ScalerKind,
    Strategy,
    detect_outliers,
    fit_imputer,
    fit_one_hot,
    fit_scaler,
    load_csv,
    numeric_values,
    profile_dataset,
    render_text,
)


def main() -> None:
    """Profile the sample dataset, then build a small preprocessing pipeline."""
    rows, columns = load_csv("datasets/customers.csv")

    profile = profile_dataset(rows, columns)
    print(render_text(profile))

    print("Columns worth dropping before modelling:")
    for name in profile.empty_columns + profile.constant_columns:
        print(f"  - {name}")

    # Fill the gaps in seats, using the median so the data-entry errors do not move it.
    imputer = fit_imputer(
        rows,
        {"seats": Strategy.MEDIAN},
        column_types={name: p.inferred_type for name, p in profile.columns.items()},
    )
    filled = imputer.transform(rows)
    print(f"\nFilled seats with {imputer.fill_values.get('seats')!r}")

    # Spend has a data-entry error in it, so use the robust scaler.
    spend = numeric_values(filled, "monthly_spend")
    report = detect_outliers(spend, Method.IQR)
    print(f"IQR flagged {report.count} of {report.total} spend values")

    scaler = fit_scaler(spend, ScalerKind.ROBUST)
    print(f"Robust scaler: centre={scaler.centre:.2f} spread={scaler.spread:.2f}")

    encoder = fit_one_hot([row["plan"] for row in filled])
    print(f"Plan encodes to {encoder.width} columns: {encoder.column_names}")


if __name__ == "__main__":
    main()
