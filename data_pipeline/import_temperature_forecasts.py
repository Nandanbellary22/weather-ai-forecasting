
import csv
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from getpass import getpass
from zoneinfo import ZoneInfo

import psycopg2
from psycopg2.extras import execute_values


EXPECTED_COLUMNS = [
    "collection_time_utc",
    "target_time_local",
    "timezone",
    "source",
    "location_id",
    "location_name",
    "requested_latitude",
    "requested_longitude",
    "returned_latitude",
    "returned_longitude",
    "forecast_temperature_c",
]

EXPECTED_ROWS = 24_000
EXPECTED_LOCATIONS = 500
EXPECTED_TARGET_TIMES = 48
EXPECTED_TIMEZONE = "Asia/Ho_Chi_Minh"

DEFAULT_CSV = (
    Path.home()
    / "Downloads"
    / "temperature-forecast-extracted"
    / "temperature_forecast_20261023T162439161437Z.csv"
)

INSERT_SQL = """
    INSERT INTO temperature_forecast_snapshots (
        collection_time_utc,
        target_time_local,
        timezone,
        source,
        location_id,
        location_name,
        requested_latitude,
        requested_longitude,
        returned_latitude,
        returned_longitude,
        forecast_temperature_c
    )
    VALUES %s
    ON CONFLICT (
        collection_time_utc,
        location_id,
        target_time_local
    ) DO NOTHING
"""


def parse_timestamp(value, field_name):
    try:
        result = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {field_name}: {value!r}") from exc

    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone offset.")

    return result


def parse_finite_float(value, field_name):
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {field_name}: {value!r}") from exc

    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be finite: {value!r}")

    return number


def load_and_validate(csv_path):
    if not csv_path.is_file():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    rows = []
    location_ids = set()
    target_times = set()
    location_target_pairs = set()
    collection_times = set()
    timezones = set()
    sources = set()

    vietnam_tz = ZoneInfo(EXPECTED_TIMEZONE)

    with csv_path.open(
        "r", newline="", encoding="utf-8-sig"
    ) as file:
        reader = csv.DictReader(file)

        if reader.fieldnames != EXPECTED_COLUMNS:
            raise ValueError(
                "CSV columns do not match the expected schema.\n"
                f"Expected: {EXPECTED_COLUMNS}\n"
                f"Found:    {reader.fieldnames}"
            )

        for line_number, row in enumerate(reader, start=2):
            try:
                collection_time = parse_timestamp(
                    row["collection_time_utc"], "collection_time_utc"
                )
                target_time = parse_timestamp(
                    row["target_time_local"], "target_time_local"
                )

                if collection_time.utcoffset().total_seconds() != 0:
                    raise ValueError(
                        "collection_time_utc must have a UTC offset."
                    )

                if row["timezone"] != EXPECTED_TIMEZONE:
                    raise ValueError(
                        f"Unexpected timezone: {row['timezone']!r}"
                    )

                if target_time.utcoffset() != vietnam_tz.utcoffset(target_time):
                    raise ValueError(
                        "Target timestamp offset does not match Vietnam time."
                    )

                location_id = row["location_id"].strip()
                location_name = row["location_name"].strip()
                source = row["source"].strip()

                if not location_id or not location_name or not source:
                    raise ValueError(
                        "Location ID, location name, and source cannot be blank."
                    )

                requested_lat = parse_finite_float(
                    row["requested_latitude"], "requested_latitude"
                )
                requested_lon = parse_finite_float(
                    row["requested_longitude"], "requested_longitude"
                )
                returned_lat = parse_finite_float(
                    row["returned_latitude"], "returned_latitude"
                )
                returned_lon = parse_finite_float(
                    row["returned_longitude"], "returned_longitude"
                )
                temperature = parse_finite_float(
                    row["forecast_temperature_c"], "forecast_temperature_c"
                )

                if not -90 <= requested_lat <= 90:
                    raise ValueError("Requested latitude is out of range.")
                if not -180 <= requested_lon <= 180:
                    raise ValueError("Requested longitude is out of range.")
                if not -90 <= returned_lat <= 90:
                    raise ValueError("Returned latitude is out of range.")
                if not -180 <= returned_lon <= 180:
                    raise ValueError("Returned longitude is out of range.")

                # PostgreSQL stores target_time_local without a timezone.
                # Convert the offset-aware time to Vietnam local time first.
                target_local_naive = (
                    target_time.astimezone(vietnam_tz).replace(tzinfo=None)
                )

                collection_utc = collection_time.astimezone(timezone.utc)

                pair = (location_id, target_local_naive)

                if pair in location_target_pairs:
                    raise ValueError(
                        f"Duplicate location/target-time pair: {pair}"
                    )

                location_target_pairs.add(pair)
                location_ids.add(location_id)
                target_times.add(target_local_naive)
                collection_times.add(collection_utc)
                timezones.add(row["timezone"])
                sources.add(source)

                rows.append(
                    (
                        collection_utc,
                        target_local_naive,
                        row["timezone"],
                        source,
                        location_id,
                        location_name,
                        requested_lat,
                        requested_lon,
                        returned_lat,
                        returned_lon,
                        temperature,
                    )
                )

            except Exception as exc:
                raise ValueError(
                    f"CSV validation failed on line {line_number}: {exc}"
                ) from exc

    if len(rows) != EXPECTED_ROWS:
        raise ValueError(
            f"Expected {EXPECTED_ROWS:,} rows; found {len(rows):,}."
        )

    if len(location_ids) != EXPECTED_LOCATIONS:
        raise ValueError(
            f"Expected {EXPECTED_LOCATIONS} locations; "
            f"found {len(location_ids)}."
        )

    if len(target_times) != EXPECTED_TARGET_TIMES:
        raise ValueError(
            f"Expected {EXPECTED_TARGET_TIMES} target timestamps; "
            f"found {len(target_times)}."
        )

    if len(location_target_pairs) != EXPECTED_ROWS:
        raise ValueError("Location/target-time uniqueness validation failed.")

    if len(collection_times) != 1:
        raise ValueError("Rows do not share one consistent collection time.")

    if timezones != {EXPECTED_TIMEZONE}:
        raise ValueError("The snapshot contains inconsistent timezones.")

    if len(sources) != 1:
        raise ValueError("Rows do not share one consistent data source.")

    return rows


