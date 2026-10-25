
import os
from pathlib import Path

from dotenv import load_dotenv

# Load the project-root .env before importing routes and services.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env", override=False)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routes import (
    coordinator,
    forecasts,
    location,
    mrc_forecasts,
    pctt,
    spatial,
    stations,
    weather,
    temperature_forecasts,
)


app = FastAPI(
    title="Hydrometeorological AI Forecasting API",
    version="0.1.0",
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


app.include_router(stations.router)
app.include_router(forecasts.router)
app.include_router(mrc_forecasts.router)
app.include_router(pctt.router)
app.include_router(weather.router)
app.include_router(spatial.router)
app.include_router(location.router)
app.include_router(coordinator.router)
app.include_router(temperature_forecasts.router)

@app.get("/")
def root():
    return {
        "message": "Hydrometeorological AI Forecasting API",
        "version": "0.1.0",
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
    }
