import os

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values


CSV_PATH = "data/processed/mrc_vietnam_measurements.csv"


def get_connection():
    return psycopg2.connect(
        host="localhost",
        port=5432,
        dbname="weather_forecasting",
        user="postgres",
        password=os.environ.get("PGPASSWORD"),
    )


def create_table(conn):
    sql = """
    CREATE TABLE IF NOT EXISTS mrc_hydromet_observations (
        id BIGSERIAL PRIMARY KEY,
        station_id VARCHAR(20) NOT NULL,
        timestamp TIMESTAMPTZ NOT NULL,
        timestamp_utc TIMESTAMPTZ NOT NULL,
        water_level DOUBLE PRECISION,
        rainfall DOUBLE PRECISION,
        temperature DOUBLE PRECISION,
        battery DOUBLE PRECISION,
        source VARCHAR(20) DEFAULT 'MRC',
        created_at TIMESTAMPTZ DEFAULT NOW(),

        CONSTRAINT mrc_station_timestamp_unique
        UNIQUE (station_id, timestamp_utc)
    );

    CREATE INDEX IF NOT EXISTS idx_mrc_station
    ON mrc_hydromet_observations (station_id);

    CREATE INDEX IF NOT EXISTS idx_mrc_timestamp
    ON mrc_hydromet_observations (timestamp);

    CREATE INDEX IF NOT EXISTS idx_mrc_station_timestamp
    ON mrc_hydromet_observations (station_id, timestamp);
    """

    with conn.cursor() as cur:
        cur.execute(sql)

    conn.commit()

    print("MRC table created/verified.")


def load_csv():
    print(f"Reading: {CSV_PATH}")

    df = pd.read_csv(
        CSV_PATH,
        dtype={"station_id": str},
    )

    print(f"CSV rows: {len(df)}")

    df["station_id"] = (
        df["station_id"]
        .astype(str)
        .str.zfill(6)
    )

    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        utc=True,
    )

    df["timestamp_utc"] = pd.to_datetime(
        df["timestamp_utc"],
        utc=True,
    )

    numeric_columns = [
        "water_level",
        "rainfall",
        "temperature",
        "battery",
    ]

    for column in numeric_columns:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    return df


def import_data(conn, df):
    rows = []

    for row in df.itertuples(index=False):

        rows.append(
            (
                row.station_id,
                row.timestamp.to_pydatetime(),
                row.timestamp_utc.to_pydatetime(),
                row.water_level,
                row.rainfall,
                row.temperature,
                row.battery,
                "MRC",
            )
        )

    sql = """
    INSERT INTO mrc_hydromet_observations (
        station_id,
        timestamp,
        timestamp_utc,
        water_level,
        rainfall,
        temperature,
        battery,
        source
    )
    VALUES %s
    ON CONFLICT (station_id, timestamp_utc)
    DO UPDATE SET
        timestamp = EXCLUDED.timestamp,
        water_level = EXCLUDED.water_level,
        rainfall = EXCLUDED.rainfall,
        temperature = EXCLUDED.temperature,
        battery = EXCLUDED.battery,
        source = EXCLUDED.source;
    """

    with conn.cursor() as cur:

        execute_values(
            cur,
            sql,
            rows,
            page_size=1000,
        )

    conn.commit()

    print(
        f"Imported/updated {len(rows)} MRC records."
    )


def print_database_summary(conn):
    print()
    print("=" * 70)
    print("MRC DATABASE SUMMARY")
    print("=" * 70)

    with conn.cursor() as cur:

        cur.execute(
            """
            SELECT COUNT(*)
            FROM mrc_hydromet_observations;
            """
        )

        total = cur.fetchone()[0]

        print(
            f"Total observations: {total}"
        )

        cur.execute(
            """
            SELECT
                station_id,
                COUNT(*) AS records,
                MIN(timestamp_utc) AS oldest,
                MAX(timestamp_utc) AS newest
            FROM mrc_hydromet_observations
            GROUP BY station_id
            ORDER BY station_id;
            """
        )

        rows = cur.fetchall()

        print()
        print(
            "Station coverage:"
        )
        print("-" * 70)

        for row in rows:
            print(
                f"{row[0]} | "
                f"{row[1]} records | "
                f"{row[2]} -> {row[3]}"
            )

    print("=" * 70)


def main():

    print("=" * 70)
    print("MRC POSTGRESQL IMPORT")
    print("=" * 70)

    if not os.environ.get("PGPASSWORD"):
        raise RuntimeError(
            "PGPASSWORD is not set in this PowerShell session."
        )

    df = load_csv()

    conn = get_connection()

    try:

        create_table(conn)

        import_data(
            conn,
            df,
        )

        print_database_summary(
            conn
        )

    finally:

        conn.close()

    print()
    print(
        "MRC PostgreSQL import completed successfully."
    )


if __name__ == "__main__":
    main()