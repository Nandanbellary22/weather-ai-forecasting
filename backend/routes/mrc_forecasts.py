from fastapi import APIRouter, HTTPException, Query

from backend.schemas import (
    MRCForecastResponse,
    MRCObservation,
    MRCStationSummary,
)
from backend.services.mrc_service import (
    get_mrc_station_history,
    get_mrc_stations,
)
from ml.services.mrc_forecast_service import forecast_next_hour


router = APIRouter(
    prefix="/mrc",
    tags=["MRC"],
)


@router.get(
    "/stations",
    response_model=list[MRCStationSummary],
)
def get_mrc_station_list() -> list[MRCStationSummary]:
    """
    Return all Vietnam MRC stations and their latest
    telemetry snapshot.
    """

    try:
        results = get_mrc_stations()

        return [
            MRCStationSummary(**station)
            for station in results
        ]

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc


@router.get(
    "/stations/{station_id}/history",
    response_model=list[MRCObservation],
)
def get_mrc_station_history_route(
    station_id: str,
    limit: int = Query(
        default=168,
        ge=1,
        le=1000,
    ),
) -> list[MRCObservation]:
    """
    Return chronological MRC observations for one station.
    """

    try:
        results = get_mrc_station_history(
            station_id=station_id,
            limit=limit,
        )

        return [
            MRCObservation(**observation)
            for observation in results
        ]

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc


@router.get(
    "/forecasts/{station_id}",
    response_model=MRCForecastResponse,
)
def get_mrc_forecast(
    station_id: str,
) -> MRCForecastResponse:
    """
    Generate a one-hour-ahead MRC water-level forecast.
    """

    try:
        result = forecast_next_hour(
            station_id=station_id,
        )

        return MRCForecastResponse(
            station_id=result["station_id"],
            model=result["model"],
            feature_set=result["feature_set"],
            forecast_timestamp=result["forecast_timestamp"],
            predicted_water_level=result[
                "predicted_water_level"
            ],
            latest_observation_timestamp=result[
                "latest_observation_timestamp"
            ],
            latest_water_level=result[
                "latest_water_level"
            ],
            validation_mae=result[
                "validation_mae"
            ],
            validation_rmse=result[
                "validation_rmse"
            ],
            train_rows=result[
                "train_rows"
            ],
            test_rows=result[
                "test_rows"
            ],
            validation_start=result[
                "validation_start"
            ],
            validation_end=result[
                "validation_end"
            ],
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc