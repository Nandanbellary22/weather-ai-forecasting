
import pandas as pd
import numpy as np


# =========================================================
# Configuration
# =========================================================

INPUT_FILE = "data/processed/hydrology_ml_ready.csv"
OUTPUT_FILE = "data/processed/hydrology_forecast_features.csv"


# Original temporal features used by the existing project
BASE_LAGS = [
    1,
    3,
    6,
    12,
    24,
]

# Additional temporal lags from the existing enhanced pipeline
ENHANCED_LAGS = [
    2,
    4,
    8,
    18,
    36,
    48,
    72,
]

# Original rolling windows
BASE_ROLLING_WINDOWS = [
    3,
    6,
    24,
]

# Additional rolling windows
ENHANCED_ROLLING_WINDOWS = [
    12,
    48,
    72,
]


# =========================================================
# Validation
# =========================================================

def validate_input(df):
    """
    Validate the ML-ready hydrology dataset before creating
    forecasting features.
    """

    required_columns = [
        "station_id",
        "timestamp",
        "value",
        "value_imputed",
        "is_imputed",
        "data_quality",
        "missing_run_hours",
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing_columns:
        raise ValueError(
            f"Missing required columns: {missing_columns}"
        )

    if df["timestamp"].isna().any():
        raise ValueError(
            "Input contains missing timestamps."
        )

    duplicate_count = df.duplicated(
        subset=["station_id", "timestamp"]
    ).sum()

    if duplicate_count > 0:
        raise ValueError(
            f"Input contains {duplicate_count} "
            "duplicate station/timestamp rows."
        )

    print()
    print("=" * 70)
    print("INPUT VALIDATION")
    print("=" * 70)

    print(f"Rows: {len(df)}")
    print(f"Stations: {df['station_id'].nunique()}")

    print(
        f"Time range: "
        f"{df['timestamp'].min()} -> "
        f"{df['timestamp'].max()}"
    )

    print(
        f"Duplicate station/timestamp rows: "
        f"{duplicate_count}"
    )

    print()
    print("Data quality distribution:")

    print(
        df["data_quality"]
        .value_counts(dropna=False)
        .to_string()
    )

    original_missing = df["value"].isna().sum()
    imputed_missing = df["value_imputed"].isna().sum()

    print()
    print(f"Original value missing: {original_missing}")
    print(f"value_imputed missing: {imputed_missing}")

    return True


# =========================================================
# Feature Creation
# =========================================================

def create_features(df):
    """
    Create temporal forecasting features from the ML-ready
    hydrology dataset.

    Lag, rolling, change, and target calculations are confined
    to continuous hourly segments within each station.

    Existing source values and data-quality metadata are
    preserved. No missing observations are artificially added.
    """

    required_columns = [
        "station_id",
        "timestamp",
        "value",
        "value_imputed",
        "is_imputed",
        "data_quality",
        "missing_run_hours",
    ]

    missing_columns = [
        column for column in required_columns
        if column not in df.columns
    ]

    if missing_columns:
        raise ValueError(
            f"Missing required columns: {missing_columns}"
        )

    df = (
        df.sort_values(
            ["station_id", "timestamp"]
        )
        .reset_index(drop=True)
        .copy()
    )

    # -----------------------------------------------------
    # Continuous hourly segments
    # -----------------------------------------------------

    # A new segment begins at each station's first observation
    # and whenever consecutive timestamps are not one hour apart.
    timestamp_difference = (
        df.groupby("station_id")["timestamp"].diff()
    )

    segment_start = (
        timestamp_difference.ne(pd.Timedelta(hours=1))
    )

    df["_segment_id"] = (
        segment_start
        .groupby(df["station_id"])
        .cumsum()
    )

    segment_keys = ["station_id", "_segment_id"]
    grouped_values = df.groupby(
        segment_keys,
        sort=False,
    )["value_imputed"]

    # -----------------------------------------------------
    # Basic time features
    # -----------------------------------------------------

    df["hour"] = df["timestamp"].dt.hour
    df["day_of_week"] = df["timestamp"].dt.dayofweek
    df["day_of_month"] = df["timestamp"].dt.day

    df["hour_sin"] = np.sin(
        2 * np.pi * df["hour"] / 24
    )

    df["hour_cos"] = np.cos(
        2 * np.pi * df["hour"] / 24
    )

    # -----------------------------------------------------
    # Base lag features
    # -----------------------------------------------------

    for lag in BASE_LAGS:
        df[f"lag_{lag}"] = grouped_values.shift(lag)

    # -----------------------------------------------------
    # Enhanced lag features
    # -----------------------------------------------------

    for lag in ENHANCED_LAGS:
        df[f"lag_{lag}"] = grouped_values.shift(lag)

    # -----------------------------------------------------
    # Rolling means
    #
    # Only prior observations from the same continuous
    # segment are allowed into each rolling window.
    # -----------------------------------------------------

    for window in (
        BASE_ROLLING_WINDOWS + ENHANCED_ROLLING_WINDOWS
    ):
        df[f"rolling_mean_{window}"] = (
            df.groupby(segment_keys, sort=False)["value_imputed"]
            .transform(
                lambda values: (
                    values.shift(1)
                    .rolling(window)
                    .mean()
                )
            )
        )

    # -----------------------------------------------------
    # Short-term variability
    # -----------------------------------------------------

    for window in (6, 24):
        df[f"rolling_std_{window}"] = (
            df.groupby(segment_keys, sort=False)["value_imputed"]
            .transform(
                lambda values: (
                    values.shift(1)
                    .rolling(window)
                    .std()
                )
            )
        )

    # -----------------------------------------------------
    # Change features
    # -----------------------------------------------------

    df["change_1"] = (
        df["value_imputed"] - df["lag_1"]
    )

    df["change_3"] = (
        df["value_imputed"] - df["lag_3"]
    )

    df["change_6"] = (
        df["value_imputed"] - df["lag_6"]
    )

    # -----------------------------------------------------
    # Data quality features
    #
    # Preserve the existing quality metadata semantics.
    # -----------------------------------------------------

    df["is_imputed"] = df["is_imputed"].astype(int)

    df["missing_run_hours"] = (
        pd.to_numeric(
            df["missing_run_hours"],
            errors="coerce",
        )
        .fillna(0)
    )

    # -----------------------------------------------------
    # Next-hour target
    # -----------------------------------------------------

    # The target can only come from the next row in the same
    # continuous hourly segment.
    df["target_next_hour"] = grouped_values.shift(-1)

    next_timestamp = (
        df.groupby(segment_keys, sort=False)["timestamp"]
        .shift(-1)
    )

    valid_next_hour = (
        next_timestamp - df["timestamp"]
    ).eq(pd.Timedelta(hours=1))

    df.loc[
        ~valid_next_hour,
        "target_next_hour",
    ] = np.nan

    # The segment ID is an internal helper, not a model feature.
    df.drop(columns=["_segment_id"], inplace=True)

    return df


# =========================================================
# Feature Validation
# =========================================================

def validate_features(df):
    """
    Validate all model features explicitly.
    """

    print()
    print("=" * 70)
    print("FEATURE VALIDATION")
    print("=" * 70)

    feature_columns = [
        "hour",
        "day_of_week",
        "day_of_month",
        "hour_sin",
        "hour_cos",
        "lag_1",
        "lag_2",
        "lag_3",
        "lag_4",
        "lag_6",
        "lag_8",
        "lag_12",
        "lag_18",
        "lag_24",
        "lag_36",
        "lag_48",
        "lag_72",
        "rolling_mean_3",
        "rolling_mean_6",
        "rolling_mean_12",
        "rolling_mean_24",
        "rolling_mean_48",
        "rolling_mean_72",
        "rolling_std_6",
        "rolling_std_24",
        "change_1",
        "change_3",
        "change_6",
        "is_imputed",
        "missing_run_hours",
    ]

    missing_feature_columns = [
        column
        for column in feature_columns
        if column not in df.columns
    ]

    if missing_feature_columns:
        raise ValueError(
            "Missing generated feature columns: "
            f"{missing_feature_columns}"
        )

    print()
    print("Missing values by feature:")

    missing_counts = (
        df[feature_columns]
        .isna()
        .sum()
        .sort_values(ascending=False)
    )

    print(missing_counts.to_string())

    target_missing = df["target_next_hour"].isna().sum()

    print()
    print(f"Missing target_next_hour: {target_missing}")

    # Missing values at segment boundaries and within
    # insufficient history windows are expected.
    # They are not silently filled here.

    return feature_columns


# =========================================================
# Main
# =========================================================

def main():

    print("=" * 70)
    print("HYDROLOGY FORECAST FEATURE ENGINEERING")
    print("=" * 70)

    # -----------------------------------------------------
    # Load
    # -----------------------------------------------------

    print()
    print("Loading ML-ready hydrology dataset...")

    df = pd.read_csv(
        INPUT_FILE,
        parse_dates=["timestamp"],
    )

    print(f"Loaded rows: {len(df)}")

    # -----------------------------------------------------
    # Validate input
    # -----------------------------------------------------

    validate_input(df)

    # -----------------------------------------------------
    # Create features
    # -----------------------------------------------------

    print()
    print("=" * 70)
    print("CREATING FEATURES")
    print("=" * 70)

    features = create_features(df)

    print(
        f"Rows after feature creation: {len(features)}"
    )

    # -----------------------------------------------------
    # Validate generated features
    # -----------------------------------------------------

    feature_columns = validate_features(features)

    # -----------------------------------------------------
    # Remove rows that cannot be used for modeling
    # -----------------------------------------------------

    model_columns = feature_columns + ["target_next_hour"]

    before_drop = len(features)

    model_data = (
        features
        .dropna(subset=model_columns)
        .reset_index(drop=True)
    )

    after_drop = len(model_data)

    print()
    print("=" * 70)
    print("MODEL DATASET")
    print("=" * 70)

    print(f"Rows before filtering: {before_drop}")
    print(f"Rows after filtering:  {after_drop}")
    print(f"Rows removed:          {before_drop - after_drop}")

    # -----------------------------------------------------
    # Final validation
    # -----------------------------------------------------

    print()
    print("Final missing values in model columns:")

    final_missing = (
        model_data[model_columns]
        .isna()
        .sum()
        .sum()
    )

    print(final_missing)

    if final_missing != 0:
        raise ValueError(
            "Model dataset still contains missing "
            "feature/target values."
        )

    duplicate_count = (
        model_data
        .duplicated(
            subset=["station_id", "timestamp"]
        )
        .sum()
    )

    print()
    print(
        f"Duplicate station/timestamp rows: "
        f"{duplicate_count}"
    )

    if duplicate_count != 0:
        raise ValueError(
            "Duplicate station/timestamp rows "
            "found in model dataset."
        )

    # -----------------------------------------------------
    # Station coverage
    # -----------------------------------------------------

    print()
    print("--- Rows per Station ---")

    station_counts = model_data.groupby("station_id").size()
    print(station_counts.to_string())

    print(
        f"Stations in model dataset: "
        f"{model_data['station_id'].nunique()}"
    )

    # -----------------------------------------------------
    # Data-quality distribution
    # -----------------------------------------------------

    print()
    print("--- Data Quality Distribution ---")

    print(
        model_data["data_quality"]
        .value_counts()
        .to_string()
    )

    # -----------------------------------------------------
    # Feature preview
    # -----------------------------------------------------

    preview_columns = [
        "station_id",
        "timestamp",
        "value",
        "value_imputed",
        "is_imputed",
        "data_quality",
        "lag_1",
        "lag_6",
        "lag_24",
        "lag_72",
        "rolling_mean_6",
        "rolling_mean_24",
        "rolling_mean_72",
        "rolling_std_24",
        "change_1",
        "target_next_hour",
    ]

    print()
    print("--- Feature Preview ---")

    print(
        model_data[preview_columns]
        .head(15)
        .to_string(index=False)
    )

    # -----------------------------------------------------
    # Save
    # -----------------------------------------------------

    model_data.to_csv(
        OUTPUT_FILE,
        index=False,
    )

    print()
    print("=" * 70)
    print("FEATURE ENGINEERING COMPLETE")
    print("=" * 70)

    print(f"Output file: {OUTPUT_FILE}")
    print(f"Output rows: {len(model_data)}")
    print(
        f"Output stations: "
        f"{model_data['station_id'].nunique()}"
    )


# =========================================================
# Run
# =========================================================

if __name__ == "__main__":
    main()
