import os
import sys
from pathlib import Path

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values


BASE_DIR = Path(__file__).resolve().parents[1]
STAGING_DIR = Path(
    os.environ.get(
        "WEATHER_STAGING_DIR",
        str(
            BASE_DIR
            / "data"
            / "processed"
            / "weather_refresh_staging_2026-07-14_to-2026-10-21"
        ),
    )
)

EXPECTED_FILES = 500
EXPECTED_ROWS_PER_FILE = 2400
EXPECTED_TOTAL_ROWS = EXPECTED_FILES * EXPECTED_ROWS_PER_FILE
EXPECTED_START = pd.Timestamp("2026-07-14 00:00:00")
EXPECTED_END = pd.Timestamp("2026-10-21 23:00:00")

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


def read_and_validate_file(path):
    df = pd.read_csv(path)

    missing = sorted(set(CSV_COLUMNS) - set(df.columns))
    if missing:
        raise ValueError(f"{path.name}: missing columns {missing}")

    df = df[CSV_COLUMNS].copy()
    df["location_id"] = df["location_id"].astype("string").str.strip()

    if len(df) != EXPECTED_ROWS_PER_FILE:
        raise ValueError(
            f"{path.name}: expected {EXPECTED_ROWS_PER_FILE:,} rows, "
            f"found {len(df):,}"
        )

    if (
        df["location_id"].isna().any()
        or df["location_id"].eq("").any()
    ):
        raise ValueError(f"{path.name}: missing location IDs")

    location_ids = df["location_id"].unique()
    if len(location_ids) != 1:
        raise ValueError(
            f"{path.name}: expected one location ID, found {len(location_ids)}"
        )

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    if df["timestamp"].isna().any():
        raise ValueError(f"{path.name}: invalid timestamps")

    if df["timestamp"].duplicated().any():
        raise ValueError(f"{path.name}: duplicate timestamps")

    df = df.sort_values("timestamp").reset_index(drop=True)

    if df["timestamp"].iloc[0] != EXPECTED_START:
        raise ValueError(
            f"{path.name}: unexpected first timestamp "
            f"{df['timestamp'].iloc[0]}"
        )

    if df["timestamp"].iloc[-1] != EXPECTED_END:
        raise ValueError(
            f"{path.name}: unexpected last timestamp "
            f"{df['timestamp'].iloc[-1]}"
        )

    expected_times = pd.date_range(
        EXPECTED_START,
        EXPECTED_END,
        freq="h",
    )
    if not df["timestamp"].reset_index(drop=True).equals(
        pd.Series(expected_times, name="timestamp")
    ):
        raise ValueError(f"{path.name}: timestamps are not a complete hourly series")

    for column in NUMERIC_COLUMNS:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    if df[["latitude", "longitude"]].isna().any().any():
        raise ValueError(f"{path.name}: missing coordinates")

    df = df.rename(
        columns={
            "location_id": "location_code",
            "precipitation": "precipitation_mm",
            "surface_pressure": "surface_pressure_hpa",
        }
    )

    return df[DB_COLUMNS]


def make_values(df):
    values = []
    for row in df.itertuples(index=False, name=None):
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


def main():
    if not STAGING_DIR.is_dir():
        raise FileNotFoundError(f"Staging directory not found: {STAGING_DIR}")

    files = sorted(STAGING_DIR.glob("weather_*.csv"))
    if len(files) != EXPECTED_FILES:
        raise ValueError(
            f"Expected {EXPECTED_FILES} staging CSVs, found {len(files)} "
            f"in {STAGING_DIR}"
        )

    print("=" * 70)
    print("OCTOBER 21 WEATHER REFRESH IMPORT")
    print("=" * 70)
    print(f"Staging directory: {STAGING_DIR}")
    print(f"Files: {len(files)}")
    print(f"Expected rows: {EXPECTED_TOTAL_ROWS:,}")
    print(f"Expected time range: {EXPECTED_START} -> {EXPECTED_END}")
    print("\nPhase 1/2: validating all files before database changes...")

    locations = set()
    total_rows = 0

    for index, path in enumerate(files, start=1):
        df = read_and_validate_file(path)
        location = str(df["location_code"].iloc[0])

        if location in locations:
            raise ValueError(
                f"Duplicate location ID {location!r}; check {path.name}"
            )

        locations.add(location)
        total_rows += len(df)

        if index % 50 == 0 or index == len(files):
            print(f"Validated {index}/{len(files)} files")

    if len(locations) != EXPECTED_FILES:
        raise ValueError(f"Expected 500 unique locations, found {len(locations)}")

    if total_rows != EXPECTED_TOTAL_ROWS:
        raise ValueError(
            f"Expected {EXPECTED_TOTAL_ROWS:,} rows, found {total_rows:,}"
        )

    print("\nValidation passed.")
    print(f"Locations: {len(locations)}")
    print(f"Rows: {total_rows:,}")
    print("\nPhase 2/2: importing in a single database transaction...")

    conn = None
    imported_rows = 0

    try:
        conn = get_connection()
        conn.autocommit = False

        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM weather_observations LIMIT 1")
        print("Connected to PostgreSQL; target table exists.")

        for index, path in enumerate(files, start=1):
            df = read_and_validate_file(path)
            values = make_values(df)

            with conn.cursor() as cur:
                execute_values(
                    cur,
                    INSERT_SQL,
                    values,
                    page_size=2000,
                )

            imported_rows += len(values)

            if index % 25 == 0 or index == len(files):
                print(
                    f"Processed {index}/{len(files)} files; "
                    f"{imported_rows:,}/{EXPECTED_TOTAL_ROWS:,} rows"
                )

        conn.commit()
        print("\nIMPORT COMMITTED")
        print(f"Rows upserted: {imported_rows:,}")
        print(f"Unique locations: {len(locations)}")
        print(f"Time range: {EXPECTED_START} -> {EXPECTED_END}")
        print("Older records were not deleted.")

    except Exception:
        if conn is not None:
            conn.rollback()
        print(
            "\nIMPORT FAILED: transaction rolled back; "
            "no partial changes from this run were committed.",
            file=sys.stderr,
        )
        raise

    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    main()
