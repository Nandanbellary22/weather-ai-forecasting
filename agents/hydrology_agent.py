
from datetime import date, datetime
from typing import Any

from ml.services.forecast_service import forecast_next_24_hours


def _serialize_datetime(value: Any) -> Any:
    """Convert date/time values into JSON-friendly ISO strings."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if hasattr(value, "isoformat"):
        return value.isoformat()

    return value


def _serialize_forecast(result: dict[str, Any]) -> dict[str, Any]:
    """Return a JSON-friendly hydrological forecast."""
    output = dict(result)

    observation = dict(output.get("last_observation", {}))
    if "timestamp" in observation:
        observation["timestamp"] = _serialize_datetime(
            observation["timestamp"]
        )
    output["last_observation"] = observation

    output["forecast"] = [
        {
            **point,
            "timestamp": _serialize_datetime(point.get("timestamp")),
        }
        for point in output.get("forecast", [])
    ]

    return output


def run_hydrology_agent(
    station_id: str,
    model_type: str = "random_forest",
) -> dict[str, Any]:
    """
    Generate a 24-hour forecast for one hydrological station.

    Uses the existing forecasting service, including its validation
    and PostgreSQL persistence behavior.
    """
    if not isinstance(station_id, (str, int)) or not str(station_id).strip():
        raise ValueError("station_id must be a non-empty string or integer.")

    station_id = str(station_id).strip()

    if model_type not in {"random_forest", "linear_regression"}:
        raise ValueError(
            "model_type must be 'random_forest' or 'linear_regression'."
        )

    try:
        result = forecast_next_24_hours(
            station_id=station_id,
            model_type=model_type,
        )

        forecast = _serialize_forecast(result)

        if len(forecast.get("forecast", [])) != 24:
            return {
                "agent": "hydrology",
                "station_id": station_id,
                "status": "failed",
                "error": {
                    "error_type": "InvalidForecastLength",
                    "message": "Expected 24 forecast points.",
                },
            }

        return {
            "agent": "hydrology",
            "station_id": station_id,
            "status": "success",
            "result": forecast,
            "errors": {},
        }

    except Exception as exc:
        return {
            "agent": "hydrology",
            "station_id": station_id,
            "status": "failed",
            "errors": {
                "forecast": {
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                }
            },
        }
