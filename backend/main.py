from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routes.forecasts import router as forecasts_router
from backend.routes.stations import router as stations_router
from backend.schemas import HealthResponse


app = FastAPI(
    title="Hydrometeorological AI Forecasting API",
    version="0.1.0",
    description=(
        "API for hydrological station data, machine-learning forecasts, "
        "and hydrometeorological WebGIS integration."
    ),
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(stations_router)
app.include_router(forecasts_router)


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


@app.get(
    "/",
    tags=["System"],
)
def root() -> dict[str, str]:
    return {
        "message": "Hydrometeorological AI Forecasting API",
        "docs": "/docs",
        "health": "/health",
    }