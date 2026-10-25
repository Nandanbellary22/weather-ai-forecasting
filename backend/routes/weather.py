
import csv
import json
import os
from pathlib import Path

import psycopg2
import requests
from fastapi import APIRouter, HTTPException, Query


router = APIRouter(
    prefix="/weather",
    tags=["Weather"],
)

OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_TIMEOUT_SECONDS = 20

RECENT_WEATHER_VARIABLES = [
    "temperature_2m",
    "relative_humidity_2m",
    "dew_point_2m",
    "precipitation",
    "rain",
    "pressure_msl",
    "surface_pressure",
    "cloud_cover",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
]


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
    Return weather locations with their latest database records.

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
                    precipitation_mm,
                    relative_humidity_2m,
                    dew_point_2m,
                    pressure_msl,
                    surface_pressure_hpa,
                    wind_speed_10m,
                    wind_direction_10m,
                    wind_gusts_10m,
                    cloud_cover
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
                "relative_humidity_2m": row[6],
                "dew_point_2m": row[7],
                "pressure_msl": row[8],
                "surface_pressure_hpa": row[9],
                "wind_speed_10m": row[10],
                "wind_direction_10m": row[11],
                "wind_gusts_10m": row[12],
                "cloud_cover": row[13],
            }
            for row in rows
        ]

    finally:
        conn.close()


