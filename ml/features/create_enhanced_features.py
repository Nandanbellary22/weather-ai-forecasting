import pandas as pd


# =========================================================
# Configuration
# =========================================================

INPUT_FILE = "data/processed/historical_90days_all_stations.csv"
OUTPUT_FILE = "data/processed/enhanced_forecast_features.csv"


# =========================================================
# Main
# =========================================================

def main():

    print("=" * 70)
    print("CREATING ENHANCED TEMPORAL FEATURES")
    print("=" * 70)

    # -----------------------------------------------------
    # Load data
    # -----------------------------------------------------

    df = pd.read_csv(INPUT_FILE)

    df["timestamp"] = pd.to_datetime(
        df["timestamp"]
    )

    # -----------------------------------------------------
    # Sort by station and time
    # -----------------------------------------------------

    df = df.sort_values(
        ["station_id", "timestamp"]
    ).reset_index(drop=True)

    print(f"\nInput rows: {len(df)}")
    print(
        f"Stations: "
        f"{df['station_id'].unique().tolist()}"
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

    # -----------------------------------------------------
    # Existing lag features
    # -----------------------------------------------------

    existing_lags = [
        1,
        3,
        6,
        12,
        24,
    ]

    for lag in existing_lags:

        df[f"lag_{lag}"] = (
            df.groupby("station_id")["value"]
            .shift(lag)
        )

    # -----------------------------------------------------
    # NEW temporal lag features
    # -----------------------------------------------------

    enhanced_lags = [
        2,
        4,
        8,
        18,
        36,
        48,
        72,
    ]

    for lag in enhanced_lags:

        df[f"lag_{lag}"] = (
            df.groupby("station_id")["value"]
            .shift(lag)
        )

    # -----------------------------------------------------
    # Existing rolling means
    #
    # shift(1) prevents the current value from leaking
    # into the rolling feature.
    # -----------------------------------------------------

    existing_windows = [
        3,
        6,
        24,
    ]

    for window in existing_windows:

        df[f"rolling_mean_{window}"] = (
            df.groupby("station_id")["value"]
            .transform(
                lambda x:
                x.shift(1)
                .rolling(window)
                .mean()
            )
        )

    # -----------------------------------------------------
    # NEW rolling windows
    # -----------------------------------------------------

    enhanced_windows = [
        12,
        48,
        72,
    ]

    for window in enhanced_windows:

        df[f"rolling_mean_{window}"] = (
            df.groupby("station_id")["value"]
            .transform(
                lambda x:
                x.shift(1)
                .rolling(window)
                .mean()
            )
        )

    # -----------------------------------------------------
    # Target
    #
    # Predict the next hour's value.
    # -----------------------------------------------------

    df["target_next_hour"] = (
        df.groupby("station_id")["value"]
        .shift(-1)
    )

    # -----------------------------------------------------
    # Remove rows with unavailable lag/rolling values
    # -----------------------------------------------------

    before_drop = len(df)

    df = df.dropna().reset_index(drop=True)

    after_drop = len(df)

    print(
        f"\nRows before dropping NaN: "
        f"{before_drop}"
    )

    print(
        f"Rows after dropping NaN: "
        f"{after_drop}"
    )

    # -----------------------------------------------------
    # Check missing values
    # -----------------------------------------------------

    missing_values = df.isna().sum().sum()

    print(
        f"Missing values remaining: "
        f"{missing_values}"
    )

    # -----------------------------------------------------
    # Display columns
    # -----------------------------------------------------

    print("\nGenerated columns:")

    for column in df.columns:

        print(f"- {column}")

    # -----------------------------------------------------
    # Station counts
    # -----------------------------------------------------

    print("\nRows per station:")

    print(
        df.groupby("station_id").size()
    )

    # -----------------------------------------------------
    # Save
    # -----------------------------------------------------

    df.to_csv(
        OUTPUT_FILE,
        index=False
    )

    print("\nEnhanced feature dataset saved to:")

    print(OUTPUT_FILE)


# =========================================================
# Run
# =========================================================

if __name__ == "__main__":
    main()