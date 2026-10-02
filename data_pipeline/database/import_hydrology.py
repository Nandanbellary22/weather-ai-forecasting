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

INPUT_FILE = Path("data/processed/hydrology_confirmed_30_stations.csv")
SOURCE = "professor_hydrology_api"


def main():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(f"Input file not found: {INPUT_FILE}")

    print(f"Reading: {INPUT_FILE}")

    df = pd.read_csv(
        INPUT_FILE,
        dtype={"station_id": str},
    )

    required_columns = {"station_id", "timestamp", "value"}

    missing_columns = required_columns - set(df.columns)

    if missing_columns:
        raise ValueError(
            f"Missing required columns: {sorted(missing_columns)}"
        )

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")

    df = df.dropna(subset=["station_id", "timestamp"])

    df = (
        df.drop_duplicates(subset=["station_id", "timestamp"])
        .sort_values(["station_id", "timestamp"])
        .reset_index(drop=True)
    )

    print(f"Rows prepared: {len(df):,}")
    print(f"Stations: {df['station_id'].nunique()}")

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    insert_sql = """
        INSERT INTO hydrology_observations (
            station_id,
            timestamp,
            value,
            source
        )
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (station_id, timestamp)
        DO UPDATE SET
            value = EXCLUDED.value,
            source = EXCLUDED.source
    """

    inserted_or_updated = 0

    for _, row in df.iterrows():
        cur.execute(
            insert_sql,
            (
                row["station_id"],
                row["timestamp"].to_pydatetime(),
                None if pd.isna(row["value"]) else float(row["value"]),
                SOURCE,
            ),
        )

        inserted_or_updated += 1

        if inserted_or_updated % 10000 == 0:
            print(f"Processed: {inserted_or_updated:,}")

    conn.commit()

    cur.execute(
        "SELECT COUNT(*) FROM hydrology_observations"
    )
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
    print(f"Rows processed: {inserted_or_updated:,}")
    print(f"Stations in database: {station_count}")
    print(f"Hydrology rows in PostgreSQL: {db_count:,}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()