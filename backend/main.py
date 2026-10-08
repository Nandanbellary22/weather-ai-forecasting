from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routes import (
    forecasts,
    location,
    mrc_forecasts,
    pctt,
    rainfall,
    spatial,
    stations,
    weather,
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
app.include_router(rainfall.router)
app.include_router(spatial.router)
app.include_router(location.router)


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