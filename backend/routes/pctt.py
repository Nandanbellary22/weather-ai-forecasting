from fastapi import APIRouter

from backend.services.pctt_service import get_pctt_latest, get_pctt_summary


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