def main():
    csv_path = Path(
        os.environ.get("TEMPERATURE_FORECAST_CSV", str(DEFAULT_CSV))
    ).expanduser()

    print(f"Reading: {csv_path}")
    rows = load_and_validate(csv_path)

    print("Validation passed.")
    print(f"Rows: {len(rows):,}")
    print(f"Locations: {EXPECTED_LOCATIONS}")
    print(f"Target timestamps: {EXPECTED_TARGET_TIMES}")
    print("Connecting to PostgreSQL...")

    password = os.environ.get("PGPASSWORD")
    if password is None:
        password = getpass("PostgreSQL password for the configured user: ")

    connection = psycopg2.connect(
        host=os.environ.get("PGHOST", "localhost"),
        port=int(os.environ.get("PGPORT", "5432")),
        dbname=os.environ.get("PGDATABASE", "weather_forecasting"),
        user=os.environ.get("PGUSER", "postgres"),
        password=password,
        connect_timeout=10,
    )

    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) FROM temperature_forecast_snapshots"
                )
                count_before = cursor.fetchone()[0]

                execute_values(
                    cursor,
                    INSERT_SQL,
                    rows,
                    page_size=1000,
                )

                inserted = cursor.rowcount

                cursor.execute(
                    """
                    SELECT COUNT(*)
                    FROM temperature_forecast_snapshots
                    """
                )
                count_after = cursor.fetchone()[0]

        print("\nImport completed successfully.")
        print(f"Rows in snapshot file: {len(rows):,}")
        print(f"Rows inserted: {inserted:,}")
        print(f"Duplicate rows skipped: {len(rows) - inserted:,}")
        print(f"Database rows before import: {count_before:,}")
        print(f"Database rows after import: {count_after:,}")

    finally:
        connection.close()


if __name__ == "__main__":
    main()
