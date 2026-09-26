from fastapi import APIRouter, HTTPException

from backend.schemas import StationSummary
from ml.services.forecast_service import get_station_summary


router = APIRouter(
    prefix="/stations",
    tags=["Stations"],
)


@router.get(
    "",
    response_model=list[StationSummary],
)
def list_stations() -> list[StationSummary]:
    """Return all available hydrological stations."""

    try:
        return get_station_summary()

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc