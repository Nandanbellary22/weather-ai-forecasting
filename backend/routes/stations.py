from fastapi import APIRouter, HTTPException

from backend.schemas import StationSummary
from backend.services.stations_service import get_station_summary


router = APIRouter(
    prefix="/stations",
    tags=["Stations"],
)


@router.get(
    "",
    response_model=list[StationSummary],
)
def list_stations() -> list[StationSummary]:
    """Return station metadata and observation statistics."""

    try:
        return get_station_summary()

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc