import pandas as pd


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

    print()
    print("=" * 70)
    print("INPUT VALIDATION")
    print("=" * 70)

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

    # Timestamp validation
    if df["timestamp"].isna().any():
        raise ValueError(
            "Input contains missing timestamps."
        )

    # Duplicate validation
    duplicate_count = df.duplicated(
        subset=["station_id", "timestamp"]
    ).sum()

    if duplicate_count > 0:
        raise ValueError(
            f"Input contains {duplicate_count} "
            "duplicate station/timestamp rows."
        )

    # Station validation
    station_count = df["station_id"].nunique()

    # Row validation
    row_count = len(df)

    print(f"Rows: {row_count}")
    print(f"Stations: {station_count}")

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

    # Check original missing values
    original_missing = df["value"].isna().sum()

    # Check remaining ML value missing values
    imputed_missing = df["value_imputed"].isna().sum()

    print()
    print(
        f"Original value missing: {original_missing}"
    )

    print(
        f"value_imputed missing: {imputed_missing}"
    )

    return True


# =========================================================
# Feature Creation
# =========================================================

def create_features(df):
    """
    Create temporal forecasting features from the ML-ready
    hydrology dataset.

    value_imputed is used for forecasting features because
    short internal gaps have already been safely interpolated.

    The original value column is preserved.
    """

    df = (
        df
        .sort_values(
            ["station_id", "timestamp"]
        )
        .reset_index(drop=True)
        .copy()
    )

    # -----------------------------------------------------
    # Basic time features
    # -----------------------------------------------------

    df["hour"] = df["timestamp"].dt.hour

    df["day_of_week"] = (
        df["timestamp"].dt.dayofweek
    )

    df["day_of_month"] = (
        df["timestamp"].dt.day
    )

    # Additional cyclic time representation
    df["hour_sin"] = (
        __import__("numpy").sin(
            2
            * __import__("numpy").pi
            * df["hour"]
            / 24
        )
    )

    df["hour_cos"] = (
        __import__("numpy").cos(
            2
            * __import__("numpy").pi
            * df["hour"]
            / 24
        )
    )

    # -----------------------------------------------------
    # Base lag features
    # -----------------------------------------------------

    for lag in BASE_LAGS:

        df[f"lag_{lag}"] = (
            df.groupby("station_id")[
                "value_imputed"
            ]
            .shift(lag)
        )

    # -----------------------------------------------------
    # Enhanced lag features
    # -----------------------------------------------------

    for lag in ENHANCED_LAGS:

        df[f"lag_{lag}"] = (
            df.groupby("station_id")[
                "value_imputed"
            ]
            .shift(lag)
        )

    # -----------------------------------------------------
    # Base rolling means
    #
    # shift(1) prevents the current observation from
    # leaking into the feature.
    # -----------------------------------------------------

    for window in BASE_ROLLING_WINDOWS:

        df[f"rolling_mean_{window}"] = (
            df.groupby("station_id")[
                "value_imputed"
            ]
            .transform(
                lambda x:
                x.shift(1)
                .rolling(window)
                .mean()
            )
        )

    # -----------------------------------------------------
    # Enhanced rolling means
    # -----------------------------------------------------

    for window in ENHANCED_ROLLING_WINDOWS:

        df[f"rolling_mean_{window}"] = (
            df.groupby("station_id")[
                "value_imputed"
            ]
            .transform(
                lambda x:
                x.shift(1)
                .rolling(window)
                .mean()
            )
        )

    # -----------------------------------------------------
    # Short-term variability
    # -----------------------------------------------------

    df["rolling_std_6"] = (
        df.groupby("station_id")[
            "value_imputed"
        ]
        .transform(
            lambda x:
            x.shift(1)
            .rolling(6)
            .std()
        )
    )

    df["rolling_std_24"] = (
        df.groupby("station_id")[
            "value_imputed"
        ]
        .transform(
            lambda x:
            x.shift(1)
            .rolling(24)
            .std()
        )
    )

    # -----------------------------------------------------
    # Change features
    # -----------------------------------------------------

    df["change_1"] = (
        df["value_imputed"]
        - df["lag_1"]
    )

    df["change_3"] = (
        df["value_imputed"]
        - df["lag_3"]
    )

    df["change_6"] = (
        df["value_imputed"]
        - df["lag_6"]
    )

    # -----------------------------------------------------
    # Data quality features
    #
    # These are metadata/features describing whether the
    # current source value was interpolated.
    # -----------------------------------------------------

    df["is_imputed"] = (
        df["is_imputed"]
        .astype(int)
    )

    df["missing_run_hours"] = (
        pd.to_numeric(
            df["missing_run_hours"],
            errors="coerce"
        )
        .fillna(0)
    )

    # -----------------------------------------------------
    # Target
    #
    # Predict the next hour's water level.
    #
    # The target comes from value_imputed so that short
    # gaps handled by the ML-ready preparation remain usable.
    # Long gaps remain NaN and are excluded later.
    # -----------------------------------------------------

    df["target_next_hour"] = (
        df.groupby("station_id")[
            "value_imputed"
        ]
        .shift(-1)
    )

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

    print(
        missing_counts.to_string()
    )

    target_missing = (
        df["target_next_hour"]
        .isna()
        .sum()
    )

    print()
    print(
        f"Missing target_next_hour: "
        f"{target_missing}"
    )

    # Important: at this stage missing values are expected
    # at the beginning of lag windows and around long gaps.
    #
    # We do not silently fill them here.

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
        parse_dates=["timestamp"]
    )

    print(
        f"Loaded rows: {len(df)}"
    )

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

    print()
    print(
        f"Rows after feature creation: "
        f"{len(features)}"
    )

    # -----------------------------------------------------
    # Validate generated features
    # -----------------------------------------------------

    feature_columns = validate_features(
        features
    )

    # -----------------------------------------------------
    # Remove rows that cannot be used for modeling
    #
    # We only remove rows with missing MODEL FEATURES or
    # missing TARGET.
    #
    # The source dataset itself remains untouched.
    # -----------------------------------------------------

    model_columns = (
        feature_columns
        + ["target_next_hour"]
    )

    before_drop = len(features)

    model_data = (
        features
        .dropna(
            subset=model_columns
        )
        .reset_index(drop=True)
    )

    after_drop = len(model_data)

    print()
    print("=" * 70)
    print("MODEL DATASET")
    print("=" * 70)

    print(
        f"Rows before filtering: {before_drop}"
    )

    print(
        f"Rows after filtering:  {after_drop}"
    )

    print(
        f"Rows removed:          "
        f"{before_drop - after_drop}"
    )

    # -----------------------------------------------------
    # Final validation
    # -----------------------------------------------------

    print()
    print("Final missing values in model columns:")

    final_missing = (
        model_data[
            model_columns
        ]
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
            subset=[
                "station_id",
                "timestamp"
            ]
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

    station_counts = (
        model_data
        .groupby("station_id")
        .size()
    )

    print(
        station_counts.to_string()
    )

    print()
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
        model_data[
            "data_quality"
        ]
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
        model_data[
            preview_columns
        ]
        .head(15)
        .to_string(index=False)
    )

    # -----------------------------------------------------
    # Save
    # -----------------------------------------------------

    model_data.to_csv(
        OUTPUT_FILE,
        index=False
    )

    print()
    print("=" * 70)
    print("FEATURE ENGINEERING COMPLETE")
    print("=" * 70)

    print(
        f"Output file: {OUTPUT_FILE}"
    )

    print(
        f"Output rows: {len(model_data)}"
    )

    print(
        f"Output stations: "
        f"{model_data['station_id'].nunique()}"
    )


# =========================================================
# Run
# =========================================================

if __name__ == "__main__":
    main()