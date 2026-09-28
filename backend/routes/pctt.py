from fastapi import APIRouter, Query

from backend.services.pctt_service import (
    get_pctt_history,
    get_pctt_latest,
    get_pctt_summary,
)


router = APIRouter(
    prefix="/pctt",
    tags=["PCTT"],
)


@router.get("/summary")
def pctt_summary():
    return get_pctt_summary()


@router.get("/latest")
def pctt_latest():
    return get_pctt_latest()


@router.get("/history")
def pctt_history(
    hours: int = Query(
        default=72,
        ge=1,
        le=168,
    ),
):
    return {
        "hours": hours,
        "observations": get_pctt_history(hours),
    }