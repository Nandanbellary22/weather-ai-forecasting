import csv
import math
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


def _to_float(value):
    if value is None or value == "":
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_datetime(value):
    if value is None:
        return None

    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=SOURCE_TIMEZONE)

        return value.astimezone(SOURCE_TIMEZONE)

    return None


def _read_mrc_stations():
    if not MRC_STATIONS_FILE.exists():
        raise FileNotFoundError(
            f"MRC station metadata file not found: "
            f"{MRC_STATIONS_FILE}"
        )

    stations = []

    with MRC_STATIONS_FILE.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        reader = csv.DictReader(file)

        for row in reader:
            latitude = _to_float(row.get("latitude"))
            longitude = _to_float(row.get("longitude"))

            if latitude is None or longitude is None:
                continue

            stations.append(
                {
                    "station_id": str(
                        row.get("station_id", "")
                    ).strip().zfill(6),
                    "station_name": (
                        row.get("station_name")
                        or None
                    ),
                    "latitude": latitude,
                    "longitude": longitude,
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
                    "flood_stage": _to_float(
                        row.get("flood_stage")
                    ),
                    "alarm_stage": _to_float(
                        row.get("alarm_stage")
                    ),
                }
            )

    return stations


def _haversine_distance_km(
    latitude_1,
    longitude_1,
    latitude_2,
    longitude_2,
):
    """
    Calculate great-circle distance between two
    geographic coordinates.

    Returns distance in kilometres.
    """

    earth_radius_km = 6371.0088

    lat1 = math.radians(latitude_1)
    lon1 = math.radians(longitude_1)
    lat2 = math.radians(latitude_2)
    lon2 = math.radians(longitude_2)

    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1)
        * math.cos(lat2)
        * math.sin(delta_lon / 2) ** 2
    )

    c = 2 * math.atan2(
        math.sqrt(a),
        math.sqrt(1 - a),
    )

    return earth_radius_km * c


def _get_latest_mrc_telemetry(station_id):
    query = """
        SELECT
            water_level,
            rainfall,
            temperature,
            battery,
            timestamp_utc
        FROM mrc_hydromet_observations
        WHERE station_id = %s
        ORDER BY timestamp_utc DESC
        LIMIT 1;
    """

    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                (station_id,),
            )

            row = cursor.fetchone()

        if row is None:
            return {
                "water_level": None,
                "rainfall": None,
                "temperature": None,
                "battery": None,
                "timestamp": None,
            }

        return {
            "water_level": (
                float(row[0])
                if row[0] is not None
                else None
            ),
            "rainfall": (
                float(row[1])
                if row[1] is not None
                else None
            ),
            "temperature": (
                float(row[2])
                if row[2] is not None
                else None
            ),
            "battery": (
                float(row[3])
                if row[3] is not None
                else None
            ),
            "timestamp": _to_datetime(row[4]),
        }

    finally:
        connection.close()


def _get_discharge_summary(station_name):
    query = """
        SELECT
            COUNT(*) AS observations,
            MIN(observation_date) AS first_date,
            MAX(observation_date) AS last_date,
            MIN(discharge_m3s) AS minimum_discharge,
            MAX(discharge_m3s) AS maximum_discharge
        FROM mekong_discharge_observations
        WHERE station_name = %s;
    """

    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                (station_name,),
            )

            row = cursor.fetchone()

        if row is None or row[0] == 0:
            return {
                "available": False,
                "observations": 0,
                "first_date": None,
                "last_date": None,
                "minimum_discharge_m3s": None,
                "maximum_discharge_m3s": None,
            }

        return {
            "available": True,
            "observations": int(row[0]),
            "first_date": row[1],
            "last_date": row[2],
            "minimum_discharge_m3s": (
                float(row[3])
                if row[3] is not None
                else None
            ),
            "maximum_discharge_m3s": (
                float(row[4])
                if row[4] is not None
                else None
            ),
        }

    finally:
        connection.close()


def get_nearest_mrc_station(
    latitude,
    longitude,
):
    """
    Find the geographically nearest MRC Vietnam station
    to the requested coordinate.

    The result combines:
    - MRC station metadata
    - geographic distance
    - latest MRC telemetry
    - historical discharge availability
    """

    stations = _read_mrc_stations()

    if not stations:
        raise ValueError(
            "No georeferenced MRC stations are available."
        )

    nearest_station = None
    nearest_distance = None

    for station in stations:
        distance = _haversine_distance_km(
            latitude,
            longitude,
            station["latitude"],
            station["longitude"],
        )

        if (
            nearest_distance is None
            or distance < nearest_distance
        ):
            nearest_distance = distance
            nearest_station = station

    station_id = nearest_station["station_id"]
    station_name = nearest_station["station_name"]

    telemetry = _get_latest_mrc_telemetry(
        station_id
    )

    discharge = _get_discharge_summary(
        station_name
    )

    return {
        "requested_latitude": float(latitude),
        "requested_longitude": float(longitude),

        "station_id": station_id,
        "station_name": station_name,

        "station_latitude": nearest_station[
            "latitude"
        ],
        "station_longitude": nearest_station[
            "longitude"
        ],

        "river": nearest_station["river"],
        "country": nearest_station["country"],
        "station_type": nearest_station[
            "station_type"
        ],

        "distance_km": round(
            nearest_distance,
            3,
        ),

        "water_level": telemetry[
            "water_level"
        ],
        "rainfall": telemetry[
            "rainfall"
        ],
        "temperature": telemetry[
            "temperature"
        ],
        "battery": telemetry[
            "battery"
        ],
        "latest_measurement": telemetry[
            "timestamp"
        ],

        "flood_stage": nearest_station[
            "flood_stage"
        ],
        "alarm_stage": nearest_station[
            "alarm_stage"
        ],

        "discharge_available": discharge[
            "available"
        ],
        "discharge_observations": discharge[
            "observations"
        ],
        "discharge_first_date": discharge[
            "first_date"
        ],
        "discharge_last_date": discharge[
            "last_date"
        ],
        "minimum_discharge_m3s": discharge[
            "minimum_discharge_m3s"
        ],
        "maximum_discharge_m3s": discharge[
            "maximum_discharge_m3s"
        ],
    }