import os
from pathlib import Path

import pandas as pd
import psycopg2


DB_CONFIG = {
    "dbname": "weather_forecasting",
    "user": "postgres",
    "host": "localhost",
    "port": 5432,
    "password": os.environ["PGPASSWORD"],
}

DATA_DIR = Path("data/processed/weather")


def main():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    files = sorted(DATA_DIR.glob("weather_*.csv"))

    print(f"Found {len(files)} weather files.")

    total_rows = 0

    for file in files:
        location_code = file.stem.replace("weather_", "")
        df = pd.read_csv(file)

        print(f"Loading {location_code}: {len(df)} rows")

        for _, row in df.iterrows():
            cur.execute(
                """
                INSERT INTO weather_observations (
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
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (location_code, timestamp) DO UPDATE SET
                    temperature_2m = EXCLUDED.temperature_2m,
                    precipitation_mm = EXCLUDED.precipitation_mm,
                    relative_humidity_2m = EXCLUDED.relative_humidity_2m,
                    surface_pressure_hpa = EXCLUDED.surface_pressure_hpa,
                    wind_speed_10m = EXCLUDED.wind_speed_10m,
                    cloud_cover = EXCLUDED.cloud_cover,
                    latitude = EXCLUDED.latitude,
                    longitude = EXCLUDED.longitude
                """,
                (
                    location_code,
                    row["timestamp"],
                    row.get("temperature_2m"),
                    row.get("precipitation"),
                    row.get("relative_humidity_2m"),
                    row.get("surface_pressure"),
                    row.get("wind_speed_10m"),
                    row.get("cloud_cover"),
                    row.get("latitude"),
                    row.get("longitude"),
                ),
            )

        total_rows += len(df)

    conn.commit()

    cur.execute("SELECT COUNT(*) FROM weather_observations")
    db_count = cur.fetchone()[0]

    print()
    print(f"Rows processed: {total_rows}")
    print(f"Weather rows in PostgreSQL: {db_count}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()