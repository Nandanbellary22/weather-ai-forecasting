import os
from pathlib import Path

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values


PROJECT_ROOT = Path(__file__).resolve().parents[1]

CSV_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "historical_180days_all_stations.csv"
)


DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "weather_forecasting",
    "user": "postgres",
    "password": os.getenv("POSTGRES_PASSWORD"),
}


# The source APIs provide observation timestamps
# as Vietnam local clock time without timezone information.
SOURCE_TIMEZONE = "Asia/Ho_Chi_Minh"


def load_csv() -> pd.DataFrame:
    print(f"Loading CSV: {CSV_PATH}")
    print(f"Interpreting source timestamps as: {SOURCE_TIMEZONE}")

    df = pd.read_csv(CSV_PATH)

    required_columns = {
        "station_id",
        "timestamp",
        "value",
    }

    missing = required_columns - set(df.columns)

    if missing:
        raise ValueError(
            f"Missing required columns: {sorted(missing)}"
        )

    df["station_id"] = df["station_id"].astype(str)

    # The source CSV contains Vietnam local observation times
    # without timezone information.
    #
    # First parse the timestamps as naive datetimes.
    # Then explicitly localize them to Vietnam time.
    #
    # This prevents PostgreSQL from incorrectly interpreting
    # the source timestamps using the computer/database timezone.
    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        errors="coerce",
    )

    if df["timestamp"].isna().any():
        raise ValueError(
            "CSV contains invalid timestamps."
        )

    df["timestamp"] = df["timestamp"].dt.tz_localize(
        SOURCE_TIMEZONE
    )

    df["value"] = pd.to_numeric(
        df["value"],
        errors="coerce",
    )

    duplicate_count = df.duplicated(
        subset=["station_id", "timestamp"]
    ).sum()

    if duplicate_count:
        raise ValueError(
            f"CSV contains {duplicate_count} "
            "duplicate station/timestamp rows."
        )

    df = df.sort_values(
        ["station_id", "timestamp"]
    ).reset_index(drop=True)

    print(f"CSV rows: {len(df)}")
    print(f"Stations: {df['station_id'].nunique()}")
    print(
        f"Missing values: {df['value'].isna().sum()}"
    )

    print(
        "Timestamp range:",
        df["timestamp"].min(),
        "to",
        df["timestamp"].max(),
    )

    return df


def get_connection():
    password = DB_CONFIG["password"]

    if not password:
        raise RuntimeError(
            "POSTGRES_PASSWORD environment variable is not set."
        )

    return psycopg2.connect(
        host=DB_CONFIG["host"],
        port=DB_CONFIG["port"],
        database=DB_CONFIG["database"],
        user=DB_CONFIG["user"],
        password=password,
    )


def insert_data(df: pd.DataFrame):
    connection = get_connection()

    try:
        with connection:
            with connection.cursor() as cursor:

                rows = [
                    (
                        row.station_id,
                        row.timestamp,
                        None
                        if pd.isna(row.value)
                        else float(row.value),
                        "professor_hydrology_api",
                    )
                    for row in df.itertuples(index=False)
                ]

                query = """
                    INSERT INTO hydrology_observations
                    (
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

                execute_values(
                    cursor,
                    query,
                    rows,
                    page_size=1000,
                )

                print(
                    f"Inserted/updated {len(rows)} rows."
                )

    finally:
        connection.close()


def main():
    df = load_csv()

    insert_data(df)

    print(
        "Hydrology data ingestion completed successfully."
    )


if __name__ == "__main__":
    main()