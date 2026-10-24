
import os

import psycopg2
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routes import temperature_forecasts

load_dotenv(override=False)

app = FastAPI(
    title="Weather AI Forecasting API",
    version="0.1.0",
    description="Cloud API for collected Vietnam temperature forecasts.",
)

allowed_origins = [
    origin.strip()
    for origin in os.getenv("FRONTEND_ORIGIN", "").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(temperature_forecasts.router)


@app.get("/")
def root():
    return {
        "message": "Weather AI Forecasting API",
        "status": "running",
    }


@app.get("/health")
def health():
    return {"status": "ok"}
