from fastapi import APIRouter, HTTPException

from ml.services.temperature_service import (
    predict_next_hour_temperature,
)


router = APIRouter(
    prefix="/weather",
    tags=["Weather"],
)


@router.get("/temperature/{location_code}")
def get_temperature_forecast(
    location_code: str,
):
    try:
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