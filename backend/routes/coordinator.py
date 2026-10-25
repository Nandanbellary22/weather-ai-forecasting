
from fastapi import APIRouter, HTTPException, Query

router = APIRouter(
    prefix="/coordinator",
    tags=["Multi-Agent Forecasting"],
)


@router.get("/forecast")
def get_combined_forecast(
    location_code: str = Query(
        ...,
        min_length=1,
        description="Weather location code, for example DN.",
    ),
    station_id: str = Query(
        ...,
        min_length=1,
        description="Hydrology station ID, for example 553100.",
    ),
    model_type: str = Query(
        default="random_forest",
        description="Hydrology model: random_forest or linear_regression.",
    ),
    max_data_age_hours: float = Query(
        default=3,
        ge=0,
        description="Maximum acceptable age of weather input data.",
    ),
):
    """Coordinate weather and hydrology forecasting agents."""
    from agents.coordinator import run_forecasting_coordinator

    try:
        return run_forecasting_coordinator(
            location_code=location_code,
            station_id=station_id,
            weather_max_age_hours=max_data_age_hours,
            hydrology_model=model_type,
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
