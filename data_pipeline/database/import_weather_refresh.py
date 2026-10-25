
import argparse
import os
from pathlib import Path

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values


BASE_DIR = Path(__file__).resolve().parents[2]

INPUT_FILE = (
    BASE_DIR
    / "data"
    / "processed"
    / "weather"
    / "vietnam_weather_grid_500_hourly_2026-10-16.csv"
)

CHUNK_SIZE = 10_000

CSV_COLUMNS = [
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

NUMERIC_COLUMNS = [
    "latitude",
    "longitude",
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

DB_COLUMNS = [
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
]

INSERT_SQL = """
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


def prepare_chunk(chunk, chunk_number):
    missing_columns = sorted(set(CSV_COLUMNS) - set(chunk.columns))

    if missing_columns:
        raise ValueError(
            f"Chunk {chunk_number}: missing columns {missing_columns}"
        )

    chunk = chunk[CSV_COLUMNS].copy()

    chunk["location_id"] = (
        chunk["location_id"].astype("string").str.strip()
    )

    chunk["timestamp"] = pd.to_datetime(
        chunk["timestamp"],
        errors="coerce",
    )

    for column in NUMERIC_COLUMNS:
        chunk[column] = pd.to_numeric(
            chunk[column],
            errors="coerce",
        )

    if (
        chunk["location_id"].isna().any()
        or chunk["location_id"].eq("").any()
    ):
        raise ValueError(
            f"Chunk {chunk_number}: missing location IDs."
        )

    if chunk["timestamp"].isna().any():
        raise ValueError(
            f"Chunk {chunk_number}: invalid timestamps."
        )

    if chunk.duplicated(["location_id", "timestamp"]).any():
        raise ValueError(
            f"Chunk {chunk_number}: duplicate location/timestamp keys."
        )

    if chunk[["latitude", "longitude"]].isna().any().any():
        raise ValueError(
            f"Chunk {chunk_number}: missing coordinates."
        )

    chunk = chunk.rename(
        columns={
            "location_id": "location_code",
            "precipitation": "precipitation_mm",
            "surface_pressure": "surface_pressure_hpa",
        }
    )

    # Critical fix: match the exact order of columns in INSERT_SQL.
    # The CSV places latitude and longitude before timestamp, while
    # the database INSERT expects timestamp in the second position.
    return chunk[DB_COLUMNS]


def make_values(chunk):
    values = []

    for row in chunk.itertuples(index=False, name=None):
        cleaned = []

        for value in row:
            if pd.isna(value):
                cleaned.append(None)
            elif isinstance(value, pd.Timestamp):
                cleaned.append(value.to_pydatetime())
            elif hasattr(value, "item"):
                cleaned.append(value.item())
            else:
                cleaned.append(value)

        values.append(tuple(cleaned))

    return values


def validate_summary(total_rows, locations, earliest, latest):
    if total_rows != 3_300_000:
        raise ValueError(
            f"Expected 3,300,000 rows, found {total_rows:,}."
        )

    if len(locations) != 500:
        raise ValueError(
            f"Expected 500 locations, found {len(locations)}."
        )

    expected_earliest = pd.Timestamp("2026-01-15 00:00:00")
    expected_latest = pd.Timestamp("2026-10-16 23:00:00")

    if earliest != expected_earliest:
        raise ValueError(
            f"Unexpected earliest timestamp: {earliest}"
        )

    if latest != expected_latest:
        raise ValueError(
            f"Unexpected latest timestamp: {latest}"
        )


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Validate and optionally import the refreshed "
            "historical weather CSV."
        )
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Write data to PostgreSQL. Without this flag, "
            "run a dry run."
        ),
    )

    args = parser.parse_args()

    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Input CSV not found: {INPUT_FILE}"
        )

    print("=" * 65)
    print("WEATHER REFRESH IMPORTER")
    print("=" * 65)
    print(f"Input: {INPUT_FILE}")
    print(f"Chunk size: {CHUNK_SIZE:,}")
    print(
        f"Mode: {'DATABASE WRITE' if args.apply else 'DRY RUN'}"
    )

    if not args.apply:
        print("No database changes will be made.")

    total_rows = 0
    total_chunks = 0
    locations = set()
    earliest = None
    latest = None

    conn = None

    try:
        if args.apply:
            conn = get_connection()
            print("Connected to PostgreSQL.")

        for chunk_number, chunk in enumerate(
            pd.read_csv(
                INPUT_FILE,
                chunksize=CHUNK_SIZE,
            ),
            start=1,
        ):
            chunk = prepare_chunk(chunk, chunk_number)

            total_rows += len(chunk)
            total_chunks += 1

            locations.update(
                chunk["location_code"].unique()
            )

            chunk_min = chunk["timestamp"].min()
            chunk_max = chunk["timestamp"].max()

            earliest = (
                chunk_min
                if earliest is None
                else min(earliest, chunk_min)
            )

            latest = (
                chunk_max
                if latest is None
                else max(latest, chunk_max)
            )

            if args.apply:
                values = make_values(chunk)

                with conn.cursor() as cur:
                    execute_values(
                        cur,
                        INSERT_SQL,
                        values,
                        page_size=CHUNK_SIZE,
                    )

            if total_chunks % 10 == 0:
                print(
                    f"Chunks: {total_chunks} | "
                    f"Rows checked: {total_rows:,} | "
                    f"Locations seen: {len(locations)}"
                )

        validate_summary(
            total_rows,
            locations,
            earliest,
            latest,
        )

        print("\nVALIDATION SUMMARY")
        print(f"Rows checked: {total_rows:,}")
        print(f"Chunks checked: {total_chunks}")
        print(f"Locations: {len(locations)}")
        print(f"Time range: {earliest} -> {latest}")

        if args.apply:
            # Keep all chunks in one transaction so a failed final
            # dataset-wide check cannot leave a partial import behind.
            conn.commit()
            print("\nIMPORT COMPLETE")
            print(
                "All input chunks were processed and committed."
            )
        else:
            print("\nDRY RUN PASSED")
            print(
                "No database rows were inserted or updated."
            )
            print(
                "Review the summary before running with --apply."
            )

    except Exception:
        if conn is not None:
            conn.rollback()

        print(
            "\nERROR: processing stopped. "
            "Review the error above."
        )
        raise

    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    main()
