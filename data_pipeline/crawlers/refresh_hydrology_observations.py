"""Refresh recent readings for active hydrology stations from the source API.

The collector reads only the active station registry and inserts new
station/timestamp keys. It never overwrites existing measurements or imports
future-dated rows returned by the upstream service.
"""

from contextlib import closing
from datetime import datetime, timedelta
from io import StringIO
import math
import time
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from psycopg2.extras import execute_values

from backend.database import get_connection


BASE_URL = "http://203.209.181.170:2018/API_TTB/XUAT/solieu.php"
TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")
SOURCE = "professor_hydrology_api"
LOOKBACK_HOURS = 48
REQUEST_DELAY_SECONDS = 0.25
REQUEST_TIMEOUT_SECONDS = 20

INSERT_SQL = """
    INSERT INTO hydrology_observations (station_id, timestamp, value, source)
    VALUES %s
    ON CONFLICT (station_id, timestamp) DO NOTHING
"""


def active_station_watermarks(connection):
    """Return active hydrology station IDs and their latest stored timestamps."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT s.station_id, MAX(h.timestamp)
            FROM stations AS s
            LEFT JOIN hydrology_observations AS h
                ON h.station_id = s.station_id
            WHERE s.station_type = 'hydrology'
              AND s.is_active = TRUE
            GROUP BY s.station_id
            ORDER BY s.station_id
            """
        )
        return [(str(station_id).strip(), latest) for station_id, latest in cursor.fetchall()]


def request_window(now, latest_timestamp):
    """Choose a completed-hour API window that can repair recent gaps."""
    local_now = now.astimezone(TIMEZONE)
    end = local_now.replace(minute=0, second=0, microsecond=0)
    lower_bound = end - timedelta(hours=LOOKBACK_HOURS)
    if latest_timestamp is not None:
        latest_local = latest_timestamp.astimezone(TIMEZONE)
        lower_bound = max(lower_bound, latest_local - timedelta(hours=1))
    start = lower_bound.replace(minute=0, second=0, microsecond=0)
    return start, end


def parse_station_response(response_text, station_id, start, end, now):
    """Parse the source's HTML table and return safe, local-time measurements."""
    tables = pd.read_html(StringIO(response_text))
    required = {"Ma Tram", "thoi gian", "so lieu"}
    if not tables or not required.issubset(tables[0].columns):
        raise ValueError(f"Unexpected hydrology table for station {station_id}.")

    frame = tables[0].rename(
        columns={"Ma Tram": "station_id", "thoi gian": "timestamp", "so lieu": "value"}
    )
    frame["station_id"] = frame["station_id"].astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
    if (frame["station_id"] != station_id).any():
        raise ValueError(f"Source returned a different station ID for {station_id}.")

    timestamps = pd.to_datetime(frame["timestamp"], errors="coerce")
    if timestamps.isna().any() or timestamps.duplicated().any():
        raise ValueError(f"Invalid or duplicate timestamps for station {station_id}.")
    if timestamps.dt.tz is None:
        timestamps = timestamps.dt.tz_localize(
            TIMEZONE, ambiguous="raise", nonexistent="raise"
        )
    else:
        timestamps = timestamps.dt.tz_convert(TIMEZONE)

    values = pd.to_numeric(frame["value"], errors="coerce")
    eligible = (
        (timestamps >= pd.Timestamp(start))
        & (timestamps <= pd.Timestamp(end))
        & (timestamps <= pd.Timestamp(now.astimezone(TIMEZONE)))
        & values.notna()
    )
    records = []
    for timestamp, value in zip(timestamps[eligible], values[eligible]):
        numeric_value = float(value)
        if not math.isfinite(numeric_value):
            raise ValueError(f"Non-finite water level for station {station_id}.")
        records.append((station_id, timestamp.to_pydatetime(), numeric_value, SOURCE))
    return records


def fetch_station(session, station_id, start, end, now):
    params = {
        "matram": station_id,
        "ten_table": "mucnuoc_oday",
        "sophut": 60,
        "tinhtong": 0,
        "thoigianbd": f"'{start:%Y-%m-%d %H:%M}'",
        "thoigiankt": f"'{end:%Y-%m-%d %H:%M}'",
    }
    response = session.get(BASE_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return parse_station_response(response.text, station_id, start, end, now)


def persist_new_records(records, connection_factory=get_connection):
    """Insert new keys only, preserving any existing stored measurement."""
    if not records:
        return 0
    with closing(connection_factory()) as connection:
        with connection:
            with connection.cursor() as cursor:
                execute_values(cursor, INSERT_SQL, records, page_size=1000)
                return max(0, cursor.rowcount)


def refresh(*, session=None, connection_factory=get_connection, now=None, dry_run=False):
    now = now or datetime.now(TIMEZONE)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware.")

    with closing(connection_factory()) as connection:
        watermarks = active_station_watermarks(connection)

    if not watermarks:
        raise ValueError("No active hydrology stations are registered.")

    session = session or requests.Session()
    records = []
    failures = []
    stations_with_values = 0
    for index, (station_id, latest_timestamp) in enumerate(watermarks):
        start, end = request_window(now, latest_timestamp)
        try:
            station_records = fetch_station(session, station_id, start, end, now)
            records.extend(station_records)
            stations_with_values += bool(station_records)
        except (requests.RequestException, ValueError) as exc:
            failures.append({"station_id": station_id, "reason": str(exc)})
        if index + 1 < len(watermarks):
            time.sleep(REQUEST_DELAY_SECONDS)

    inserted = 0 if dry_run else persist_new_records(records, connection_factory)
    return {
        "status": "partial" if failures else "success",
        "active_station_count": len(watermarks),
        "stations_with_values": stations_with_values,
        "record_count": len(records),
        "inserted_count": inserted,
        "dry_run": dry_run,
        "failures": failures,
    }


def main(argv=None):
    import argparse
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Fetch and validate without writing rows.")
    args = parser.parse_args(argv)
    try:
        result = refresh(dry_run=args.dry_run)
    except Exception as exc:
        result = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps(result, indent=2))
    return 0 if result.get("status") == "success" else 1


def cli(argv=None):
    raise SystemExit(main(argv))


if __name__ == "__main__":
    cli()
