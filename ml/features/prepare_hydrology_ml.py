"""
Prepare hydrology data for machine learning.

Input:
    data/processed/historical_180days_all_stations.csv

Output:
    data/processed/hydrology_ml_ready.csv

Policy:
    - Raw historical data is never modified.
    - Source-specific invalid values are flagged.
    - Station 557600 value -25.13 is treated as invalid source data.
    - Short internal gaps (<= 5 hours) are linearly interpolated.
    - Long gaps (>= 6 hours) remain missing.
    - Original values are preserved in the `value` column.
    - `value_imputed` is the ML-ready value.
    - Provenance is preserved through `data_quality`.
"""

from pathlib import Path

import numpy as np
import pandas as pd


# ============================================================
# PATHS
# ============================================================

INPUT_FILE = Path(
    "data/processed/historical_180days_all_stations.csv"
)

OUTPUT_FILE = Path(
    "data/processed/hydrology_ml_ready.csv"
)


# ============================================================
# CONFIGURATION
# ============================================================

# Short gaps are safe candidates for interpolation.
MAX_INTERPOLATION_GAP_HOURS = 5

# Known source-specific invalid value discovered during QC.
# This is NOT removed from the raw dataset.
INVALID_SOURCE_VALUES = {
    557600: {-25.13},
}


# ============================================================
# VALIDATION HELPERS
# ============================================================

def validate_input(df: pd.DataFrame) -> None:
    """Validate the raw historical dataset."""

    required_columns = {
        "station_id",
        "timestamp",
        "value",
    }

    missing_columns = required_columns - set(df.columns)

    if missing_columns:
        raise ValueError(
            f"Missing required columns: {sorted(missing_columns)}"
        )

    if df.empty:
        raise ValueError("Input dataset is empty.")

    if df["station_id"].isna().any():
        raise ValueError("station_id contains missing values.")

    if df["timestamp"].isna().any():
        raise ValueError("timestamp contains missing values.")

    duplicate_count = df.duplicated(
        subset=["station_id", "timestamp"]
    ).sum()

    if duplicate_count:
        raise ValueError(
            f"Found {duplicate_count} duplicate station/timestamp rows."
        )


