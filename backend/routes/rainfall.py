from fastapi import APIRouter, HTTPException

from ml.services.rainfall_service import (
    predict_next_hour_rainfall,
)


router = APIRouter(
    prefix="/weather",
    tags=["Weather"],
)


@router.get(
    "/rainfall/{location_code}"
)
def get_rainfall_forecast(
    location_code: str,
):
    try:
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