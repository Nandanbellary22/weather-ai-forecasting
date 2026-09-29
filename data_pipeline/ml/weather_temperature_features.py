from pathlib import Path

import pandas as pd
import psycopg2


DB_CONFIG = {
    "dbname": "weather_forecasting",
    "user": "postgres",
    "host": "localhost",
    "port": 5432,
}


OUTPUT_DIR = Path("data/processed/weather")
OUTPUT_FILE = OUTPUT_DIR / "temperature_forecast_features.csv"


def load_weather_data():
    conn = psycopg2.connect(**DB_CONFIG)

    query = """
        SELECT
            location_code,
            timestamp,
            temperature_2m,
            precipitation_mm,
            relative_humidity_2m,
            surface_pressure_hpa,
            wind_speed_10m,
            cloud_cover,
            latitude,
            longitude
        FROM weather_observations
        ORDER BY location_code, timestamp
    """

    df = pd.read_sql_query(query, conn)
    conn.close()

    return df


def create_features(df):
    df = df.copy()

    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values(["location_code", "timestamp"])

    grouped = df.groupby("location_code", group_keys=False)

    # ---------------------------------------------------------
    # Time features
    # ---------------------------------------------------------
    df["hour"] = df["timestamp"].dt.hour
    df["day_of_week"] = df["timestamp"].dt.dayofweek
    df["day_of_month"] = df["timestamp"].dt.day
    df["month"] = df["timestamp"].dt.month
    df["day_of_year"] = df["timestamp"].dt.dayofyear

    # ---------------------------------------------------------
    # Temperature lags
    # Same lag structure used in the hydrology workflow
    # ---------------------------------------------------------
    for lag in [1, 3, 6, 12, 24]:
        df[f"temperature_lag_{lag}h"] = grouped["temperature_2m"].shift(lag)

    # ---------------------------------------------------------
    # Weather-variable lags
    # ---------------------------------------------------------
    for column in [
        "precipitation_mm",
        "relative_humidity_2m",
        "surface_pressure_hpa",
        "wind_speed_10m",
        "cloud_cover",
    ]:
        df[f"{column}_lag_1h"] = grouped[column].shift(1)

    # ---------------------------------------------------------
    # Rolling temperature means
    # ---------------------------------------------------------
    for window in [3, 6, 24]:
        df[f"temperature_rolling_mean_{window}h"] = (
            grouped["temperature_2m"]
            .transform(lambda x: x.rolling(window).mean())
        )

    # ---------------------------------------------------------
    # Target: next-hour temperature
    # ---------------------------------------------------------
    df["target_next_hour"] = grouped["temperature_2m"].shift(-1)

    # Remove rows created by lags/target
    df = df.dropna().reset_index(drop=True)

    return df


def main():
    print("Loading weather observations from PostgreSQL...")

    df = load_weather_data()

    print(f"Loaded rows: {len(df)}")
    print(f"Locations: {df['location_code'].nunique()}")

    print("Creating temperature forecasting features...")

    features = create_features(df)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    features.to_csv(OUTPUT_FILE, index=False)

    print()
    print("Feature engineering complete.")
    print(f"Feature rows: {len(features)}")
    print(f"Feature columns: {len(features.columns)}")
    print(f"Saved to: {OUTPUT_FILE}")

    print()
    print("Columns:")
    for column in features.columns:
        print(f"  - {column}")


if __name__ == "__main__":
    main()