@router.get("/recent/{location_code}")
def get_recent_weather(location_code: str):
    """
    Fetch recent hourly weather and the next 24-hour forecast from Open-Meteo.

    These are external weather-model outputs, not verified local-station
    observations. This endpoint does not write to PostgreSQL or model files.
    """
    requested_code = location_code.strip().upper()

    if not requested_code:
        raise HTTPException(
            status_code=400,
            detail="A non-empty location code is required.",
        )

    conn = get_db_connection()

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT latitude, longitude
                FROM weather_observations
                WHERE UPPER(location_code) = %s
                  AND latitude IS NOT NULL
                  AND longitude IS NOT NULL
                ORDER BY timestamp DESC
                LIMIT 1;
                """,
                (requested_code,),
            )
            location_row = cur.fetchone()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Could not look up the requested weather location.",
        ) from exc
    finally:
        conn.close()

    if location_row is None:
        raise HTTPException(
            status_code=404,
            detail=f"No coordinates found for location {requested_code}.",
        )

    latitude, longitude = location_row

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": ",".join(RECENT_WEATHER_VARIABLES),
        "past_hours": 24,
        "forecast_hours": 24,
        "timezone": "Asia/Ho_Chi_Minh",
        "temperature_unit": "celsius",
        "wind_speed_unit": "kmh",
        "precipitation_unit": "mm",
    }

    try:
        response = requests.get(
            OPEN_METEO_FORECAST_URL,
            params=params,
            timeout=OPEN_METEO_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502,
            detail="Open-Meteo could not be reached. Try again later.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail="Open-Meteo returned an invalid JSON response.",
        ) from exc

    hourly = payload.get("hourly")

    if not isinstance(hourly, dict) or not isinstance(hourly.get("time"), list):
        raise HTTPException(
            status_code=502,
            detail="Open-Meteo returned an unexpected hourly-data structure.",
        )

    timestamps = hourly["time"]
    expected_length = len(timestamps)

    if expected_length == 0:
        raise HTTPException(
            status_code=502,
            detail="Open-Meteo returned no hourly timestamps.",
        )

    for variable in RECENT_WEATHER_VARIABLES:
        values = hourly.get(variable)

        if not isinstance(values, list) or len(values) != expected_length:
            raise HTTPException(
                status_code=502,
                detail=f"Open-Meteo returned incomplete data for {variable}.",
            )

    hourly_records = []

    for index, timestamp in enumerate(timestamps):
        hourly_records.append(
            {
                "timestamp": timestamp,
                "temperature_c": hourly["temperature_2m"][index],
                "relative_humidity_2m": hourly["relative_humidity_2m"][index],
                "dew_point_c": hourly["dew_point_2m"][index],
                "precipitation_mm": hourly["precipitation"][index],
                "rain_mm": hourly["rain"][index],
                "pressure_msl_hpa": hourly["pressure_msl"][index],
                "surface_pressure_hpa": hourly["surface_pressure"][index],
                "cloud_cover_percent": hourly["cloud_cover"][index],
                "wind_speed_kmh": hourly["wind_speed_10m"][index],
                "wind_direction_degrees": hourly["wind_direction_10m"][index],
                "wind_gusts_kmh": hourly["wind_gusts_10m"][index],
            }
        )

    return {
        "location_code": requested_code,
        "latitude": payload.get("latitude", latitude),
        "longitude": payload.get("longitude", longitude),
        "timezone": payload.get("timezone", "Asia/Ho_Chi_Minh"),
        "source": "Open-Meteo",
        "data_type": "weather_model_output",
        "is_verified_station_observation": False,
        "database_modified": False,
        "model_files_modified": False,
        "requested_past_hours": 24,
        "requested_forecast_hours": 24,
        "returned_hour_count": len(hourly_records),
        "hourly": hourly_records,
        "notice": (
            "Data are provided by Open-Meteo weather models. "
            "Past timestamps do not by themselves establish that values "
            "are measured observations from a local weather station."
        ),
    }


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


@router.get("/temperature-candidate")
def get_temperature_candidate(
    location_code: str | None = Query(default=None),
):
    """Read-only access to experimental candidate predictions."""

    project_root = Path(__file__).resolve().parents[2]
    candidate_dir = (
        project_root
        / "models"
        / "weather"
        / "candidate_temperature_hybrid"
    )
    predictions_path = candidate_dir / "latest_500_predictions.csv"
    report_path = candidate_dir / "bulk_inference_report.json"

    if not predictions_path.is_file() or not report_path.is_file():
        raise HTTPException(
            status_code=503,
            detail=(
                "Candidate predictions are not available. "
                "Run the candidate inference script first."
            ),
        )

    try:
        with report_path.open("r", encoding="utf-8") as file:
            report = json.load(file)

        if report.get("status") != "candidate_inference_completed":
            raise ValueError("Candidate inference report is not complete.")

        predictions = []
        requested_code = (
            location_code.strip().upper()
            if location_code and location_code.strip()
            else None
        )

        with predictions_path.open(
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as file:
            reader = csv.DictReader(file)
            required = {
                "location_code",
                "source_timestamp",
                "selection_rule",
                "current_temperature",
                "mlp_prediction",
                "hybrid_prediction",
                "calibration_alpha",
            }

            if not required.issubset(set(reader.fieldnames or [])):
                raise ValueError(
                    "Candidate prediction CSV has an unexpected schema."
                )

            for row in reader:
                code = row["location_code"].strip().upper()

                if requested_code and code != requested_code:
                    continue

                predictions.append(
                    {
                        "location_code": code,
                        "source_timestamp": row["source_timestamp"],
                        "selection_rule": row["selection_rule"],
                        "current_temperature_c": float(
                            row["current_temperature"]
                        ),
                        "mlp_prediction_c": float(row["mlp_prediction"]),
                        "hybrid_prediction_c": float(row["hybrid_prediction"]),
                        "calibration_alpha": float(row["calibration_alpha"]),
                    }
                )

        if requested_code and not predictions:
            raise HTTPException(
                status_code=404,
                detail=(
                    "No candidate prediction found for location "
                    f"{requested_code}."
                ),
            )

        return {
            "status": "experimental_candidate",
            "production_model_modified": False,
            "forecast_validation": "not_independently_verified",
            "source_timestamp": report.get("latest_source_timestamp"),
            "source_data_age_hours": report.get("source_data_age_hours"),
            "source_data_stale": report.get("source_data_stale", True),
            "locations_returned": len(predictions),
            "warning": (
                "Experimental candidate only. Source data may be stale; "
                "these values are not verified live forecasts."
            ),
            "predictions": predictions,
        }

    except HTTPException:
        raise
    except (OSError, ValueError, TypeError, KeyError, csv.Error) as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Candidate predictions could not be read safely: {exc}",
        ) from exc
