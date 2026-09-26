from fastapi import APIRouter, HTTPException, Query

from backend.schemas import ForecastResponse
from ml.services.forecast_service import forecast_next_24_hours


router = APIRouter(
    prefix="/forecasts",
    tags=["Forecasts"],
)


@router.get(
    "/{station_id}",
    response_model=ForecastResponse,
)
def get_forecast(
    station_id: int,
    model: str = Query(
        default="random_forest",
        pattern="^(random_forest|linear_regression)$",
    ),
) -> ForecastResponse:
    """Generate a 24-hour forecast for a hydrological station."""

    try:
        result = forecast_next_24_hours(
            station_id=station_id,
            model_type=model,
        )

        return result

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