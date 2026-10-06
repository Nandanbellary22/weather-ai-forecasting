from pathlib import Path

import pandas as pd


# -------------------------------------------------------------------
# Configuration
# -------------------------------------------------------------------

INPUT_FILE = Path(
    "data/processed/historical_180days_all_stations.csv"
)

OUTPUT_FILE = Path(
    "data/processed/hydrology_ml_ready.csv"
)

# Only gaps up to this length are eligible for interpolation.
# Gaps of 6 hours or more remain missing.
MAX_INTERPOLATION_GAP_HOURS = 5


# -------------------------------------------------------------------
# Data loading
# -------------------------------------------------------------------

def load_data() -> pd.DataFrame:
    print()
    print("=" * 70)
    print("LOADING HISTORICAL HYDROLOGY DATA")
    print("=" * 70)

    print(f"Input file: {INPUT_FILE}")

    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Input file not found: {INPUT_FILE}"
        )

    df = pd.read_csv(
        INPUT_FILE,
        dtype={"station_id": str},
    )

    required_columns = {
        "station_id",
        "timestamp",
        "value",
    }

    missing_columns = required_columns - set(df.columns)

    if missing_columns:
        raise ValueError(
            "Missing required columns: "
            + ", ".join(sorted(missing_columns))
        )

    df["station_id"] = (
        df["station_id"]
        .astype(str)
        .str.strip()
    )

    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        errors="coerce",
    )

    df["value"] = pd.to_numeric(
        df["value"],
        errors="coerce",
    )

    df = df[
        [
            "station_id",
            "timestamp",
            "value",
        ]
    ].copy()

    df = (
        df
        .sort_values(
            [
                "station_id",
                "timestamp",
            ]
        )
        .reset_index(drop=True)
    )

    return df


# -------------------------------------------------------------------
# Validation before processing
# -------------------------------------------------------------------

def validate_input(df: pd.DataFrame) -> None:
    print()
    print("=" * 70)
    print("INPUT DATA VALIDATION")
    print("=" * 70)

    print(f"Rows:              {len(df)}")
    print(
        f"Stations:          {df['station_id'].nunique()}"
    )
    print(
        f"Start:             {df['timestamp'].min()}"
    )
    print(
        f"End:               {df['timestamp'].max()}"
    )
    print(
        f"Missing values:    {df['value'].isna().sum()}"
    )

    duplicate_count = df.duplicated(
        subset=[
            "station_id",
            "timestamp",
        ]
    ).sum()

    print(
        f"Duplicate rows:    {duplicate_count}"
    )

    if duplicate_count != 0:
        raise ValueError(
            "Duplicate station/timestamp rows found."
        )


# -------------------------------------------------------------------
# Identify missing-value runs
# -------------------------------------------------------------------

def calculate_missing_runs(
    df: pd.DataFrame,
) -> pd.DataFrame:

    result = df.copy()

    result["is_missing"] = (
        result["value"].isna()
    )

    # Create a separate consecutive-run ID
    # within each station.
    result["missing_run_id"] = (
        result
        .groupby("station_id")["is_missing"]
        .transform(
            lambda x:
            x.ne(x.shift()).cumsum()
        )
    )

    # Number of rows/hours in each missing run.
    result["missing_run_hours"] = (
        result
        .groupby(
            [
                "station_id",
                "missing_run_id",
            ]
        )["is_missing"]
        .transform("sum")
    )

    return result


# -------------------------------------------------------------------
# Interpolate only short internal gaps
# -------------------------------------------------------------------

def prepare_ml_values(
    df: pd.DataFrame,
) -> pd.DataFrame:

    result = calculate_missing_runs(df)

    # A gap is eligible only when:
    #
    # 1. The original value is missing.
    # 2. The entire consecutive missing run is <= 5 hours.
    #
    # We deliberately do NOT fill long gaps.
    eligible_gap = (
        result["is_missing"]
        & (
            result["missing_run_hours"]
            <= MAX_INTERPOLATION_GAP_HOURS
        )
    )

    # Linear interpolation is performed independently
    # for every station.
    #
    # Important:
    # pandas linear interpolation does not fill missing
    # values at the beginning/end when there is no valid
    # value on both sides.
    interpolated_values = (
        result
        .groupby("station_id")["value"]
        .transform(
            lambda x:
            x.interpolate(
                method="linear"
            )
        )
    )

    # Preserve the original source value.
    result["value_imputed"] = result["value"]

    # Only replace eligible short gaps.
    #
    # If an eligible gap happens to be at the edge and
    # interpolation cannot produce a value, it remains NaN.
    fill_mask = (
        eligible_gap
        & interpolated_values.notna()
    )

    result.loc[
        fill_mask,
        "value_imputed",
    ] = interpolated_values.loc[fill_mask]

    result["is_imputed"] = (
        fill_mask.astype(int)
    )

    # ----------------------------------------------------------------
    # Data quality classification
    # ----------------------------------------------------------------

    result["data_quality"] = "observed"

    # All original missing values initially become
    # missing / unavailable.
    result.loc[
        result["is_missing"],
        "data_quality",
    ] = "missing"

    # Short gaps successfully interpolated.
    result.loc[
        result["is_imputed"] == 1,
        "data_quality",
    ] = "interpolated_short_gap"

    # Long source gaps.
    long_gap_mask = (
        result["is_missing"]
        & (
            result["missing_run_hours"]
            > MAX_INTERPOLATION_GAP_HOURS
        )
    )

    result.loc[
        long_gap_mask,
        "data_quality",
    ] = "missing_long_gap"

    # Short gaps that could not be interpolated,
    # for example a gap at the beginning/end of a station series.
    short_unfilled_mask = (
        result["is_missing"]
        & (
            result["missing_run_hours"]
            <= MAX_INTERPOLATION_GAP_HOURS
        )
        & result["value_imputed"].isna()
    )

    result.loc[
        short_unfilled_mask,
        "data_quality",
    ] = "missing_short_gap"

    return result


# -------------------------------------------------------------------
# Final validation
# -------------------------------------------------------------------

def validate_output(
    df: pd.DataFrame,
) -> None:

    print()
    print("=" * 70)
    print("ML-READY DATASET VALIDATION")
    print("=" * 70)

    print(
        f"Rows:                    {len(df)}"
    )

    print(
        f"Stations:                "
        f"{df['station_id'].nunique()}"
    )

    print(
        f"Start:                   "
        f"{df['timestamp'].min()}"
    )

    print(
        f"End:                     "
        f"{df['timestamp'].max()}"
    )

    print()
    print("--- Original Values ---")

    print(
        f"Original missing:        "
        f"{df['value'].isna().sum()}"
    )

    print()
    print("--- ML Values ---")

    print(
        f"Remaining missing:      "
        f"{df['value_imputed'].isna().sum()}"
    )

    print(
        f"Values interpolated:    "
        f"{df['is_imputed'].sum()}"
    )

    print()
    print("--- Data Quality ---")

    print(
        df["data_quality"]
        .value_counts()
        .sort_index()
        .to_string()
    )

    print()
    print("--- Missing Run Sizes ---")

    missing_runs = (
        df.loc[
            df["value"].isna(),
            [
                "station_id",
                "timestamp",
                "missing_run_hours",
            ],
        ]
        .drop_duplicates(
            subset=[
                "station_id",
                "missing_run_hours",
            ]
        )
    )

    print(
        "Maximum missing run: "
        f"{df['missing_run_hours'].max()} hours"
    )

    print()
    print("--- Duplicate Station/Timestamp ---")

    duplicate_count = df.duplicated(
        subset=[
            "station_id",
            "timestamp",
        ]
    ).sum()

    print(duplicate_count)

    if duplicate_count != 0:
        raise ValueError(
            "Duplicate station/timestamp rows found."
        )

    print()
    print("--- Rows Per Station ---")

    print(
        df.groupby("station_id")
        .size()
        .sort_index()
        .to_string()
    )

    print()
    print("--- Remaining Missing Values By Station ---")

    remaining_missing = (
        df.loc[
            df["value_imputed"].isna()
        ]
        .groupby("station_id")
        .size()
        .sort_values(
            ascending=False
        )
    )

    if remaining_missing.empty:
        print("None")
    else:
        print(
            remaining_missing.to_string()
        )


# -------------------------------------------------------------------
# Main
# -------------------------------------------------------------------

def main() -> None:

    print()
    print("=" * 70)
    print("HYDROLOGY ML PREPARATION")
    print("=" * 70)

    print(
        "Interpolation policy:"
    )

    print(
        f"  1-{MAX_INTERPOLATION_GAP_HOURS} hour gaps -> "
        "eligible for linear interpolation"
    )

    print(
        "  6+ hour gaps -> remain missing"
    )

    print(
        "  Original source values -> preserved"
    )

    # ---------------------------------------------------------------
    # Load
    # ---------------------------------------------------------------

    df = load_data()

    # ---------------------------------------------------------------
    # Validate input
    # ---------------------------------------------------------------

    validate_input(df)

    # ---------------------------------------------------------------
    # Prepare ML values
    # ---------------------------------------------------------------

    print()
    print("=" * 70)
    print("PREPARING ML VALUES")
    print("=" * 70)

    prepared = prepare_ml_values(df)

    # ---------------------------------------------------------------
    # Select final columns
    # ---------------------------------------------------------------

    prepared = prepared[
        [
            "station_id",
            "timestamp",
            "value",
            "value_imputed",
            "is_imputed",
            "data_quality",
            "missing_run_hours",
        ]
    ].copy()

    prepared = (
        prepared
        .sort_values(
            [
                "station_id",
                "timestamp",
            ]
        )
        .reset_index(drop=True)
    )

    # ---------------------------------------------------------------
    # Validate output
    # ---------------------------------------------------------------

    validate_output(prepared)

    # ---------------------------------------------------------------
    # Save
    # ---------------------------------------------------------------

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    prepared.to_csv(
        OUTPUT_FILE,
        index=False,
    )

    print()
    print("=" * 70)
    print("SAVED")
    print("=" * 70)

    print(
        f"Output file: {OUTPUT_FILE}"
    )

    print(
        f"Final rows:  {len(prepared)}"
    )

    print(
        f"Final stations: "
        f"{prepared['station_id'].nunique()}"
    )


if __name__ == "__main__":
    main()