from fastapi import FastAPI

from backend.routes.forecasts import router as forecast_router
from backend.routes.stations import router as station_router
from backend.schemas import HealthResponse


app = FastAPI(
    title="Hydrometeorological AI Forecasting API",
    description=(
        "API for hydrological observations and 24-hour "
        "machine-learning forecasts."
    ),
    version="0.1.0",
)


app.include_router(station_router)
app.include_router(forecast_router)


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["System"],
)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="hydrometeorological-ai-forecasting",
    )


@app.get("/", tags=["System"])
def root() -> dict[str, str]:
    return {
        "name": "Hydrometeorological AI Forecasting API",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health",
    }