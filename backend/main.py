from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routes import (
    forecasts,
    pctt,
    rainfall,
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
app.include_router(pctt.router)
app.include_router(weather.router)
app.include_router(rainfall.router)


@app.get("/")
def root():
    return {
        "message": "Hydrometeorological AI Forecasting API",
        "version": "0.1.0",
    }


@app.get("/health")
def health():
    return {
        "status": "ok"
    }