from fastapi import APIRouter, HTTPException, Query

from backend.schemas import StationObservation, StationSummary
from backend.services.stations_service import (
    get_station_history,
    get_station_summary,
)

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


@router.get(
    "/{station_id}/history",
    response_model=list[StationObservation],
)
def station_history(
    station_id: str,
    limit: int = Query(
        default=168,
        ge=1,
        le=5000,
        description="Number of most recent observations to return.",
    ),
) -> list[StationObservation]:
    """Return recent observations for one hydrology station."""
    try:
        history = get_station_history(
            station_id=station_id,
            limit=limit,
        )

        if not history:
            raise HTTPException(
                status_code=404,
                detail=f"No observations found for station {station_id}.",
            )

        return history

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc