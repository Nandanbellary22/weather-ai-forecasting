from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from backend.services.db import get_connection


CSV_PATH = Path("data/processed/evn_reservoir_current.csv")
TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")

REQUIRED_COLUMNS = [
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

NUMERIC_COLUMNS = [
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
        %s, %s, %s, %s, %s, %s,
        %s, %s, %s, %s, %s, %s
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
        source = EXCLUDED.source
    WHERE
        evn_reservoirs.observation_time IS NULL
        OR EXCLUDED.observation_time >=
           evn_reservoirs.observation_time
"""


def parse_evn_timestamp(
    series: pd.Series,
    *,
    target_year: int | None = None,
) -> pd.Series:
    """Parse EVN DD/MM HH:MM values as Vietnam-local timestamps.

    EVN omits the year. Use the current Vietnam calendar year by default,
    while allowing an explicit year for deterministic tests and backfills.
    """
    if target_year is None:
        target_year = datetime.now(TIMEZONE).year

    values = (
        series.astype("string")
        .str.strip()
        .str.replace(
            r"^(\d{2}/\d{2})(\d{1,2}:\d{2})$",
            r"\1 \2",
            regex=True,
        )
    )

    parsed = pd.to_datetime(
        f"{target_year}/" + values,
        format="%Y/%d/%m %H:%M",
        errors="coerce",
    )

    return parsed.dt.tz_localize(TIMEZONE)


def prepare_dataframe(csv_path: Path = CSV_PATH) -> pd.DataFrame:
    if not csv_path.is_file():
        raise FileNotFoundError(f"EVN CSV not found: {csv_path}")

    df = pd.read_csv(csv_path)

    missing = [
        column for column in REQUIRED_COLUMNS
        if column not in df.columns
    ]

    if missing:
        raise ValueError(f"Missing EVN columns: {missing}")

    df = df[REQUIRED_COLUMNS].copy()

    df["reservoir_name"] = (
        df["reservoir_name"]
        .astype("string")
        .str.strip()
    )

    df["observation_time"] = parse_evn_timestamp(
        df["observation_time"]
    )

    for column in NUMERIC_COLUMNS:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    invalid_names = (
        df["reservoir_name"].isna()
        | df["reservoir_name"].eq("")
    )

    invalid_timestamps = df["observation_time"].isna()

    invalid_rows = invalid_names | invalid_timestamps

    if invalid_rows.any():
        raise ValueError(
            f"EVN import rejected: {int(invalid_rows.sum())} "
            "rows have invalid reservoir names or timestamps."
        )

    if df.empty:
        raise ValueError("EVN CSV contains no usable reservoir rows.")

    expected_year = datetime.now(TIMEZONE).year

    if (df["observation_time"].dt.year != expected_year).any():
        raise ValueError(
            "EVN observations must belong to the current Vietnam calendar "
            f"year ({expected_year})."
        )

    df = (
        df.sort_values(
            ["reservoir_name", "observation_time"]
        )
        .drop_duplicates(
            subset=["reservoir_name"],
            keep="last",
        )
        .reset_index(drop=True)
    )

    return df



def import_current_reservoirs(
    csv_path: Path = CSV_PATH,
    connection=None,
) -> dict:
    """
    Import current EVN reservoir observations.

    A caller may provide an existing connection. When omitted,
    the shared project database connection is used.
    """
    df = prepare_dataframe(csv_path)

    rows = []

    for row in df.itertuples(index=False):
        values = []

        for column in NUMERIC_COLUMNS:
            value = getattr(row, column)
            values.append(
                None if pd.isna(value) else float(value)
            )

        rows.append((
            row.reservoir_name,
            row.observation_time.to_pydatetime(),
            *values[:3],
            values[3],
            values[4],
            values[6],
            values[5],
            values[7],
            values[8],
            "evn_reservoir_current",
        ))

    owns_connection = connection is None
    conn = get_connection() if owns_connection else connection

    try:
        with conn.cursor() as cur:
            cur.executemany(UPSERT_SQL, rows)
            affected_rows = cur.rowcount

            cur.execute(
                """
                SELECT
                    COUNT(*),
                    MIN(observation_time),
                    MAX(observation_time)
                FROM evn_reservoirs
                WHERE source = 'evn_reservoir_current'
                """
            )

            total, min_time, max_time = cur.fetchone()

        if owns_connection:
            conn.commit()

        return {
            "source": "evn_reservoir_current",
            "status": "success",
            "records_fetched": len(df),
            "records_validated": len(df),
            "records_inserted_or_updated": affected_rows,
            "database_records": total,
            "database_min_observation_time": (
                min_time.isoformat() if min_time else None
            ),
            "database_max_observation_time": (
                max_time.isoformat() if max_time else None
            ),
            "timezone": "Asia/Ho_Chi_Minh",
        }

    except Exception:
        if owns_connection:
            conn.rollback()
        raise

    finally:
        if owns_connection:
            conn.close()



def main():
    result = import_current_reservoirs()

    print("=" * 65)
    print("EVN CURRENT RESERVOIR IMPORT")
    print("=" * 65)

    for key, value in result.items():
        print(f"{key}: {value}")

    print("=" * 65)


if __name__ == "__main__":
    main()
