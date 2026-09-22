import pandas as pd


INPUT_FILE = "data/processed/historical_all_stations.csv"
OUTPUT_FILE = "data/processed/forecast_features.csv"


def create_features(df):

    # Make sure data is sorted correctly
    df = (
        df
        .sort_values(["station_id", "timestamp"])
        .reset_index(drop=True)
    )

    # Create time-based features
    df["hour"] = df["timestamp"].dt.hour
    df["day_of_week"] = df["timestamp"].dt.dayofweek
    df["day_of_month"] = df["timestamp"].dt.day

    # Previous observations
    df["lag_1"] = (
        df.groupby("station_id")["value"]
        .shift(1)
    )

    df["lag_3"] = (
        df.groupby("station_id")["value"]
        .shift(3)
    )

    df["lag_6"] = (
        df.groupby("station_id")["value"]
        .shift(6)
    )

    df["lag_12"] = (
        df.groupby("station_id")["value"]
        .shift(12)
    )

    df["lag_24"] = (
        df.groupby("station_id")["value"]
        .shift(24)
    )

    # Rolling statistics
    df["rolling_mean_3"] = (
        df.groupby("station_id")["value"]
        .transform(
            lambda x: x.shift(1).rolling(3).mean()
        )
    )

    df["rolling_mean_6"] = (
        df.groupby("station_id")["value"]
        .transform(
            lambda x: x.shift(1).rolling(6).mean()
        )
    )

    df["rolling_mean_24"] = (
        df.groupby("station_id")["value"]
        .transform(
            lambda x: x.shift(1).rolling(24).mean()
        )
    )

    # Target = next hour's value
    df["target_next_hour"] = (
        df.groupby("station_id")["value"]
        .shift(-1)
    )

    return df


def main():

    print("Loading historical dataset...")

    df = pd.read_csv(
        INPUT_FILE,
        parse_dates=["timestamp"]
    )

    print(f"Input rows: {len(df)}")

    features = create_features(df)

    print()
    print("=" * 60)
    print("FEATURE ENGINEERING")
    print("=" * 60)

    print(f"Rows before dropping NaN: {len(features)}")

    # Display columns
    print()
    print("--- Columns ---")

    print(features.columns.tolist())

    # Remove rows where lag/rolling/target values
    # cannot be calculated
    model_data = features.dropna().reset_index(drop=True)

    print()
    print(f"Rows after dropping NaN: {len(model_data)}")

    print()
    print("--- Missing Values ---")

    print(model_data.isna().sum())

    print()
    print("--- Rows by Station ---")

    print(
        model_data.groupby("station_id").size()
    )

    print()
    print("--- Feature Preview ---")

    print(
        model_data[
            [
                "station_id",
                "timestamp",
                "value",
                "lag_1",
                "lag_3",
                "lag_6",
                "lag_12",
                "lag_24",
                "rolling_mean_3",
                "rolling_mean_6",
                "rolling_mean_24",
                "target_next_hour",
            ]
        ]
        .head(10)
        .to_string(index=False)
    )

    # Save
    model_data.to_csv(
        OUTPUT_FILE,
        index=False
    )

    print()
    print(f"Saved to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()