from datetime import datetime

from pydantic import BaseModel


class StationSummary(BaseModel):
    station_id: str
    observations: int
    valid_observations: int
    missing_values: int
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
    timestamp: datetime
    value: float


class ForecastResponse(BaseModel):
    station_id: str
    model: str
    metrics: ForecastMetrics
    last_observation: LastObservation
    forecast: list[ForecastPoint]


class HealthResponse(BaseModel):
    status: str