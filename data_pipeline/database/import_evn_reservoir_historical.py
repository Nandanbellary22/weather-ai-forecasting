"""Upsert the validated EVN historical-reservoir CSV into PostgreSQL."""

from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import psycopg2


BASE_DIR = Path(__file__).resolve().parents[2]
CSV_PATH = BASE_DIR / "data" / "processed" / "evn_reservoir_historical.csv"

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "weather_forecasting",
    "user": "postgres",
    "password": os.getenv("PGPASSWORD"),
}

TABLE_DDL = """
CREATE TABLE IF NOT EXISTS evn_reservoir_observations (
    id BIGSERIAL PRIMARY KEY,
    reservoir_name TEXT NOT NULL,
    requested_date DATE NOT NULL,
    observation_time_raw TEXT,
    observation_timestamp TIMESTAMP,
    observation_year_inferred BOOLEAN,
    observation_year_method VARCHAR(100),
    water_level_m DOUBLE PRECISION,
    normal_water_level_m DOUBLE PRECISION,
    dead_water_level_m DOUBLE PRECISION,
    inflow_m3s DOUBLE PRECISION,
    total_discharge_m3s DOUBLE PRECISION,
    spillway_discharge_m3s DOUBLE PRECISION,
    powerhouse_discharge_m3s DOUBLE PRECISION,
    deep_release_gates DOUBLE PRECISION,
    surface_release_gates DOUBLE PRECISION,
    source VARCHAR(100),
    quality_flag VARCHAR(50),
    collection_status VARCHAR(50),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_evn_reservoir_observations_name_requested_date
        UNIQUE (reservoir_name, requested_date)
)
"""

CSV_COLUMNS = [
    "reservoir_name",
    "requested_date",
    "observation_time_raw",
    "observation_timestamp",
    "observation_year_inferred",
    "observation_year_method",
    "water_level_m",
    "normal_water_level_m",
    "dead_water_level_m",
    "inflow_m3s",
    "total_discharge_m3s",
    "spillway_discharge_m3s",
    "powerhouse_discharge_m3s",
    "deep_release_gates",
    "surface_release_gates",
    "source",
    "quality_flag",
    "collection_status",
]
MEASUREMENT_COLUMNS = [
    "water_level_m",
    "normal_water_level_m",
    "dead_water_level_m",
    "inflow_m3s",
    "total_discharge_m3s",
    "spillway_discharge_m3s",
    "powerhouse_discharge_m3s",
    "deep_release_gates",
    "surface_release_gates",
]

UPSERT_SQL = """
INSERT INTO evn_reservoir_observations (
    reservoir_name,
    requested_date,
    observation_time_raw,
    observation_timestamp,
    observation_year_inferred,
    observation_year_method,
    water_level_m,
    normal_water_level_m,
    dead_water_level_m,
    inflow_m3s,
    total_discharge_m3s,
    spillway_discharge_m3s,
    powerhouse_discharge_m3s,
    deep_release_gates,
    surface_release_gates,
    source,
    quality_flag,
    collection_status
)
VALUES (
    %s, %s, %s, %s, %s, %s, %s, %s, %s,
    %s, %s, %s, %s, %s, %s, %s, %s, %s
)
ON CONFLICT (reservoir_name, requested_date)
DO UPDATE SET
    observation_time_raw = EXCLUDED.observation_time_raw,
    observation_timestamp = EXCLUDED.observation_timestamp,
    observation_year_inferred = EXCLUDED.observation_year_inferred,
    observation_year_method = EXCLUDED.observation_year_method,
    water_level_m = EXCLUDED.water_level_m,
    normal_water_level_m = EXCLUDED.normal_water_level_m,
    dead_water_level_m = EXCLUDED.dead_water_level_m,
    inflow_m3s = EXCLUDED.inflow_m3s,
    total_discharge_m3s = EXCLUDED.total_discharge_m3s,
    spillway_discharge_m3s = EXCLUDED.spillway_discharge_m3s,
    powerhouse_discharge_m3s = EXCLUDED.powerhouse_discharge_m3s,
    deep_release_gates = EXCLUDED.deep_release_gates,
    surface_release_gates = EXCLUDED.surface_release_gates,
    source = EXCLUDED.source,
    quality_flag = EXCLUDED.quality_flag,
    collection_status = EXCLUDED.collection_status,
    updated_at = NOW()
"""


