from pathlib import Path

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values


# =========================================================
# Configuration
# =========================================================

BASE_DIR = Path(__file__).resolve().parents[2]

INPUT_FILE = (
    BASE_DIR
    / "data"
    / "processed"
    / "weather"
    / "vietnam_weather_grid_500_hourly.csv"
)

SOURCE = "open_meteo_historical"

CHUNK_SIZE = 10_000


# =========================================================
# Database connection
# =========================================================

def get_connection():
    return psycopg2.connect(
        host="localhost",
        port=5432,
        dbname="weather_forecasting",
        user="postgres",
    )


# =========================================================
# Main
# =========================================================

def main():

    print("=" * 70)
    print("WEATHER DATA -> POSTGRESQL IMPORT")
    print("=" * 70)

    print(f"Input file: {INPUT_FILE}")

    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Weather CSV not found:\n{INPUT_FILE}"
        )

    # -----------------------------------------------------
    # Read CSV
    # -----------------------------------------------------

    print("\nReading weather dataset...")

    df = pd.read_csv(INPUT_FILE)

    print(f"Rows loaded: {len(df):,}")
    print(f"Columns: {list(df.columns)}")

    # -----------------------------------------------------
    # Validate source CSV columns
    # -----------------------------------------------------

    required_csv_columns = [
        "location_id",
        "latitude",
        "longitude",
        "timestamp",
        "temperature_2m",
        "relative_humidity_2m",
        "dew_point_2m",
        "precipitation",
        "rain",
        "pressure_msl",
        "surface_pressure",
        "cloud_cover",
        "wind_speed_10m",
        "wind_direction_10m",
        "wind_gusts_10m",
    ]

    missing_columns = [
        column
        for column in required_csv_columns
        if column not in df.columns
    ]

    if missing_columns:
        raise ValueError(
            f"Missing required CSV columns: {missing_columns}"
        )

    # -----------------------------------------------------
    # Keep all weather fields required by PostgreSQL
    # -----------------------------------------------------

    df = df[
        [
            "location_id",
            "latitude",
            "longitude",
            "timestamp",
            "temperature_2m",
            "relative_humidity_2m",
            "dew_point_2m",
            "precipitation",
            "rain",
            "pressure_msl",
            "surface_pressure",
            "cloud_cover",
            "wind_speed_10m",
            "wind_direction_10m",
            "wind_gusts_10m",
        ]
    ].copy()

    # -----------------------------------------------------
    # Rename CSV fields to PostgreSQL fields
    # -----------------------------------------------------

    df = df.rename(
        columns={
            "location_id": "location_code",
            "precipitation": "precipitation_mm",
            "surface_pressure": "surface_pressure_hpa",
        }
    )

    # -----------------------------------------------------
    # Parse timestamp
    # -----------------------------------------------------

    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        errors="coerce",
    )

    # -----------------------------------------------------
    # Convert numeric fields
    # -----------------------------------------------------

    numeric_columns = [
        "temperature_2m",
        "relative_humidity_2m",
        "dew_point_2m",
        "precipitation_mm",
        "rain",
        "pressure_msl",
        "surface_pressure_hpa",
        "cloud_cover",
        "wind_speed_10m",
        "wind_direction_10m",
        "wind_gusts_10m",
        "latitude",
        "longitude",
    ]

    for column in numeric_columns:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    # -----------------------------------------------------
    # Remove rows with missing identifiers
    # -----------------------------------------------------

    before = len(df)

    df = df.dropna(
        subset=[
            "location_code",
            "timestamp",
        ]
    )

    removed = before - len(df)

    if removed > 0:
        print(
            f"Removed rows with missing identifiers: "
            f"{removed:,}"
        )

    # -----------------------------------------------------
    # Remove duplicate location/timestamp rows
    # -----------------------------------------------------

    before = len(df)

    df = df.drop_duplicates(
        subset=[
            "location_code",
            "timestamp",
        ],
        keep="last",
    )

    duplicates_removed = before - len(df)

    print(
        f"Duplicate location/timestamp rows removed: "
        f"{duplicates_removed:,}"
    )

    # -----------------------------------------------------
    # Dataset summary
    # -----------------------------------------------------

    print("\nDataset summary:")
    print(f"Rows to import : {len(df):,}")
    print(
        f"Locations      : "
        f"{df['location_code'].nunique():,}"
    )
    print(
        f"Time range     : "
        f"{df['timestamp'].min()} -> "
        f"{df['timestamp'].max()}"
    )

    # -----------------------------------------------------
    # Connect to PostgreSQL
    # -----------------------------------------------------

    print("\nConnecting to PostgreSQL...")

    conn = get_connection()
    cur = conn.cursor()

    print("Connected successfully.")

    # -----------------------------------------------------
    # Insert / update SQL
    # -----------------------------------------------------

    insert_sql = """
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
            longitude,
            dew_point_2m,
            rain,
            pressure_msl,
            wind_direction_10m,
            wind_gusts_10m
        )
        VALUES %s
        ON CONFLICT (location_code, timestamp)
        DO UPDATE SET
            temperature_2m = EXCLUDED.temperature_2m,
            precipitation_mm = EXCLUDED.precipitation_mm,
            relative_humidity_2m = EXCLUDED.relative_humidity_2m,
            surface_pressure_hpa = EXCLUDED.surface_pressure_hpa,
            wind_speed_10m = EXCLUDED.wind_speed_10m,
            cloud_cover = EXCLUDED.cloud_cover,
            latitude = EXCLUDED.latitude,
            longitude = EXCLUDED.longitude,
            dew_point_2m = EXCLUDED.dew_point_2m,
            rain = EXCLUDED.rain,
            pressure_msl = EXCLUDED.pressure_msl,
            wind_direction_10m = EXCLUDED.wind_direction_10m,
            wind_gusts_10m = EXCLUDED.wind_gusts_10m
    """

    # -----------------------------------------------------
    # Import in chunks
    # -----------------------------------------------------

    total_rows = len(df)
    imported_rows = 0

    print("\nStarting PostgreSQL import...")
    print(f"Chunk size: {CHUNK_SIZE:,}")
    print(f"Total rows: {total_rows:,}")
    print()

    try:

        for start in range(
            0,
            total_rows,
            CHUNK_SIZE,
        ):

            end = min(
                start + CHUNK_SIZE,
                total_rows,
            )

            chunk = df.iloc[start:end]

            values = [
                (
                    row.location_code,
                    row.timestamp.to_pydatetime(),
                    row.temperature_2m,
                    row.precipitation_mm,
                    row.relative_humidity_2m,
                    row.surface_pressure_hpa,
                    row.wind_speed_10m,
                    row.cloud_cover,
                    row.latitude,
                    row.longitude,
                    row.dew_point_2m,
                    row.rain,
                    row.pressure_msl,
                    row.wind_direction_10m,
                    row.wind_gusts_10m,
                )
                for row in chunk.itertuples(
                    index=False
                )
            ]

            execute_values(
                cur,
                insert_sql,
                values,
                page_size=CHUNK_SIZE,
            )

            conn.commit()

            imported_rows += len(chunk)

            percentage = (
                imported_rows / total_rows * 100
                if total_rows
                else 100
            )

            print(
                f"Chunk "
                f"{start // CHUNK_SIZE + 1:>3} | "
                f"{imported_rows:>10,} / "
                f"{total_rows:,} "
                f"({percentage:6.2f}%)"
            )

    except Exception:

        conn.rollback()

        print("\nERROR: Import failed.")
        print("Current transaction rolled back.")

        raise

    finally:

        cur.close()
        conn.close()

    # -----------------------------------------------------
    # Complete
    # -----------------------------------------------------

    print("\n" + "=" * 70)
    print("WEATHER IMPORT COMPLETE")
    print("=" * 70)

    print(f"Rows processed : {total_rows:,}")
    print(f"Rows imported  : {imported_rows:,}")
    print(
        f"Locations      : "
        f"{df['location_code'].nunique():,}"
    )
    print(
        f"Time range     : "
        f"{df['timestamp'].min()} -> "
        f"{df['timestamp'].max()}"
    )
    print(f"Source         : {SOURCE}")

    print("=" * 70)


if __name__ == "__main__":
    main()