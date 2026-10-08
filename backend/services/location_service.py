import os
from math import (
    atan2,
    cos,
    radians,
    sin,
    sqrt,
)
from pathlib import Path

import psycopg2


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def get_connection():
    return psycopg2.connect(
        host="localhost",
        port=5432,
        database="weather_forecasting",
        user="postgres",
        password=os.getenv("PGPASSWORD"),
    )


def _haversine_distance_km(
    latitude_1,
    longitude_1,
    latitude_2,
    longitude_2,
):
    earth_radius_km = 6371.0088

    lat1 = radians(latitude_1)
    lon1 = radians(longitude_1)
    lat2 = radians(latitude_2)
    lon2 = radians(longitude_2)

    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1

    a = (
        sin(delta_lat / 2) ** 2
        + cos(lat1)
        * cos(lat2)
        * sin(delta_lon / 2) ** 2
    )

    c = 2 * atan2(
        sqrt(a),
        sqrt(1 - a),
    )

    return earth_radius_km * c


def _get_weather_location(location_code):
    query = """
        SELECT
            location_code,
            latitude,
            longitude,
            timestamp,
            temperature_2m,
            precipitation_mm,
            relative_humidity_2m,
            surface_pressure_hpa,
            wind_speed_10m,
            cloud_cover,
            dew_point_2m,
            rain
        FROM weather_observations
        WHERE location_code = %s
        ORDER BY timestamp DESC
        LIMIT 1;
    """

    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                (location_code,),
            )

            row = cursor.fetchone()

        if row is None:
            return None

        return {
            "location_code": row[0],
            "latitude": float(row[1]),
            "longitude": float(row[2]),
            "timestamp": row[3],
            "temperature_c": (
                float(row[4])
                if row[4] is not None
                else None
            ),
            "rainfall_mm": (
                float(row[5])
                if row[5] is not None
                else None
            ),
            "relative_humidity": (
                float(row[6])
                if row[6] is not None
                else None
            ),
            "surface_pressure_hpa": (
                float(row[7])
                if row[7] is not None
                else None
            ),
            "wind_speed_10m": (
                float(row[8])
                if row[8] is not None
                else None
            ),
            "cloud_cover": (
                float(row[9])
                if row[9] is not None
                else None
            ),
            "dew_point_c": (
                float(row[10])
                if row[10] is not None
                else None
            ),
            "rain": (
                float(row[11])
                if row[11] is not None
                else None
            ),
        }

    finally:
        connection.close()


def _get_nearest_mrc(
    latitude,
    longitude,
):
    from backend.services.spatial_service import (
        get_nearest_mrc_station,
    )

    return get_nearest_mrc_station(
        latitude=latitude,
        longitude=longitude,
    )


def _get_weather_forecasts(location_code):
    temperature_forecast = None
    rainfall_forecast = None

    try:
        from ml.services.temperature_service import (
            predict_next_hour_temperature,
        )

        temperature_forecast = (
            predict_next_hour_temperature(
                location_code=location_code,
            )
        )
    except Exception:
        temperature_forecast = None

    try:
        from ml.services.rainfall_service import (
            predict_next_hour_rainfall,
        )

        rainfall_forecast = (
            predict_next_hour_rainfall(
                location_code=location_code,
            )
        )
    except Exception:
        rainfall_forecast = None

    return {
        "temperature": temperature_forecast,
        "rainfall": rainfall_forecast,
    }


def _get_data_status(
    weather,
    forecasts,
    nearest_mrc,
):
    temperature_forecast = forecasts.get(
        "temperature"
    )

    rainfall_forecast = forecasts.get(
        "rainfall"
    )

    return {
        "weather_observation_available": (
            weather is not None
        ),
        "weather_observation_timestamp": (
            weather["timestamp"]
            if weather is not None
            else None
        ),
        "temperature_forecast_available": (
            temperature_forecast is not None
        ),
        "temperature_forecast_timestamp": (
            temperature_forecast.get("timestamp")
            if isinstance(
                temperature_forecast,
                dict,
            )
            else None
        ),
        "rainfall_forecast_available": (
            rainfall_forecast is not None
        ),
        "rainfall_forecast_timestamp": (
            rainfall_forecast.get("timestamp")
            if isinstance(
                rainfall_forecast,
                dict,
            )
            else None
        ),
        "mrc_observation_available": (
            nearest_mrc.get(
                "latest_measurement"
            )
            is not None
        ),
        "mrc_observation_timestamp": (
            nearest_mrc.get(
                "latest_measurement"
            )
        ),
        "historical_discharge_available": (
            nearest_mrc.get(
                "discharge_available",
                False,
            )
        ),
        "historical_discharge_first_date": (
            nearest_mrc.get(
                "discharge_first_date"
            )
        ),
        "historical_discharge_last_date": (
            nearest_mrc.get(
                "discharge_last_date"
            )
        ),
    }


def get_location_profile(location_code):
    """
    Build an integrated profile for one weather location.

    Combines:
    - latest weather observation
    - weather ML forecasts
    - nearest MRC station
    - MRC telemetry
    - historical discharge availability
    - explicit data timestamps/status
    """

    weather = _get_weather_location(
        location_code
    )

    if weather is None:
        raise ValueError(
            f"Weather location '{location_code}' "
            "was not found."
        )

    nearest_mrc = _get_nearest_mrc(
        latitude=weather["latitude"],
        longitude=weather["longitude"],
    )

    forecasts = _get_weather_forecasts(
        location_code
    )

    data_status = _get_data_status(
        weather=weather,
        forecasts=forecasts,
        nearest_mrc=nearest_mrc,
    )

    return {
        "location": weather,
        "weather_forecast": forecasts,
        "nearest_mrc": nearest_mrc,
        "data_status": data_status,
    }