import os
from pathlib import Path

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values


DB_CONFIG = {
    "dbname": "weather_forecasting",
    "user": "postgres",
    "host": "localhost",
    "port": 5432,
}

INPUT_FILE = Path("data/processed/hydrology_confirmed_30_stations.csv")
SOURCE = "professor_hydrology_api"
TIMEZONE = "Asia/Ho_Chi_Minh"


def get_db_config():
    password = os.getenv("POSTGRES_PASSWORD") or os.getenv("PGPASSWORD")

    if not password:
        raise EnvironmentError(
            "Database password not found. Set POSTGRES_PASSWORD or PGPASSWORD."
        )

    return {**DB_CONFIG, "password": password}


def main():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(f"Input file not found: {INPUT_FILE}")

    print(f"Reading: {INPUT_FILE}")

    df = pd.read_csv(INPUT_FILE, dtype={"station_id": str})

    required_columns = {"station_id", "timestamp", "value"}
    missing_columns = required_columns - set(df.columns)

    if missing_columns:
        raise ValueError(
            f"Missing required columns: {sorted(missing_columns)}"
        )

    df["station_id"] = df["station_id"].str.strip()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")

    df = df.dropna(subset=["station_id", "timestamp"])
    df = df[df["station_id"] != ""]

    # The source CSV contains Vietnam-local timestamps without timezone data.
    # Localize them explicitly before writing to PostgreSQL TIMESTAMPTZ.
    if df["timestamp"].dt.tz is None:
        df["timestamp"] = df["timestamp"].dt.tz_localize(
            TIMEZONE,
            ambiguous="raise",
            nonexistent="raise",
        )
    else:
        df["timestamp"] = df["timestamp"].dt.tz_convert(TIMEZONE)

    duplicate_count = int(
        df.duplicated(subset=["station_id", "timestamp"]).sum()
    )

    if duplicate_count:
        print(f"Duplicate station/timestamp rows removed: {duplicate_count:,}")

    df = (
        df.drop_duplicates(subset=["station_id", "timestamp"])
        .sort_values(["station_id", "timestamp"])
        .reset_index(drop=True)
    )

    print(f"Rows prepared: {len(df):,}")
    print(f"Stations: {df['station_id'].nunique()}")
    print(f"Timestamp timezone: {TIMEZONE}")

    insert_sql = """
        INSERT INTO hydrology_observations (
            station_id,
            timestamp,
            value,
            source
        )
        VALUES %s
        ON CONFLICT (station_id, timestamp)
        DO UPDATE SET
            value = EXCLUDED.value,
            source = EXCLUDED.source
    """

    rows = [
        (
            row.station_id,
            row.timestamp.to_pydatetime(),
            None if pd.isna(row.value) else float(row.value),
            SOURCE,
        )
        for row in df.itertuples(index=False)
    ]

    # The connection context commits on success and rolls back on failure.
    with psycopg2.connect(**get_db_config()) as conn:
        with conn.cursor() as cur:
            execute_values(
                cur,
                insert_sql,
                rows,
                page_size=2000,
            )

            cur.execute("SELECT COUNT(*) FROM hydrology_observations")
            db_count = cur.fetchone()[0]

            cur.execute(
                """
                SELECT COUNT(DISTINCT station_id)
                FROM hydrology_observations
                """
            )
            station_count = cur.fetchone()[0]

    print()
    print("========== IMPORT COMPLETE ==========")
    print(f"Rows processed: {len(rows):,}")
    print(f"Stations in database: {station_count}")
    print(f"Hydrology rows in PostgreSQL: {db_count:,}")
    print("Import transaction committed successfully.")


if __name__ == "__main__":
    main()