import os
from pathlib import Path

import pandas as pd
import psycopg2
from dotenv import load_dotenv


load_dotenv()


DB_CONFIG = {
    "dbname": "weather_forecasting",
    "user": "postgres",
    "host": "localhost",
    "port": 5432,
    "password": os.getenv("PGPASSWORD"),
}


OUTPUT_DIR = Path("data/processed/weather")
OUTPUT_FILE = OUTPUT_DIR / "rainfall_forecast_features.csv"


def load_weather_data():
    if not DB_CONFIG["password"]:
        raise RuntimeError(
            "PostgreSQL password not found. "
            "Set PGPASSWORD in the .env file."
        )

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

    df = df.sort_values(
        ["location_code", "timestamp"]
    )

    grouped = df.groupby(
        "location_code",
        group_keys=False,
    )

    # Time features
    df["hour"] = df["timestamp"].dt.hour
    df["day_of_week"] = df["timestamp"].dt.dayofweek
    df["day_of_month"] = df["timestamp"].dt.day
    df["month"] = df["timestamp"].dt.month
    df["day_of_year"] = df["timestamp"].dt.dayofyear

    # Rainfall lag features
    for lag in [1, 3, 6, 12, 24]:
        df[f"precipitation_lag_{lag}h"] = (
            grouped["precipitation_mm"].shift(lag)
        )

    # Other weather lag features
    for column in [
        "temperature_2m",
        "relative_humidity_2m",
        "surface_pressure_hpa",
        "wind_speed_10m",
        "cloud_cover",
    ]:
        df[f"{column}_lag_1h"] = (
            grouped[column].shift(1)
        )

    # Rainfall rolling statistics
    for window in [3, 6, 12, 24]:

        df[f"precipitation_rolling_sum_{window}h"] = (
            grouped["precipitation_mm"]
            .transform(
                lambda x: x.rolling(window).sum()
            )
        )

        df[f"precipitation_rolling_mean_{window}h"] = (
            grouped["precipitation_mm"]
            .transform(
                lambda x: x.rolling(window).mean()
            )
        )

    # Target: precipitation in the next hour
    df["target_next_hour"] = (
        grouped["precipitation_mm"].shift(-1)
    )

    df = df.dropna().reset_index(drop=True)

    return df


def main():
    print(
        "Loading weather observations from PostgreSQL..."
    )

    df = load_weather_data()

    print(f"Loaded rows: {len(df)}")
    print(
        f"Locations: {df['location_code'].nunique()}"
    )

    print()
    print(
        "Creating rainfall forecasting features..."
    )

    features = create_features(df)

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    features.to_csv(
        OUTPUT_FILE,
        index=False,
    )

    print()
    print(
        "Rainfall feature engineering complete."
    )
    print(
        f"Feature rows: {len(features)}"
    )
    print(
        f"Feature columns: {len(features.columns)}"
    )
    print(
        f"Saved to: {OUTPUT_FILE}"
    )

    print()
    print("Columns:")

    for column in features.columns:
        print(f"  - {column}")


if __name__ == "__main__":
    main()