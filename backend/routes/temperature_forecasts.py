
import os
from datetime import datetime
from typing import Optional

import psycopg2
from fastapi import APIRouter, HTTPException, Query


router = APIRouter(
    prefix="/api/temperature-forecasts",
    tags=["Collected Temperature Forecasts"],
)


def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("PGHOST", "localhost"),
        port=int(os.getenv("PGPORT", "5432")),
        database=os.getenv("PGDATABASE", "weather_forecasting"),
        user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD"),
        connect_timeout=10,
    )


def latest_collection_time(cur):
    cur.execute(
        """
        SELECT MAX(collection_time_utc)
        FROM temperature_forecast_snapshots
        """
    )
    result = cur.fetchone()
    return result[0] if result else None


@router.get("/latest")
def get_latest_temperature_forecasts(
    limit: int = Query(default=500, ge=1, le=500),
    target_time: Optional[datetime] = Query(
        default=None,
        description=(
            "Optional target forecast time. Supply an ISO 8601 timestamp "
            "with timezone offset, for example +07:00."
        ),
    ),
):
    """Return the latest collected forecast for each location and target time."""

    if target_time is not None and (
        target_time.tzinfo is None or target_time.utcoffset() is None
    ):
        raise HTTPException(
            status_code=400,
            detail="target_time must include a timezone offset.",
        )

    conn = None

    try:
        conn = get_db_connection()

        with conn.cursor() as cur:
            collection_time = latest_collection_time(cur)

            if collection_time is None:
                return {
                    "status": "no_data",
                    "source": None,
                    "collection_time_utc": None,
                    "locations_returned": 0,
                    "forecasts": [],
                }

            if target_time is None:
                cur.execute(
                    """
                    SELECT DISTINCT ON (location_id)
                        location_id,
                        location_name,
                        requested_latitude,
                        requested_longitude,
                        returned_latitude,
                        returned_longitude,
                        target_time_local,
                        timezone,
                        source,
                        forecast_temperature_c
                    FROM temperature_forecast_snapshots
                    WHERE collection_time_utc = %s
                    ORDER BY location_id, target_time_local ASC
                    LIMIT %s
                    """,
                    (collection_time, limit),
                )
            else:
                cur.execute(
                    """
                    SELECT
                        location_id,
                        location_name,
                        requested_latitude,
                        requested_longitude,
                        returned_latitude,
                        returned_longitude,
                        target_time_local,
                        timezone,
                        source,
                        forecast_temperature_c
                    FROM temperature_forecast_snapshots
                    WHERE collection_time_utc = %s
                      AND target_time_local = %s
                    ORDER BY location_id
                    LIMIT %s
                    """,
                    (
                        collection_time,
                        target_time.replace(tzinfo=None),
                        limit,
                    ),
                )

            rows = cur.fetchall()

        forecasts = [
            {
                "location_id": row[0],
                "location_name": row[1],
                "latitude": row[2],
                "longitude": row[3],
                "returned_latitude": row[4],
                "returned_longitude": row[5],
                "target_time_local": row[6].isoformat(),
                "timezone": row[7],
                "source": row[8],
                "temperature_c": row[9],
            }
            for row in rows
        ]

        return {
            "status": "ok",
            "source": forecasts[0]["source"] if forecasts else None,
            "collection_time_utc": collection_time.isoformat(),
            "locations_returned": len(forecasts),
            "forecasts": forecasts,
        }

    except psycopg2.Error as exc:
        raise HTTPException(
            status_code=503,
            detail="Could not read collected temperature forecasts from PostgreSQL.",
        ) from exc

    finally:
        if conn is not None:
            conn.close()


@router.get("/locations")
def get_forecast_locations():
    """List locations present in the latest collected snapshot."""

    conn = None

    try:
        conn = get_db_connection()

        with conn.cursor() as cur:
            collection_time = latest_collection_time(cur)

            if collection_time is None:
                return {
                    "status": "no_data",
                    "locations_returned": 0,
                    "locations": [],
                }

            cur.execute(
                """
                SELECT
                    location_id,
                    MAX(location_name) AS location_name,
                    MAX(requested_latitude) AS latitude,
                    MAX(requested_longitude) AS longitude
                FROM temperature_forecast_snapshots
                WHERE collection_time_utc = %s
                GROUP BY location_id
                ORDER BY location_id
                """,
                (collection_time,),
            )

            rows = cur.fetchall()

        locations = [
            {
                "location_id": row[0],
                "location_name": row[1],
                "latitude": row[2],
                "longitude": row[3],
            }
            for row in rows
        ]

        return {
            "status": "ok",
            "collection_time_utc": collection_time.isoformat(),
            "locations_returned": len(locations),
            "locations": locations,
        }

    except psycopg2.Error as exc:
        raise HTTPException(
            status_code=503,
            detail="Could not read forecast locations from PostgreSQL.",
        ) from exc

    finally:
        if conn is not None:
            conn.close()


@router.get("/{location_id}")
def get_location_temperature_forecast(
    location_id: str,
    limit: int = Query(default=48, ge=1, le=48),
):
    """Return the latest collected forecast timeline for one location."""

    conn = None

    try:
        conn = get_db_connection()

        with conn.cursor() as cur:
            collection_time = latest_collection_time(cur)

            if collection_time is None:
                raise HTTPException(
                    status_code=404,
                    detail="No collected temperature forecasts are available.",
                )

            cur.execute(
                """
                SELECT
                    location_id,
                    location_name,
                    requested_latitude,
                    requested_longitude,
                    target_time_local,
                    timezone,
                    source,
                    forecast_temperature_c
                FROM temperature_forecast_snapshots
                WHERE collection_time_utc = %s
                  AND location_id = %s
                ORDER BY target_time_local ASC
                LIMIT %s
                """,
                (collection_time, location_id.strip(), limit),
            )

            rows = cur.fetchall()

        if not rows:
            raise HTTPException(
                status_code=404,
                detail=f"No forecasts found for location {location_id}.",
            )

        return {
            "status": "ok",
            "location_id": rows[0][0],
            "location_name": rows[0][1],
            "latitude": rows[0][2],
            "longitude": rows[0][3],
            "timezone": rows[0][5],
            "source": rows[0][6],
            "collection_time_utc": collection_time.isoformat(),
            "forecast_count": len(rows),
            "forecasts": [
                {
                    "target_time_local": row[4].isoformat(),
                    "temperature_c": row[7],
                }
                for row in rows
            ],
        }

    except psycopg2.Error as exc:
        raise HTTPException(
            status_code=503,
            detail="Could not read the location forecast from PostgreSQL.",
        ) from exc

    finally:
        if conn is not None:
            conn.close()
