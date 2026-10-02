import os
import psycopg2
from zoneinfo import ZoneInfo

SOURCE_TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")


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
    return timestamp.astimezone(SOURCE_TIMEZONE)


def get_station_summary():
    query = """
        SELECT
            s.station_id,
            s.station_name,
            s.station_type,
            s.latitude,
            s.longitude,
            s.source,
            s.is_active,
            COUNT(h.station_id) AS observations,
            COUNT(h.value) AS valid_observations,
            COUNT(h.station_id) - COUNT(h.value) AS missing_values,
            MIN(h.timestamp) AS start_time,
            MAX(h.timestamp) AS end_time
        FROM stations s
        LEFT JOIN hydrology_observations h
            ON s.station_id = h.station_id
        GROUP BY
            s.station_id,
            s.station_name,
            s.station_type,
            s.latitude,
            s.longitude,
            s.source,
            s.is_active
        ORDER BY s.station_id;
    """

    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()

        results = []

        for row in rows:
            (
                station_id,
                station_name,
                station_type,
                latitude,
                longitude,
                source,
                is_active,
                observations,
                valid_observations,
                missing_values,
                start_time,
                end_time,
            ) = row

            latest_query = """
                SELECT value
                FROM hydrology_observations
                WHERE station_id = %s
                  AND value IS NOT NULL
                ORDER BY timestamp DESC
                LIMIT 1;
            """

            with connection.cursor() as cursor:
                cursor.execute(latest_query, (station_id,))
                latest_row = cursor.fetchone()

            latest_value = latest_row[0] if latest_row else None

            results.append(
                {
                    "station_id": str(station_id),
                    "station_name": station_name,
                    "station_type": station_type,
                    "latitude": float(latitude) if latitude is not None else None,
                    "longitude": float(longitude) if longitude is not None else None,
                    "source": source,
                    "is_active": bool(is_active),
                    "observations": int(observations),
                    "valid_observations": int(valid_observations),
                    "missing_values": int(missing_values),
                    "start_time": convert_to_vietnam_time(start_time),
                    "end_time": convert_to_vietnam_time(end_time),
                    "latest_value": latest_value,
                }
            )

        return results

    finally:
        connection.close()


def get_station_history(station_id: str, limit: int = 168):
    query = """
        SELECT
            station_id,
            timestamp,
            value
        FROM hydrology_observations
        WHERE station_id = %s
        ORDER BY timestamp DESC
        LIMIT %s;
    """

    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(query, (station_id, limit))
            rows = cursor.fetchall()

        # Return chronological order for charts.
        rows.reverse()

        return [
            {
                "station_id": str(row[0]),
                "timestamp": convert_to_vietnam_time(row[1]),
                "value": float(row[2]) if row[2] is not None else None,
            }
            for row in rows
        ]

    finally:
        connection.close()