def calculate_missing_run_lengths(
    series: pd.Series,
) -> pd.Series:
    """
    Calculate consecutive missing-run length for every row.

    The result contains the size of the missing block that each
    missing observation belongs to.
    """

    missing = series.isna()

    groups = missing.ne(missing.shift()).cumsum()

    run_sizes = missing.groupby(groups).transform("sum")

    return run_sizes.where(missing, 0).astype(int)


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    print("=" * 70)
    print("HYDROLOGY ML DATA PREPARATION")
    print("=" * 70)

    # --------------------------------------------------------
    # Load
    # --------------------------------------------------------

    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Input file not found: {INPUT_FILE}"
        )

    df = pd.read_csv(INPUT_FILE)

    print(f"Input file: {INPUT_FILE}")
    print(f"Loaded rows: {len(df)}")

    validate_input(df)

    # --------------------------------------------------------
    # Basic normalization
    # --------------------------------------------------------

    df["station_id"] = pd.to_numeric(
        df["station_id"],
        errors="coerce",
    ).astype("Int64")

    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        errors="coerce",
    )

    df["value"] = pd.to_numeric(
        df["value"],
        errors="coerce",
    )

    if df["station_id"].isna().any():
        raise ValueError("Invalid station_id values found.")

    if df["timestamp"].isna().any():
        raise ValueError("Invalid timestamp values found.")

    df["station_id"] = df["station_id"].astype(int)

    df = df.sort_values(
        ["station_id", "timestamp"]
    ).reset_index(drop=True)

    # --------------------------------------------------------
    # Dataset summary
    # --------------------------------------------------------

    print(f"Stations: {df['station_id'].nunique()}")
    print(
        f"Start: {df['timestamp'].min()}"
    )
    print(
        f"End:   {df['timestamp'].max()}"
    )

    duplicate_count = df.duplicated(
        subset=["station_id", "timestamp"]
    ).sum()

    print(f"Duplicate station/timestamp rows: {duplicate_count}")

    if duplicate_count:
        raise ValueError(
            "Duplicate station/timestamp rows detected."
        )

    # --------------------------------------------------------
    # Preserve original value
    # --------------------------------------------------------

    df["value_original"] = df["value"]

    # --------------------------------------------------------
    # Detect known invalid source values
    # --------------------------------------------------------

    df["invalid_source_value"] = False

    for station_id, invalid_values in INVALID_SOURCE_VALUES.items():

        station_mask = df["station_id"].eq(station_id)

        invalid_mask = (
            station_mask
            & df["value"].isin(invalid_values)
        )

        df.loc[
            invalid_mask,
            "invalid_source_value"
        ] = True

    invalid_count = int(
        df["invalid_source_value"].sum()
    )

    print(
        f"Known invalid source values detected: {invalid_count}"
    )

    if invalid_count:

        print("\nInvalid source values by station:")

        invalid_summary = (
            df[df["invalid_source_value"]]
            .groupby("station_id")
            .size()
            .to_string()
        )

        print(invalid_summary)

    # --------------------------------------------------------
    # Create ML working value
    # --------------------------------------------------------

    # Start from original values.
    df["value_imputed"] = df["value"]

    # Known invalid source values must not enter ML.
    df.loc[
        df["invalid_source_value"],
        "value_imputed"
    ] = np.nan

    # --------------------------------------------------------
    # Calculate missing runs
    # --------------------------------------------------------

    df["missing_run_hours"] = (
        df.groupby("station_id", group_keys=False)[
            "value_imputed"
        ]
        .transform(calculate_missing_run_lengths)
    )

    # --------------------------------------------------------
    # Data-quality classification
    # --------------------------------------------------------

    df["data_quality"] = "observed"

    # Known invalid source observations
    df.loc[
        df["invalid_source_value"],
        "data_quality"
    ] = "invalid_source_value"

    # --------------------------------------------------------
    # Interpolate only short internal gaps
    # --------------------------------------------------------

    original_missing_mask = df["value_imputed"].isna()

    short_gap_mask = (
        original_missing_mask
        & df["missing_run_hours"].between(
            1,
            MAX_INTERPOLATION_GAP_HOURS,
        )
    )

    # Do not interpolate invalid source values automatically.
    short_gap_mask &= ~df["invalid_source_value"]

    short_gap_count = int(short_gap_mask.sum())

    print(
        f"Short missing observations eligible for interpolation: "
        f"{short_gap_count}"
    )

    # Work station by station.
    interpolated_series = (
        df.groupby("station_id", group_keys=False)[
            "value_imputed"
        ]
        .transform(
            lambda s: s.interpolate(
                method="linear",
                limit=MAX_INTERPOLATION_GAP_HOURS,
                limit_area="inside",
            )
        )
    )

    # Only accept interpolation for explicitly eligible rows.
    df.loc[
        short_gap_mask,
        "value_imputed"
    ] = interpolated_series[short_gap_mask]

    # Mark successfully interpolated observations.
    successfully_interpolated = (
        short_gap_mask
        & df["value_imputed"].notna()
    )

    df.loc[
        successfully_interpolated,
        "data_quality"
    ] = "interpolated_short_gap"

    df.loc[
        successfully_interpolated,
        "invalid_source_value"
    ] = False

    # --------------------------------------------------------
    # Recalculate missing run lengths after interpolation
    # --------------------------------------------------------

    df["missing_run_hours"] = (
        df.groupby("station_id", group_keys=False)[
            "value_imputed"
        ]
        .transform(calculate_missing_run_lengths)
    )

    # --------------------------------------------------------
    # Remaining missing observations
    # --------------------------------------------------------

    remaining_missing = df["value_imputed"].isna()

    # Preserve invalid-source classification.
    invalid_remaining = (
        remaining_missing
        & df["invalid_source_value"]
    )

    df.loc[
        invalid_remaining,
        "data_quality"
    ] = "invalid_source_value"

    # All other remaining missing observations are long gaps.
    long_gap_remaining = (
        remaining_missing
        & ~df["invalid_source_value"]
    )

    df.loc[
        long_gap_remaining,
        "data_quality"
    ] = "missing_long_gap"

    # --------------------------------------------------------
    # Convert flag to integer
    # --------------------------------------------------------

    df["is_imputed"] = (
        df["data_quality"]
        .eq("interpolated_short_gap")
        .astype(int)
    )

    # --------------------------------------------------------
    # Validation
    # --------------------------------------------------------

    print("\n" + "=" * 70)
    print("VALIDATION")
    print("=" * 70)

    print(f"Rows: {len(df)}")
    print(f"Stations: {df['station_id'].nunique()}")
    print(
        f"Time range: "
        f"{df['timestamp'].min()} -> {df['timestamp'].max()}"
    )

    print(
        f"\nOriginal missing values: "
        f"{df['value_original'].isna().sum()}"
    )

    print(
        f"Known invalid source values: "
        f"{df['invalid_source_value'].sum()}"
    )

    print(
        f"Interpolated values: "
        f"{(df['data_quality'] == 'interpolated_short_gap').sum()}"
    )

    print(
        f"Remaining missing ML values: "
        f"{df['value_imputed'].isna().sum()}"
    )

    print("\nData quality distribution:")

    print(
        df["data_quality"]
        .value_counts()
        .to_string()
    )

    # --------------------------------------------------------
    # Invalid source value validation
    # --------------------------------------------------------

    invalid_rows = df["invalid_source_value"]

    if invalid_rows.any():

        invalid_values = (
            df.loc[invalid_rows, "value"]
            .value_counts()
            .to_dict()
        )

        print("\nInvalid source value distribution:")

        for value, count in invalid_values.items():
            print(f"  {value}: {count}")

        # All invalid source values must remain missing in ML value.
        invalid_with_ml_value = (
            df.loc[
                invalid_rows,
                "value_imputed"
            ]
            .notna()
            .sum()
        )

        if invalid_with_ml_value:
            raise ValueError(
                "Invalid source values still have ML values."
            )

    # --------------------------------------------------------
    # Raw-value preservation
    # --------------------------------------------------------

    raw_changed = (
        df["value_original"].fillna(-999999999)
        != df["value"].fillna(-999999999)
    ).sum()

    if raw_changed:
        raise ValueError(
            "Original/raw values were unexpectedly modified."
        )

    print(
        "\nRaw value preservation check: PASSED"
    )

    # --------------------------------------------------------
    # Duplicate validation
    # --------------------------------------------------------

    duplicate_count = df.duplicated(
        subset=["station_id", "timestamp"]
    ).sum()

    print(
        f"Duplicate station/timestamp rows: {duplicate_count}"
    )

    if duplicate_count:
        raise ValueError(
            "Duplicate station/timestamp rows found."
        )

    # --------------------------------------------------------
    # Station coverage
    # --------------------------------------------------------

    station_counts = (
        df.groupby("station_id")
        .size()
    )

    print("\nRows per station:")

    print(
        station_counts.to_string()
    )

    # --------------------------------------------------------
    # Final columns
    # --------------------------------------------------------

    final_columns = [
        "station_id",
        "timestamp",
        "value",
        "value_original",
        "value_imputed",
        "is_imputed",
        "invalid_source_value",
        "data_quality",
        "missing_run_hours",
    ]

    df = df[final_columns]

    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    df.to_csv(
        OUTPUT_FILE,
        index=False,
    )

    print(
        f"\nSaved: {OUTPUT_FILE}"
    )

    print("=" * 70)
    print("HYDROLOGY ML PREPARATION COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()