from pathlib import Path
import pandas as pd


INPUT_FILE = Path("data/processed/historical_90days_all_stations.csv")
OUTPUT_FILE = Path("data/processed/forecast_features_90days.csv")


def create_features(df):
    df = df.copy()

    # Make sure data is correctly ordered
    df = df.sort_values(
        ["station_id", "timestamp"]
    ).reset_index(drop=True)

    # Time-based features
    df["hour"] = df["timestamp"].dt.hour
    df["day_of_week"] = df["timestamp"].dt.dayofweek
    df["day_of_month"] = df["timestamp"].dt.day

    # Lag features
    df["lag_1"] = df.groupby("station_id")["value"].shift(1)
    df["lag_3"] = df.groupby("station_id")["value"].shift(3)
    df["lag_6"] = df.groupby("station_id")["value"].shift(6)
    df["lag_12"] = df.groupby("station_id")["value"].shift(12)
    df["lag_24"] = df.groupby("station_id")["value"].shift(24)

    # Rolling mean features
    df["rolling_mean_3"] = (
        df.groupby("station_id")["value"]
        .transform(lambda x: x.shift(1).rolling(3).mean())
    )

    df["rolling_mean_6"] = (
        df.groupby("station_id")["value"]
        .transform(lambda x: x.shift(1).rolling(6).mean())
    )

    df["rolling_mean_24"] = (
        df.groupby("station_id")["value"]
        .transform(lambda x: x.shift(1).rolling(24).mean())
    )

    # Target: next-hour value
    df["target_next_hour"] = (
        df.groupby("station_id")["value"].shift(-1)
    )

    # Remove rows where lag/rolling/target values are unavailable
    df = df.dropna().reset_index(drop=True)

    return df


def main():
    print(f"Loading: {INPUT_FILE}")

    df = pd.read_csv(INPUT_FILE)

    df["station_id"] = df["station_id"].astype(str)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")

    print(f"Input rows: {len(df)}")

    features = create_features(df)

    print(f"Rows after dropping NaN: {len(features)}")

    print("\nRows per station:")
    print(features.groupby("station_id").size())

    print("\nMissing values:")
    print(features.isna().sum())

    print("\nFeature columns:")
    print(list(features.columns))

    print("\nFirst 5 rows:")
    print(features.head())

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    features.to_csv(OUTPUT_FILE, index=False)

    print(f"\nSaved: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()