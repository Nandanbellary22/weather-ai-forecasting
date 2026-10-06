import csv
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import psycopg2


SOURCE_TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")

PROJECT_ROOT = Path(__file__).resolve().parents[2]

MRC_STATIONS_FILE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "mrc_vietnam_stations.csv"
)


def get_connection():
    return psycopg2.connect(
        host="localhost",
        database="weather_forecasting",
        user="postgres",
        password=os.getenv("PGPASSWORD"),
    )


def convert_to_vietnam_time(timestamp):
    if timestamp is None:
        return None

    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(
            tzinfo=ZoneInfo("UTC")
        )

    return timestamp.astimezone(SOURCE_TIMEZONE)


def _to_float(value):
    if value is None or value == "":
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_bool(value):
    if value is None:
        return False

    return str(value).strip().lower() in {
        "true",
        "1",
        "yes",
    }


def _to_datetime(value):
    if value is None or value == "":
        return None

    try:
        parsed = datetime.fromisoformat(value)

        if parsed.tzinfo is None:
            parsed = parsed.replace(
                tzinfo=SOURCE_TIMEZONE
            )

        return parsed

    except ValueError:
        return None


def _read_station_metadata():
    if not MRC_STATIONS_FILE.exists():
        raise FileNotFoundError(
            f"MRC station metadata file not found: "
            f"{MRC_STATIONS_FILE}"
        )

    with MRC_STATIONS_FILE.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        reader = csv.DictReader(file)

        rows = []

        for row in reader:
            rows.append(
                {
                    "station_id": str(
                        row.get("station_id", "")
                    ).zfill(6),

                    "station_name": (
                        row.get("station_name")
                        or None
                    ),

                    "latitude": _to_float(
                        row.get("latitude")
                    ),

                    "longitude": _to_float(
                        row.get("longitude")
                    ),

                    "river": (
                        row.get("river")
                        or None
                    ),

                    "country": (
                        row.get("country")
                        or None
                    ),

                    "station_type": (
                        row.get("station_type")
                        or None
                    ),

                    "water_level": _to_float(
                        row.get("water_level")
                    ),

                    "rainfall": _to_float(
                        row.get("rainfall")
                    ),

                    "rainfall_1h": _to_float(
                        row.get("rainfall_1h")
                    ),

                    "rainfall_6h": _to_float(
                        row.get("rainfall_6h")
                    ),

                    "rainfall_12h": _to_float(
                        row.get("rainfall_12h")
                    ),

                    "rainfall_24h": _to_float(
                        row.get("rainfall_24h")
                    ),

                    "rainfall_7to7": _to_float(
                        row.get("rainfall_7to7")
                    ),

                    "flood_stage": _to_float(
                        row.get("flood_stage")
                    ),

                    "alarm_stage": _to_float(
                        row.get("alarm_stage")
                    ),

                    "mean_sea_level": _to_float(
                        row.get("mean_sea_level")
                    ),

                    "water_level_sensor": _to_bool(
                        row.get("water_level_sensor")
                    ),

                    "rainfall_sensor": _to_bool(
                        row.get("rainfall_sensor")
                    ),

                    "temperature_sensor": _to_bool(
                        row.get("temperature_sensor")
                    ),

                    "battery_sensor": _to_bool(
                        row.get("battery_sensor")
                    ),

                    "success_rate": _to_float(
                        row.get("success_rate")
                    ),

                    "last_status": (
                        row.get("last_status")
                        or None
                    ),

                    "last_measurement": _to_datetime(
                        row.get("last_measurement")
                    ),

                    "telemetry_available": _to_bool(
                        row.get("telemetry_available")
                    ),

                    "temperature": None,
                    "battery": None,
                }
            )

    rows.sort(
        key=lambda item: item["station_id"]
    )

    return rows


def _get_latest_telemetry():
    query = """
        SELECT DISTINCT ON (station_id)
            station_id,
            water_level,
            rainfall,
            temperature,
            battery,
            timestamp_utc
        FROM mrc_hydromet_observations
        ORDER BY
            station_id,
            timestamp_utc DESC;
    """

    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()

        latest = {}

        for row in rows:
            station_id = str(row[0]).zfill(6)

            latest[station_id] = {
                "water_level": (
                    float(row[1])
                    if row[1] is not None
                    else None
                ),
                "rainfall": (
                    float(row[2])
                    if row[2] is not None
                    else None
                ),
                "temperature": (
                    float(row[3])
                    if row[3] is not None
                    else None
                ),
                "battery": (
                    float(row[4])
                    if row[4] is not None
                    else None
                ),
                "timestamp": convert_to_vietnam_time(
                    row[5]
                ),
            }

        return latest

    finally:
        connection.close()


def get_mrc_stations():
    """
    Return all Vietnam MRC stations.

    Station metadata comes from the MRC collector output.
    Latest telemetry values are taken from PostgreSQL.
    Stations without telemetry remain in the response.
    """

    stations = _read_station_metadata()
    latest = _get_latest_telemetry()

    results = []

    for station in stations:
        station_id = station["station_id"]

        telemetry = latest.get(
            station_id,
            {},
        )

        station["temperature"] = telemetry.get(
            "temperature"
        )

        station["battery"] = telemetry.get(
            "battery"
        )

        if telemetry.get("water_level") is not None:
            station["water_level"] = telemetry[
                "water_level"
            ]

        if telemetry.get("rainfall") is not None:
            station["rainfall"] = telemetry[
                "rainfall"
            ]

        if telemetry.get("timestamp") is not None:
            station["last_measurement"] = telemetry[
                "timestamp"
            ]

        results.append(station)

    return results


def get_mrc_station_history(
    station_id: str,
    limit: int = 168,
):
    """
    Return chronological MRC observations for one station.
    """

    station_id = (
        str(station_id)
        .strip()
        .zfill(6)
    )

    if limit < 1:
        limit = 1

    if limit > 1000:
        limit = 1000

    query = """
        SELECT
            station_id,
            timestamp_utc,
            water_level,
            rainfall,
            temperature,
            battery
        FROM mrc_hydromet_observations
        WHERE station_id = %s
        ORDER BY timestamp_utc DESC
        LIMIT %s;
    """

    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                (
                    station_id,
                    limit,
                ),
            )

            rows = cursor.fetchall()

        rows.reverse()

        return [
            {
                "station_id": str(
                    row[0]
                ).zfill(6),

                "timestamp": convert_to_vietnam_time(
                    row[1]
                ),

                "water_level": (
                    float(row[2])
                    if row[2] is not None
                    else None
                ),

                "rainfall": (
                    float(row[3])
                    if row[3] is not None
                    else None
                ),

                "temperature": (
                    float(row[4])
                    if row[4] is not None
                    else None
                ),

                "battery": (
                    float(row[5])
                    if row[5] is not None
                    else None
                ),
            }
            for row in rows
        ]

    finally:
        connection.close()