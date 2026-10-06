import os
from pathlib import Path

import pandas as pd
import psycopg2


CSV_PATH = Path("data/processed/evn_reservoir_current.csv")

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "weather_forecasting",
    "user": "postgres",
    "password": os.getenv("PGPASSWORD"),
}

TARGET_YEAR = 2026


def parse_evn_timestamp(series: pd.Series) -> pd.Series:
    """
    EVN source timestamps contain DD/MM HH:MM without a year.

    Examples:
        24/09 16:00
        24/0916:00

    The current EVN dataset is associated with TARGET_YEAR.
    """

    values = (
        series.astype(str)
        .str.strip()
        .str.replace(
            r"^(\d{2}/\d{2})(\d{1,2}:\d{2})$",
            r"\1 \2",
            regex=True,
        )
    )

    return pd.to_datetime(
        f"{TARGET_YEAR}/" + values,
        format="%Y/%d/%m %H:%M",
        errors="coerce",
    )


def main():
    print("=" * 70)
    print("EVN RESERVOIR IMPORT")
    print("=" * 70)

    if not CSV_PATH.exists():
        raise FileNotFoundError(
            f"EVN CSV not found: {CSV_PATH}"
        )

    df = pd.read_csv(CSV_PATH)

    required = [
        "reservoir_name",
        "observation_time",
        "water_level_m",
        "normal_water_level_m",
        "dead_water_level_m",
        "inflow_m3s",
        "total_discharge_m3s",
        "spillway_discharge_m3s",
        "powerhouse_discharge_m3s",
        "deep_release_gates",
        "surface_release_gates",
        "sync_time",
    ]

    missing = [
        column
        for column in required
        if column not in df.columns
    ]

    if missing:
        raise ValueError(
            f"Missing required columns: {missing}"
        )

    print(f"Source rows: {len(df)}")

    # --------------------------------------------------
    # Keep required columns
    # --------------------------------------------------

    df = df[required].copy()

    # --------------------------------------------------
    # Clean reservoir names
    # --------------------------------------------------

    df["reservoir_name"] = (
        df["reservoir_name"]
        .astype(str)
        .str.strip()
    )

    # --------------------------------------------------
    # Parse EVN timestamp correctly
    # --------------------------------------------------

    raw_timestamps = df["observation_time"].copy()

    df["observation_time"] = parse_evn_timestamp(
        df["observation_time"]
    )

    invalid_timestamps = df[
        "observation_time"
    ].isna().sum()

    if invalid_timestamps:
        print(
            f"WARNING: Invalid timestamps: "
            f"{invalid_timestamps}"
        )

        print(
            raw_timestamps[
                df["observation_time"].isna()
            ].tolist()
        )

    # --------------------------------------------------
    # Convert numeric fields
    # --------------------------------------------------

    numeric_columns = [
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

    for column in numeric_columns:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    # --------------------------------------------------
    # Remove invalid rows
    # --------------------------------------------------

    df = df[
        df["reservoir_name"].notna()
        & df["reservoir_name"].ne("")
        & df["observation_time"].notna()
    ].copy()

    # --------------------------------------------------
    # One current observation per reservoir
    # --------------------------------------------------

    df = (
        df.sort_values(
            [
                "reservoir_name",
                "observation_time",
            ]
        )
        .drop_duplicates(
            subset=["reservoir_name"],
            keep="last",
        )
        .reset_index(drop=True)
    )

    print(f"Valid rows: {len(df)}")

    # --------------------------------------------------
    # Timestamp validation
    # --------------------------------------------------

    print(
        "Observation range: "
        f"{df['observation_time'].min()} -> "
        f"{df['observation_time'].max()}"
    )

    invalid_years = df[
        df["observation_time"].dt.year != TARGET_YEAR
    ]

    if not invalid_years.empty:
        raise ValueError(
            "Invalid EVN observation year detected:\n"
            f"{invalid_years[['reservoir_name', 'observation_time']]}"
        )

    # --------------------------------------------------
    # Database connection
    # --------------------------------------------------

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    sql = """
        INSERT INTO evn_reservoirs (
            reservoir_name,
            observation_time,
            htl,
            hdbt,
            hc,
            qve,
            total_discharge,
            powerhouse_discharge,
            spillway_discharge,
            ncxs,
            ncxm,
            source
        )
        VALUES (
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s
        )
        ON CONFLICT (reservoir_name)
        DO UPDATE SET
            observation_time = EXCLUDED.observation_time,
            htl = EXCLUDED.htl,
            hdbt = EXCLUDED.hdbt,
            hc = EXCLUDED.hc,
            qve = EXCLUDED.qve,
            total_discharge = EXCLUDED.total_discharge,
            powerhouse_discharge = EXCLUDED.powerhouse_discharge,
            spillway_discharge = EXCLUDED.spillway_discharge,
            ncxs = EXCLUDED.ncxs,
            ncxm = EXCLUDED.ncxm,
            source = EXCLUDED.source,
            created_at = NOW()
    """

    rows = []

    for _, row in df.iterrows():
        rows.append(
            (
                row["reservoir_name"],
                row["observation_time"].to_pydatetime(),
                row["water_level_m"],
                row["normal_water_level_m"],
                row["dead_water_level_m"],
                row["inflow_m3s"],
                row["total_discharge_m3s"],
                row["powerhouse_discharge_m3s"],
                row["spillway_discharge_m3s"],
                row["deep_release_gates"],
                row["surface_release_gates"],
                "evn_reservoir_current",
            )
        )

    # --------------------------------------------------
    # Upsert
    # --------------------------------------------------

    cur.executemany(
        sql,
        rows,
    )

    conn.commit()

    # --------------------------------------------------
    # Verification
    # --------------------------------------------------

    cur.execute(
        "SELECT COUNT(*) FROM evn_reservoirs"
    )

    total = cur.fetchone()[0]

    cur.execute(
        """
        SELECT
            COUNT(*),
            MIN(observation_time),
            MAX(observation_time)
        FROM evn_reservoirs
        """
    )

    count, min_time, max_time = cur.fetchone()

    print(f"Imported/upserted: {len(rows)}")
    print(f"Total EVN reservoirs in DB: {total}")
    print(f"Verified rows: {count}")
    print(
        f"Database observation range: "
        f"{min_time} -> {max_time}"
    )

    # --------------------------------------------------
    # Final safety check
    # --------------------------------------------------

    if min_time.year != TARGET_YEAR:
        raise RuntimeError(
            f"Database contains an invalid minimum year: "
            f"{min_time}"
        )

    if max_time.year != TARGET_YEAR:
        raise RuntimeError(
            f"Database contains an invalid maximum year: "
            f"{max_time}"
        )

    cur.close()
    conn.close()

    print("=" * 70)
    print("EVN IMPORT COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()