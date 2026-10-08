from fastapi import APIRouter, HTTPException


router = APIRouter(
    prefix="/spatial",
    tags=["Spatial"],
)


@router.get("/location/{location_code}")
def get_location_profile(
    location_code: str,
):
    """
    Return an integrated weather and hydrological
    profile for one weather location.
    """

    try:
        from backend.services.location_service import (
            get_location_profile as build_location_profile,
        )

        return build_location_profile(
            location_code=location_code,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc