"""
Create hourly forecasting features from MRC hydrometeorological observations.

Input:
    data/processed/mrc_vietnam_measurements.csv

Output:
    data/processed/mrc_hourly_features.csv

Design:
    - Preserve MRC station IDs exactly, including leading zeros.
    - Aggregate raw 15-minute observations to hourly resolution.
    - Do not fabricate missing measurements.
    - Build an explicit continuous hourly timeline per station.
    - Prevent lag/rolling features from crossing missing-hour gaps.
    - Create a one-hour-ahead water-level forecasting target.
"""

from pathlib import Path

import pandas as pd


INPUT_FILE = Path(
    "data/processed/mrc_vietnam_measurements.csv"
)

OUTPUT_FILE = Path(
    "data/processed/mrc_hourly_features.csv"
)

EXPECTED_RECORDS_PER_HOUR = 4
MIN_RECORDS_PER_HOUR = 3

LAG_HOURS = [1, 3, 6, 12, 24]
ROLLING_WINDOWS = [3, 6, 12, 24]


def preserve_station_ids(series: pd.Series) -> pd.Series:
    """
    Preserve MRC station IDs as six-character strings.

    Examples:
        019803 -> 019803
        039801 -> 039801
        902601 -> 902601
    """

    return (
        series.astype("string")
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
        .str.zfill(6)
    )


def load_raw_data() -> pd.DataFrame:
    """Load and validate raw MRC measurements."""

    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Input file not found: {INPUT_FILE}"
        )

    df = pd.read_csv(
        INPUT_FILE,
        dtype={
            "station_id": "string",
        },
    )

    required_columns = [
        "station_id",
        "timestamp",
        "timestamp_utc",
        "water_level",
        "rainfall",
        "temperature",
        "battery",
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing_columns:
        raise ValueError(
            "Missing required columns: "
            + ", ".join(missing_columns)
        )

    # Preserve leading zeros in MRC station IDs.
    df["station_id"] = preserve_station_ids(
        df["station_id"]
    )

    # UTC is the canonical timestamp used for feature engineering.
    df["timestamp_utc"] = pd.to_datetime(
        df["timestamp_utc"],
        utc=True,
        errors="coerce",
    )

    # Keep local timestamp for traceability.
    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        errors="coerce",
    )

    numeric_columns = [
        "water_level",
        "rainfall",
        "temperature",
        "battery",
    ]

    for column in numeric_columns:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    before = len(df)

    df = df.dropna(
        subset=[
            "station_id",
            "timestamp_utc",
        ]
    ).copy()

    removed = before - len(df)

    if removed:
        print(
            f"Removed {removed:,} rows with invalid "
            "station ID or timestamp."
        )

    df = df.sort_values(
        [
            "station_id",
            "timestamp_utc",
        ]
    ).reset_index(drop=True)

    return df


def aggregate_to_hourly(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Aggregate raw MRC measurements to hourly resolution.

    water_level:
        hourly mean

    rainfall:
        hourly sum

    temperature:
        hourly mean

    battery:
        last available value

    source_records:
        number of raw observations contributing to the hour
    """

    working = df.copy()

    working["hour"] = (
        working["timestamp_utc"]
        .dt.floor("h")
    )

    hourly = (
        working.groupby(
            [
                "station_id",
                "hour",
            ],
            as_index=False,
            sort=True,
        )
        .agg(
            water_level=("water_level", "mean"),
            rainfall=("rainfall", "sum"),
            temperature=("temperature", "mean"),
            battery=("battery", "last"),
            source_records=("timestamp_utc", "size"),
        )
    )

    hourly["expected_records"] = (
        EXPECTED_RECORDS_PER_HOUR
    )

    hourly["hour_complete"] = (
        hourly["source_records"]
        >= MIN_RECORDS_PER_HOUR
    )

    hourly["completeness_ratio"] = (
        hourly["source_records"]
        / EXPECTED_RECORDS_PER_HOUR
    ).clip(upper=1.0)

    return hourly


def build_complete_hourly_grid(
    hourly: pd.DataFrame,
) -> pd.DataFrame:
    """
    Create a continuous hourly timeline for every station.

    Missing hours are retained with NaN measurements.

    This prevents a missing hour from causing a row-based lag
    to incorrectly refer to an older available observation.
    """

    station_frames = []

    for station_id, station_df in hourly.groupby(
        "station_id",
        sort=True,
    ):
        station_df = station_df.sort_values(
            "hour"
        ).copy()

        start = station_df["hour"].min()
        end = station_df["hour"].max()

        complete_hours = pd.date_range(
            start=start,
            end=end,
            freq="1h",
            tz="UTC",
        )

        station_df = (
            station_df
            .set_index("hour")
            .reindex(complete_hours)
        )

        station_df.index.name = "hour"

        station_df = station_df.reset_index()

        # Reattach station ID to newly-created missing-hour rows.
        station_df["station_id"] = station_id

        # A missing hour has zero source observations.
        station_df["source_records"] = (
            station_df["source_records"]
            .fillna(0)
            .astype("int64")
        )

        station_df["expected_records"] = (
            EXPECTED_RECORDS_PER_HOUR
        )

        station_df["hour_complete"] = (
            station_df["source_records"]
            >= MIN_RECORDS_PER_HOUR
        )

        station_df["completeness_ratio"] = (
            station_df["source_records"]
            / EXPECTED_RECORDS_PER_HOUR
        ).clip(upper=1.0)

        station_frames.append(station_df)

    if not station_frames:
        return pd.DataFrame()

    result = pd.concat(
        station_frames,
        ignore_index=True,
    )

    result = result.sort_values(
        [
            "station_id",
            "hour",
        ]
    ).reset_index(drop=True)

    return result


def create_time_features(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """Create calendar and time features."""

    df = df.copy()

    df["hour_of_day"] = (
        df["hour"].dt.hour
    )

    df["day_of_week"] = (
        df["hour"].dt.dayofweek
    )

    df["day_of_month"] = (
        df["hour"].dt.day
    )

    return df


def create_lag_and_rolling_features(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Create continuity-aware lag and rolling features.

    Because the dataframe contains an explicit hourly grid:

        shift(1)  = previous hour
        shift(3)  = three hours ago
        shift(24) = twenty-four hours ago

    Missing source hours remain NaN and therefore cannot silently
    become valid historical features.
    """

    df = df.copy()

    grouped = df.groupby(
        "station_id",
        sort=False,
    )

    # ---------------------------------------------------------
    # Water-level lags
    # ---------------------------------------------------------

    for lag in LAG_HOURS:
        df[
            f"water_level_lag_{lag}"
        ] = (
            grouped["water_level"]
            .shift(lag)
        )

    # ---------------------------------------------------------
    # Rainfall lags
    # ---------------------------------------------------------

    for lag in LAG_HOURS:
        df[
            f"rainfall_lag_{lag}"
        ] = (
            grouped["rainfall"]
            .shift(lag)
        )

    # ---------------------------------------------------------
    # Water-level rolling means
    # ---------------------------------------------------------

    df["water_level_shift_1"] = (
        grouped["water_level"]
        .shift(1)
    )

    water_level_group = df.groupby(
        "station_id",
        sort=False,
    )["water_level_shift_1"]

    for window in ROLLING_WINDOWS:
        df[
            f"water_level_rolling_mean_{window}"
        ] = (
            water_level_group
            .transform(
                lambda values: values.rolling(
                    window=window,
                    min_periods=window,
                ).mean()
            )
        )

    # ---------------------------------------------------------
    # Rainfall rolling sums
    # ---------------------------------------------------------

    df["rainfall_shift_1"] = (
        grouped["rainfall"]
        .shift(1)
    )

    rainfall_group = df.groupby(
        "station_id",
        sort=False,
    )["rainfall_shift_1"]

    for window in ROLLING_WINDOWS:
        df[
            f"rainfall_rolling_sum_{window}"
        ] = (
            rainfall_group
            .transform(
                lambda values: values.rolling(
                    window=window,
                    min_periods=window,
                ).sum()
            )
        )

    # Temporary columns are no longer needed.
    df = df.drop(
        columns=[
            "water_level_shift_1",
            "rainfall_shift_1",
        ]
    )

    return df


def create_target(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Create the one-hour-ahead water-level target.

    The target is valid only when the next row is exactly
    one hour after the current row.
    """

    df = df.copy()

    grouped = df.groupby(
        "station_id",
        sort=False,
    )

    df["target_next_hour"] = (
        grouped["water_level"]
        .shift(-1)
    )

    df["next_hour"] = (
        grouped["hour"]
        .shift(-1)
    )

    expected_next_hour = (
        df["hour"]
        + pd.Timedelta(hours=1)
    )

    df["target_is_next_hour"] = (
        df["next_hour"]
        == expected_next_hour
    )

    # Invalidate targets across missing-hour gaps.
    df.loc[
        ~df["target_is_next_hour"],
        "target_next_hour",
    ] = pd.NA

    return df


def filter_training_rows(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Keep rows suitable for supervised forecasting.

    Temperature and battery are NOT required because they contain
    substantial missing values in the MRC historical feed.

    Water level and rainfall history are required.
    """

    df = df.copy()

    feature_columns = []

    feature_columns.extend(
        [
            f"water_level_lag_{lag}"
            for lag in LAG_HOURS
        ]
    )

    feature_columns.extend(
        [
            f"rainfall_lag_{lag}"
            for lag in LAG_HOURS
        ]
    )

    feature_columns.extend(
        [
            f"water_level_rolling_mean_{window}"
            for window in ROLLING_WINDOWS
        ]
    )

    feature_columns.extend(
        [
            f"rainfall_rolling_sum_{window}"
            for window in ROLLING_WINDOWS
        ]
    )

    required_columns = [
        "water_level",
        "target_next_hour",
        *feature_columns,
    ]

    before = len(df)

    valid_mask = (
        df[required_columns]
        .notna()
        .all(axis=1)
    )

    valid_mask &= (
        df["target_is_next_hour"]
    )

    df = df.loc[
        valid_mask
    ].copy()

    removed = before - len(df)

    print(
        "Rows removed because of missing "
        "forecast history/target: "
        f"{removed:,}"
    )

    return df


def reorder_columns(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """Return a predictable output column order."""

    columns = [
        "station_id",
        "hour",
        "water_level",
        "rainfall",
        "temperature",
        "battery",
        "source_records",
        "expected_records",
        "hour_complete",
        "completeness_ratio",
        "hour_of_day",
        "day_of_week",
        "day_of_month",
        "water_level_lag_1",
        "water_level_lag_3",
        "water_level_lag_6",
        "water_level_lag_12",
        "water_level_lag_24",
        "rainfall_lag_1",
        "rainfall_lag_3",
        "rainfall_lag_6",
        "rainfall_lag_12",
        "rainfall_lag_24",
        "water_level_rolling_mean_3",
        "water_level_rolling_mean_6",
        "water_level_rolling_mean_12",
        "water_level_rolling_mean_24",
        "rainfall_rolling_sum_3",
        "rainfall_rolling_sum_6",
        "rainfall_rolling_sum_12",
        "rainfall_rolling_sum_24",
        "target_next_hour",
        "next_hour",
        "target_is_next_hour",
    ]

    return df[
        [
            column
            for column in columns
            if column in df.columns
        ]
    ]


def print_summary(
    raw_df: pd.DataFrame,
    hourly_grid: pd.DataFrame,
    feature_df: pd.DataFrame,
) -> None:
    """Print data-quality summary."""

    print()
    print("=" * 70)
    print("MRC HOURLY FEATURE SUMMARY")
    print("=" * 70)

    print(
        f"Raw input rows:              {len(raw_df):,}"
    )

    print(
        "Raw stations:                "
        f"{raw_df['station_id'].nunique()}"
    )

    print(
        f"Hourly grid rows:            "
        f"{len(hourly_grid):,}"
    )

    print(
        f"Final forecasting rows:      "
        f"{len(feature_df):,}"
    )

    print()
    print("Station IDs:")

    station_ids = sorted(
        feature_df["station_id"]
        .dropna()
        .astype(str)
        .unique()
        .tolist()
    )

    print(station_ids)

    print()
    print("Rows per station:")

    print(
        feature_df
        .groupby("station_id")
        .size()
        .to_string()
    )

    print()
    print("Hourly completeness:")

    completeness = (
        hourly_grid
        .groupby("station_id")
        .agg(
            hours=("hour", "size"),
            complete_hours=(
                "hour_complete",
                "sum",
            ),
            source_records=(
                "source_records",
                "sum",
            ),
        )
    )

    completeness["complete_pct"] = (
        completeness["complete_hours"]
        / completeness["hours"]
        * 100
    )

    print(
        completeness.to_string()
    )

    print()
    print(
        "Missing source hours:"
    )

    missing_hour_rows = []

    for station_id, station_df in (
        hourly_grid.groupby(
            "station_id",
            sort=True,
        )
    ):
        missing_hours = station_df[
            station_df["source_records"] == 0
        ]

        if not missing_hours.empty:
            missing_hour_rows.append(
                {
                    "station_id": station_id,
                    "missing_hours": len(
                        missing_hours
                    ),
                    "first_missing": (
                        missing_hours["hour"].min()
                    ),
                    "last_missing": (
                        missing_hours["hour"].max()
                    ),
                }
            )

    if missing_hour_rows:
        print(
            pd.DataFrame(
                missing_hour_rows
            ).to_string(index=False)
        )
    else:
        print(
            "No missing source hours."
        )

    print()
    print(
        "Remaining missing values in final features:"
    )

    missing = (
        feature_df
        .isna()
        .sum()
    )

    missing = missing[
        missing > 0
    ]

    if missing.empty:
        print("None")
    else:
        print(
            missing.to_string()
        )

    print("=" * 70)


def main() -> None:
    print("=" * 70)
    print("MRC HOURLY FEATURE BUILDER")
    print("=" * 70)

    print()
    print(
        f"Input:  {INPUT_FILE}"
    )

    print(
        f"Output: {OUTPUT_FILE}"
    )

    # ---------------------------------------------------------
    # 1. Load raw MRC data
    # ---------------------------------------------------------

    print()
    print(
        "Loading raw MRC measurements..."
    )

    raw_df = load_raw_data()

    print(
        f"Loaded {len(raw_df):,} raw measurement rows."
    )

    # ---------------------------------------------------------
    # 2. Aggregate to hourly
    # ---------------------------------------------------------

    print()
    print(
        "Aggregating 15-minute observations to hourly..."
    )

    hourly = aggregate_to_hourly(
        raw_df
    )

    print(
        f"Hourly source buckets: {len(hourly):,}"
    )

    # ---------------------------------------------------------
    # 3. Build complete hourly timeline
    # ---------------------------------------------------------

    print()
    print(
        "Building explicit hourly timeline per station..."
    )

    hourly_grid = (
        build_complete_hourly_grid(
            hourly
        )
    )

    print(
        f"Hourly grid rows: {len(hourly_grid):,}"
    )

    # ---------------------------------------------------------
    # 4. Time features
    # ---------------------------------------------------------

    hourly_grid = create_time_features(
        hourly_grid
    )

    # ---------------------------------------------------------
    # 5. Lag and rolling features
    # ---------------------------------------------------------

    print()
    print(
        "Creating continuity-aware lag "
        "and rolling features..."
    )

    features = (
        create_lag_and_rolling_features(
            hourly_grid
        )
    )

    # ---------------------------------------------------------
    # 6. Forecast target
    # ---------------------------------------------------------

    print()
    print(
        "Creating one-hour-ahead "
        "water-level target..."
    )

    features = create_target(
        features
    )

    # ---------------------------------------------------------
    # 7. Filter training rows
    # ---------------------------------------------------------

    print()
    print(
        "Filtering forecasting-ready rows..."
    )

    before_filter = len(features)

    features = filter_training_rows(
        features
    )

    print(
        "Rows before final filtering: "
        f"{before_filter:,}"
    )

    print(
        "Rows after final filtering:  "
        f"{len(features):,}"
    )

    # ---------------------------------------------------------
    # 8. Reorder columns
    # ---------------------------------------------------------

    features = reorder_columns(
        features
    )

    # Explicitly preserve six-character station IDs.
    features["station_id"] = (
        features["station_id"]
        .astype("string")
        .str.zfill(6)
    )

    # ---------------------------------------------------------
    # 9. Save
    # ---------------------------------------------------------

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    features.to_csv(
        OUTPUT_FILE,
        index=False,
    )

    # ---------------------------------------------------------
    # 10. Print summary
    # ---------------------------------------------------------

    print_summary(
        raw_df=raw_df,
        hourly_grid=hourly_grid,
        feature_df=features,
    )

    print()
    print(
        f"Saved successfully: {OUTPUT_FILE}"
    )


if __name__ == "__main__":
    main()