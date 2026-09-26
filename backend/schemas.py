from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class StationSummary(BaseModel):
    station_id: int
    observation_count: int
    valid_observation_count: int
    missing_value_count: int
    start_time: datetime
    end_time: datetime
    latest_value: float | None


class ForecastMetrics(BaseModel):
    mae: float
    rmse: float
    train_rows: int
    test_rows: int


class LastObservation(BaseModel):
    timestamp: datetime
    value: float


class ForecastPoint(BaseModel):
    station_id: int
    timestamp: datetime
    predicted_value: float


class ForecastResponse(BaseModel):
    station_id: int
    model: str
    forecast_horizon_hours: int = Field(
        description="Number of hourly forecast points"
    )
    last_observation: LastObservation
    metrics: ForecastMetrics
    forecasts: list[ForecastPoint]


class HealthResponse(BaseModel):
    status: str
    service: str