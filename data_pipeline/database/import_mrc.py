
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

        rainfall_1h DOUBLE PRECISION,
        rainfall_6h DOUBLE PRECISION,
        rainfall_12h DOUBLE PRECISION,
        rainfall_24h DOUBLE PRECISION,
        rainfall_7to7 DOUBLE PRECISION,

        temperature DOUBLE PRECISION,
        battery DOUBLE PRECISION,

        source VARCHAR(20) DEFAULT 'MRC',
        created_at TIMESTAMPTZ DEFAULT NOW(),

        CONSTRAINT mrc_station_timestamp_unique
        UNIQUE (station_id, timestamp_utc)
    );

    ALTER TABLE mrc_hydromet_observations
    ADD COLUMN IF NOT EXISTS rainfall_1h DOUBLE PRECISION;

    ALTER TABLE mrc_hydromet_observations
    ADD COLUMN IF NOT EXISTS rainfall_6h DOUBLE PRECISION;

    ALTER TABLE mrc_hydromet_observations
    ADD COLUMN IF NOT EXISTS rainfall_12h DOUBLE PRECISION;

    ALTER TABLE mrc_hydromet_observations
    ADD COLUMN IF NOT EXISTS rainfall_24h DOUBLE PRECISION;

    ALTER TABLE mrc_hydromet_observations
    ADD COLUMN IF NOT EXISTS rainfall_7to7 DOUBLE PRECISION;

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

    if not os.path.exists(CSV_PATH):
        raise FileNotFoundError(
            f"MRC measurement CSV not found: {CSV_PATH}"
        )

    df = pd.read_csv(
        CSV_PATH,
        dtype={"station_id": str},
    )

    print(f"CSV rows: {len(df)}")

    if df.empty:
        raise ValueError("MRC measurement CSV is empty.")

    df["station_id"] = (
        df["station_id"]
        .astype("string")
        .str.strip()
        .str.zfill(6)
    )

    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        utc=True,
        errors="coerce",
    )

    df["timestamp_utc"] = pd.to_datetime(
        df["timestamp_utc"],
        utc=True,
        errors="coerce",
    )

    numeric_columns = [
        "water_level",
        "rainfall",
        "rainfall_1h",
        "rainfall_6h",
        "rainfall_12h",
        "rainfall_24h",
        "rainfall_7to7",
        "temperature",
        "battery",
    ]

    for column in numeric_columns:
        if column not in df.columns:
            df[column] = pd.NA

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    required_columns = [
        "station_id",
        "timestamp",
        "timestamp_utc",
        "water_level",
        "rainfall",
        "rainfall_1h",
        "rainfall_6h",
        "rainfall_12h",
        "rainfall_24h",
        "rainfall_7to7",
        "temperature",
        "battery",
    ]

    df = df[required_columns].copy()

    df = df.dropna(
        subset=[
            "station_id",
            "timestamp",
            "timestamp_utc",
        ]
    )

    df = df.drop_duplicates(
        subset=[
            "station_id",
            "timestamp_utc",
        ],
        keep="last",
    )

    print(f"Valid rows after cleaning: {len(df)}")

    print()
    print("CSV missing values:")
    print(
        f"  water_level:   {df['water_level'].isna().sum()}"
    )
    print(
        f"  rainfall:      {df['rainfall'].isna().sum()}"
    )
    print(
        f"  rainfall_1h:   {df['rainfall_1h'].isna().sum()}"
    )
    print(
        f"  rainfall_6h:   {df['rainfall_6h'].isna().sum()}"
    )
    print(
        f"  rainfall_12h:  {df['rainfall_12h'].isna().sum()}"
    )
    print(
        f"  rainfall_24h:  {df['rainfall_24h'].isna().sum()}"
    )
    print(
        f"  rainfall_7to7: {df['rainfall_7to7'].isna().sum()}"
    )
    print(
        f"  temperature:   {df['temperature'].isna().sum()}"
    )
    print(
        f"  battery:       {df['battery'].isna().sum()}"
    )

    return df


def python_value(value):
    """
    Convert pandas missing/numeric values into values that
    psycopg2 can safely send to PostgreSQL.

    pandas NaN / NA -> None -> PostgreSQL NULL
    """

    if pd.isna(value):
        return None

    if hasattr(value, "item"):
        return value.item()

    return value


