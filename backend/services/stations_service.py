import os

import psycopg2


def get_connection():
    """Create a PostgreSQL connection."""

    return psycopg2.connect(
        host="localhost",
        database="weather_forecasting",
        user="postgres",
        password=os.getenv("POSTGRES_PASSWORD"),
    )


def get_station_summary():
    """
    Return station metadata together with observation statistics.

    Station metadata comes from the stations table.
    Observation statistics come from hydrology_observations.
    """

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
                cursor.execute(latest_query, (str(station_id),))
                latest_row = cursor.fetchone()

            latest_value = None

            if latest_row is not None:
                latest_value = float(latest_row[0])

            results.append(
                {
                    "station_id": str(station_id),
                    "station_name": station_name,
                    "station_type": station_type,
                    "latitude": (
                        float(latitude)
                        if latitude is not None
                        else None
                    ),
                    "longitude": (
                        float(longitude)
                        if longitude is not None
                        else None
                    ),
                    "source": source,
                    "is_active": bool(is_active),
                    "observations": int(observations),
                    "valid_observations": int(valid_observations),
                    "missing_values": int(missing_values),
                    "start_time": start_time,
                    "end_time": end_time,
                    "latest_value": latest_value,
                }
            )

        return results

    finally:
        connection.close()