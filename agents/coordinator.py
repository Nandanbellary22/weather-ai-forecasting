
from typing import Any

from agents.hydrology_agent import run_hydrology_agent
from agents.weather_agent import run_weather_agent


def run_forecasting_coordinator(
    location_code: str,
    station_id: str | int,
    weather_max_age_hours: float = 3,
    hydrology_model: str = "random_forest",
) -> dict[str, Any]:
    """
    Coordinate the existing weather and hydrology agents.

    Each agent runs independently so that one failure does not
    prevent the other agent from returning its result.
    """
    location_code = str(location_code).strip().upper()
    station_id = str(station_id).strip()

    if not location_code:
        raise ValueError("location_code must be a non-empty string.")

    if not station_id:
        raise ValueError("station_id must be a non-empty string.")

    results: dict[str, Any] = {}
    errors: dict[str, dict[str, str]] = {}

    agents = {
        "weather": lambda: run_weather_agent(
            location_code,
            max_data_age_hours=weather_max_age_hours,
        ),
        "hydrology": lambda: run_hydrology_agent(
            station_id,
            model_type=hydrology_model,
        ),
    }

    for name, run_agent in agents.items():
        try:
            results[name] = run_agent()
        except Exception as exc:
            errors[name] = {
                "error_type": type(exc).__name__,
                "message": str(exc),
            }

    successful_count = sum(
        result.get("status") == "success"
        for result in results.values()
    )
    stale_count = sum(
        result.get("status") == "stale_data"
        for result in results.values()
    )
    failed_count = len(agents) - successful_count - stale_count

    if successful_count == len(agents):
        status = "success"
    elif successful_count > 0 or stale_count > 0:
        status = "partial"
    else:
        status = "failed"

    return {
        "coordinator": "weather_hydrology",
        "location_code": location_code,
        "station_id": station_id,
        "status": status,
        "agents": results,
        "errors": errors,
        "summary": {
            "total_agents": len(agents),
            "successful_agents": successful_count,
            "stale_data_agents": stale_count,
            "failed_agents": failed_count,
        },
    }
