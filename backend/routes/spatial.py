from fastapi import APIRouter, HTTPException, Query

from backend.schemas import SpatialMRCResponse
from backend.services.spatial_service import (
    get_nearest_mrc_station,
)


router = APIRouter(
    prefix="/spatial",
    tags=["Spatial"],
)


@router.get(
    "/nearest-mrc",
    response_model=SpatialMRCResponse,
)
def get_nearest_mrc(
    latitude: float = Query(
        ...,
        ge=-90,
        le=90,
    ),
    longitude: float = Query(
        ...,
        ge=-180,
        le=180,
    ),
) -> SpatialMRCResponse:
    """
    Find the nearest georeferenced MRC Vietnam station
    to a requested geographic coordinate.

    The response also includes the latest MRC telemetry
    and historical discharge availability.
    """

    try:
        result = get_nearest_mrc_station(
            latitude=latitude,
            longitude=longitude,
        )

        return SpatialMRCResponse(**result)

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc

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