def import_data(conn, df):
    rows = []

    for row in df.itertuples(index=False):

        rows.append(
            (
                python_value(row.station_id),
                python_value(row.timestamp.to_pydatetime()),
                python_value(row.timestamp_utc.to_pydatetime()),
                python_value(row.water_level),
                python_value(row.rainfall),
                python_value(row.rainfall_1h),
                python_value(row.rainfall_6h),
                python_value(row.rainfall_12h),
                python_value(row.rainfall_24h),
                python_value(row.rainfall_7to7),
                python_value(row.temperature),
                python_value(row.battery),
                "MRC",
            )
        )

    if not rows:
        print("No rows to import.")
        return

    sql = """
    INSERT INTO mrc_hydromet_observations (
        station_id,
        timestamp,
        timestamp_utc,
        water_level,
        rainfall,
        rainfall_1h,
        rainfall_6h,
        rainfall_12h,
        rainfall_24h,
        rainfall_7to7,
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
        rainfall_1h = EXCLUDED.rainfall_1h,
        rainfall_6h = EXCLUDED.rainfall_6h,
        rainfall_12h = EXCLUDED.rainfall_12h,
        rainfall_24h = EXCLUDED.rainfall_24h,
        rainfall_7to7 = EXCLUDED.rainfall_7to7,
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


def clean_existing_nan_values(conn):
    """
    Convert existing PostgreSQL floating-point NaN values
    into proper SQL NULL values.

    This fixes records imported by older versions of the
    importer.
    """

    print()
    print("Cleaning existing PostgreSQL NaN values...")

    sql = """
    UPDATE mrc_hydromet_observations
    SET
        water_level = NULLIF(water_level, 'NaN'::double precision),
        rainfall = NULLIF(rainfall, 'NaN'::double precision),
        rainfall_1h = NULLIF(rainfall_1h, 'NaN'::double precision),
        rainfall_6h = NULLIF(rainfall_6h, 'NaN'::double precision),
        rainfall_12h = NULLIF(rainfall_12h, 'NaN'::double precision),
        rainfall_24h = NULLIF(rainfall_24h, 'NaN'::double precision),
        rainfall_7to7 = NULLIF(rainfall_7to7, 'NaN'::double precision),
        temperature = NULLIF(temperature, 'NaN'::double precision),
        battery = NULLIF(battery, 'NaN'::double precision);
    """

    with conn.cursor() as cur:
        cur.execute(sql)
        updated_rows = cur.rowcount

    conn.commit()

    print(
        f"Cleaned NaN values across {updated_rows} database rows."
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

        print(f"Total observations: {total}")

        cur.execute(
            """
            SELECT
                COUNT(*) FILTER (
                    WHERE water_level IS NULL
                ),
                COUNT(*) FILTER (
                    WHERE rainfall IS NULL
                ),
                COUNT(*) FILTER (
                    WHERE rainfall_1h IS NULL
                ),
                COUNT(*) FILTER (
                    WHERE rainfall_6h IS NULL
                ),
                COUNT(*) FILTER (
                    WHERE rainfall_12h IS NULL
                ),
                COUNT(*) FILTER (
                    WHERE rainfall_24h IS NULL
                ),
                COUNT(*) FILTER (
                    WHERE rainfall_7to7 IS NULL
                ),
                COUNT(*) FILTER (
                    WHERE temperature IS NULL
                ),
                COUNT(*) FILTER (
                    WHERE battery IS NULL
                )
            FROM mrc_hydromet_observations;
            """
        )

        null_counts = cur.fetchone()

        print()
        print("SQL NULL counts:")
        print(
            f"  water_level:   {null_counts[0]}"
        )
        print(
            f"  rainfall:      {null_counts[1]}"
        )
        print(
            f"  rainfall_1h:   {null_counts[2]}"
        )
        print(
            f"  rainfall_6h:   {null_counts[3]}"
        )
        print(
            f"  rainfall_12h:  {null_counts[4]}"
        )
        print(
            f"  rainfall_24h:  {null_counts[5]}"
        )
        print(
            f"  rainfall_7to7: {null_counts[6]}"
        )
        print(
            f"  temperature:   {null_counts[7]}"
        )
        print(
            f"  battery:       {null_counts[8]}"
        )

        cur.execute(
            """
            SELECT
                COUNT(*) FILTER (
                    WHERE water_level = 'NaN'::double precision
                ),
                COUNT(*) FILTER (
                    WHERE rainfall = 'NaN'::double precision
                ),
                COUNT(*) FILTER (
                    WHERE rainfall_1h = 'NaN'::double precision
                ),
                COUNT(*) FILTER (
                    WHERE rainfall_6h = 'NaN'::double precision
                ),
                COUNT(*) FILTER (
                    WHERE rainfall_12h = 'NaN'::double precision
                ),
                COUNT(*) FILTER (
                    WHERE rainfall_24h = 'NaN'::double precision
                ),
                COUNT(*) FILTER (
                    WHERE rainfall_7to7 = 'NaN'::double precision
                ),
                COUNT(*) FILTER (
                    WHERE temperature = 'NaN'::double precision
                ),
                COUNT(*) FILTER (
                    WHERE battery = 'NaN'::double precision
                )
            FROM mrc_hydromet_observations;
            """
        )

        nan_counts = cur.fetchone()

        print()
        print("Remaining PostgreSQL NaN counts:")
        print(
            f"  water_level:   {nan_counts[0]}"
        )
        print(
            f"  rainfall:      {nan_counts[1]}"
        )
        print(
            f"  rainfall_1h:   {nan_counts[2]}"
        )
        print(
            f"  rainfall_6h:   {nan_counts[3]}"
        )
        print(
            f"  rainfall_12h:  {nan_counts[4]}"
        )
        print(
            f"  rainfall_24h:  {nan_counts[5]}"
        )
        print(
            f"  rainfall_7to7: {nan_counts[6]}"
        )
        print(
            f"  temperature:   {nan_counts[7]}"
        )
        print(
            f"  battery:       {nan_counts[8]}"
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
        print("Station coverage:")
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

        clean_existing_nan_values(conn)

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
