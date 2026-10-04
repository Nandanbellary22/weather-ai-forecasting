from fastapi import APIRouter, HTTPException, Query
import os

import psycopg2


router = APIRouter(
    prefix="/weather",
    tags=["Weather"],
)


def get_db_connection():
    return psycopg2.connect(
        host="localhost",
        port=5432,
        database="weather_forecasting",
        user="postgres",
        password=os.getenv("PGPASSWORD"),
    )


@router.get("/locations")
def get_weather_locations(
    limit: int = Query(
        default=500,
        ge=1,
        le=1000,
        description="Maximum number of weather locations to return.",
    ),
):
    """
    Return weather locations with their latest observations.

    Used by the WebGIS frontend to display the Vietnam weather grid.
    """

    conn = get_db_connection()

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT ON (location_code)
                    location_code,
                    latitude,
                    longitude,
                    timestamp,
                    temperature_2m,
                    precipitation_mm
                FROM weather_observations
                WHERE latitude IS NOT NULL
                  AND longitude IS NOT NULL
                ORDER BY location_code, timestamp DESC
                LIMIT %s;
                """,
                (limit,),
            )

            rows = cur.fetchall()

        return [
            {
                "location_code": row[0],
                "latitude": row[1],
                "longitude": row[2],
                "timestamp": row[3],
                "temperature_c": row[4],
                "rainfall_mm": row[5],
            }
            for row in rows
        ]

    finally:
        conn.close()


@router.get("/temperature/{location_code}")
def get_temperature_forecast(location_code: str):
    try:
        from ml.services.temperature_service import (
            predict_next_hour_temperature,
        )

        return predict_next_hour_temperature(
            location_code=location_code,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc


@router.get("/rainfall/{location_code}")
def get_rainfall_forecast(location_code: str):
    try:
        from ml.services.rainfall_service import (
            predict_next_hour_rainfall,
        )

        return predict_next_hour_rainfall(
            location_code=location_code,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc