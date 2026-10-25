
import os
from pathlib import Path

import pandas as pd
import psycopg2


BASE_DIR = Path(__file__).resolve().parents[1]
STAGING_DIR = (
    BASE_DIR
    / "data"
    / "processed"
    / "weather_refresh_staging_2026-07-14_to_2026-10-21"
)

def get_connection():
    password = (
        os.environ.get("PGPASSWORD")
        or os.environ.get("POSTGRES_PASSWORD")
    )
    return psycopg2.connect(
        host="localhost",
        port=5432,
        dbname="weather_forecasting",
        user="postgres",
        password=password,
    )


def main():
    print("Loading and validating staged files...")
    files = sorted(STAGING_DIR.glob("weather_*.csv"))

    if len(files) != 500:
        raise ValueError(f"Expected 500 files, found {len(files)}")

    columns = [
        "location_id",
        "timestamp",
        "temperature_2m",
        "precipitation",
        "relative_humidity_2m",
        "surface_pressure",
        "wind_speed_10m",
        "cloud_cover",
        "latitude",
        "longitude",
        "dew_point_2m",
        "rain",
        "pressure_msl",
        "wind_direction_10m",
        "wind_gusts_10m",
    ]

    frames = []
    for path in files:
        df = pd.read_csv(path, usecols=columns)
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="raise")
        frames.append(df)

    staged = pd.concat(frames, ignore_index=True)
    staged = staged.rename(
        columns={
            "location_id": "location_code",
            "precipitation": "precipitation_mm",
            "surface_pressure": "surface_pressure_hpa",
        }
    )

    if staged.duplicated(["location_code", "timestamp"]).any():
        raise ValueError("Duplicate staged location/timestamp keys found")

    print(f"Staged rows: {len(staged):,}")
    print("Connecting to PostgreSQL in read-only mode...")

    conn = get_connection()
    try:
        conn.set_session(readonly=True, autocommit=False)
        with conn.cursor() as cur:
            cur.execute(
                """
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
                    longitude,
                    dew_point_2m,
                    rain,
                    pressure_msl,
                    wind_direction_10m,
                    wind_gusts_10m
                FROM weather_observations
                WHERE timestamp >= %s
                  AND timestamp <= %s
                """,
                (
                    pd.Timestamp("2026-07-14 00:00:00").to_pydatetime(),
                    pd.Timestamp("2026-10-21 23:00:00").to_pydatetime(),
                ),
            )
            existing = pd.DataFrame(cur.fetchall(), columns=[
                "location_code",
                "timestamp",
                "temperature_2m",
                "precipitation_mm",
                "relative_humidity_2m",
                "surface_pressure_hpa",
                "wind_speed_10m",
                "cloud_cover",
                "latitude",
                "longitude",
                "dew_point_2m",
                "rain",
                "pressure_msl",
                "wind_direction_10m",
                "wind_gusts_10m",
            ])
    finally:
        conn.rollback()
        conn.close()

    print(f"Existing rows in period: {len(existing):,}")

    key = ["location_code", "timestamp"]
    merged = staged.merge(
        existing,
        on=key,
        how="outer",
        suffixes=("_staged", "_db"),
        indicator=True,
    )

    print("\nKey coverage:")
    print(merged["_merge"].value_counts().to_string())

    fields = [
        "temperature_2m",
        "precipitation_mm",
        "relative_humidity_2m",
        "surface_pressure_hpa",
        "wind_speed_10m",
        "cloud_cover",
        "latitude",
        "longitude",
        "dew_point_2m",
        "rain",
        "pressure_msl",
        "wind_direction_10m",
        "wind_gusts_10m",
    ]

    both = merged[merged["_merge"] == "both"]
    print("\nField comparison (different values, including NULL differences):")
    total_differences = 0
    for field in fields:
        left = both[f"{field}_staged"]
        right = both[f"{field}_db"]
        equal = left.eq(right) | (left.isna() & right.isna())
        count = int((~equal).sum())
        total_differences += count
        print(f"{field}: {count:,} differing rows")

    print(f"\nTotal field-level differences: {total_differences:,}")
    print("READ-ONLY COMPARISON COMPLETE. No database rows were modified.")


if __name__ == "__main__":
    main()
