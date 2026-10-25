
import os
from datetime import date, datetime
from typing import Any

import pandas as pd

from ml.services.rainfall_service import (
    load_features as load_rainfall_features,
    predict_next_hour_rainfall,
)
from ml.services.temperature_service import (
    load_features as load_temperature_features,
    predict_next_hour_temperature,
)

DEFAULT_MAX_DATA_AGE_HOURS = 3


def _serialize_timestamp(result: dict[str, Any]) -> dict[str, Any]:
    """Convert timestamps into JSON-friendly ISO strings."""
    output = dict(result)
    timestamp = output.get("timestamp")

    if isinstance(timestamp, (datetime, date)):
        output["timestamp"] = timestamp.isoformat()
    elif hasattr(timestamp, "isoformat"):
        output["timestamp"] = timestamp.isoformat()

    return output


def _latest_timestamp(location_code: str) -> pd.Timestamp | None:
    """Return the newest timestamp shared by both weather datasets."""
    temperature = load_temperature_features()
    rainfall = load_rainfall_features()

    temperature_rows = temperature.loc[
        temperature["location_code"].astype(str).str.upper()
        == location_code
    ]
    rainfall_rows = rainfall.loc[
        rainfall["location_code"].astype(str).str.upper()
        == location_code
    ]

    if temperature_rows.empty or rainfall_rows.empty:
        return None

    temperature_latest = pd.to_datetime(
        temperature_rows["timestamp"], errors="coerce"
    ).max()
    rainfall_latest = pd.to_datetime(
        rainfall_rows["timestamp"], errors="coerce"
    ).max()

    if pd.isna(temperature_latest) or pd.isna(rainfall_latest):
        return None

    # A combined weather result is only as fresh as its oldest input.
    return min(
        pd.Timestamp(temperature_latest),
        pd.Timestamp(rainfall_latest),
    )


def run_weather_agent(
    location_code: str,
    max_data_age_hours: float | None = None,
) -> dict[str, Any]:
    """
    Run existing temperature and rainfall predictors.

    The response includes data freshness information. Stale data
    is flagged rather than silently presented as current.
    """
    if not isinstance(location_code, str) or not location_code.strip():
        raise ValueError("location_code must be a non-empty string.")

    location_code = location_code.strip().upper()

    if max_data_age_hours is None:
        max_data_age_hours = float(
            os.getenv(
                "WEATHER_AGENT_MAX_DATA_AGE_HOURS",
                DEFAULT_MAX_DATA_AGE_HOURS,
            )
        )

    if max_data_age_hours < 0:
        raise ValueError("max_data_age_hours cannot be negative.")

    predictions: dict[str, Any] = {}
    errors: dict[str, dict[str, str]] = {}

    services = {
        "temperature": predict_next_hour_temperature,
        "rainfall": predict_next_hour_rainfall,
    }

    for name, predict in services.items():
        try:
            predictions[name] = _serialize_timestamp(
                predict(location_code)
            )
        except Exception as exc:
            errors[name] = {
                "error_type": type(exc).__name__,
                "message": str(exc),
            }

    successful_count = len(predictions)

    if successful_count == len(services):
        status = "success"
    elif successful_count > 0:
        status = "partial"
    else:
        status = "failed"

    data_timestamp = None
    age_hours = None
    freshness = "unknown"

    try:
        latest = _latest_timestamp(location_code)

        if latest is not None:
            # Feature timestamps are currently naive local timestamps.
            # Compare them to the system's local wall clock without
            # silently treating them as UTC.
            now = pd.Timestamp.now()

            if latest.tzinfo is not None:
                now = now.tz_localize(latest.tzinfo)

            age_hours = max(
                0.0,
                (now - latest).total_seconds() / 3600,
            )
            data_timestamp = latest.isoformat()
            freshness = (
                "fresh"
                if age_hours <= max_data_age_hours
                else "stale"
            )
    except Exception as exc:
        errors["freshness"] = {
            "error_type": type(exc).__name__,
            "message": str(exc),
        }

    if freshness == "stale" and status == "success":
        status = "stale_data"

    return {
        "agent": "weather",
        "location_code": location_code,
        "status": status,
        "data_freshness": {
            "status": freshness,
            "latest_input_timestamp": data_timestamp,
            "age_hours": round(age_hours, 2) if age_hours is not None else None,
            "max_allowed_age_hours": max_data_age_hours,
        },
        "predictions": predictions,
        "errors": errors,
    }