def nullable_text(value: object) -> str | None:
    if pd.isna(value) or str(value).strip() == "":
        return None
    return str(value)


def nullable_float(value: object, column: str, row_number: int) -> float | None:
    if pd.isna(value) or str(value).strip() == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Invalid numeric value in CSV row {row_number}, {column}: {value!r}"
        ) from exc


def nullable_bool(value: object, row_number: int) -> bool | None:
    """Read booleans, including the CSV's existing 1.0/0.0 representation."""
    if pd.isna(value) or str(value).strip() == "":
        return None
    normalized = str(value).strip().casefold()
    if normalized in {"true", "1", "1.0"}:
        return True
    if normalized in {"false", "0", "0.0"}:
        return False
    raise ValueError(
        f"Invalid boolean value in CSV row {row_number}: {value!r}"
    )


def nullable_date(value: object, row_number: int) -> date:
    if pd.isna(value) or str(value).strip() == "":
        raise ValueError(f"requested_date is required in CSV row {row_number}.")
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError as exc:
        raise ValueError(
            f"Invalid requested_date in CSV row {row_number}: {value!r}"
        ) from exc


def nullable_timestamp(value: object, row_number: int) -> datetime | None:
    if pd.isna(value) or str(value).strip() == "":
        return None
    try:
        # The CSV has no UTC offset; keep the observed wall-clock timestamp
        # as TIMESTAMP WITHOUT TIME ZONE instead of inventing a timezone.
        parsed = datetime.fromisoformat(str(value).strip())
        if parsed.tzinfo is not None:
            raise ValueError("timezone offsets are not expected")
        return parsed
    except ValueError as exc:
        raise ValueError(
            f"Invalid observation_timestamp in CSV row {row_number}: {value!r}"
        ) from exc


def read_records() -> list[tuple[object, ...]]:
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"Historical EVN CSV not found: {CSV_PATH}")

    frame = pd.read_csv(CSV_PATH, encoding="utf-8-sig")
    missing_columns = [column for column in CSV_COLUMNS if column not in frame.columns]
    if missing_columns:
        raise ValueError(f"CSV is missing required columns: {missing_columns}")
    frame = frame[CSV_COLUMNS]

    duplicate_keys = frame.duplicated(["reservoir_name", "requested_date"]).sum()
    if duplicate_keys:
        raise ValueError(
            f"CSV contains {duplicate_keys} duplicate reservoir/date keys; refusing import."
        )

    records = []
    for index, row in frame.iterrows():
        row_number = index + 2  # Header is CSV line 1.
        reservoir_name = nullable_text(row["reservoir_name"])
        if reservoir_name is None:
            raise ValueError(f"reservoir_name is required in CSV row {row_number}.")

        values = {
            column: nullable_float(row[column], column, row_number)
            for column in MEASUREMENT_COLUMNS
        }
        records.append(
            (
                reservoir_name,
                nullable_date(row["requested_date"], row_number),
                nullable_text(row["observation_time_raw"]),
                nullable_timestamp(row["observation_timestamp"], row_number),
                nullable_bool(row["observation_year_inferred"], row_number),
                nullable_text(row["observation_year_method"]),
                values["water_level_m"],
                values["normal_water_level_m"],
                values["dead_water_level_m"],
                values["inflow_m3s"],
                values["total_discharge_m3s"],
                values["spillway_discharge_m3s"],
                values["powerhouse_discharge_m3s"],
                values["deep_release_gates"],
                values["surface_release_gates"],
                nullable_text(row["source"]),
                nullable_text(row["quality_flag"]),
                nullable_text(row["collection_status"]),
            )
        )
    return records


def main() -> None:
    records = read_records()
    with psycopg2.connect(**DB_CONFIG) as connection:
        with connection.cursor() as cursor:
            cursor.execute(TABLE_DDL)
            cursor.executemany(UPSERT_SQL, records)
            cursor.execute("SELECT COUNT(*) FROM evn_reservoir_observations")
            table_count = cursor.fetchone()[0]
    print(f"CSV rows loaded: {len(records)}")
    print(f"Rows upserted: {len(records)}")
    print(f"Rows now in evn_reservoir_observations: {table_count}")


if __name__ == "__main__":
    main()
