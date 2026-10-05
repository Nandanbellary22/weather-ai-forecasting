from datetime import datetime

from pydantic import BaseModel


class StationSummary(BaseModel):
    station_id: str
    station_name: str | None
    station_type: str | None
    latitude: float | None
    longitude: float | None
    source: str | None
    is_active: bool
    observations: int
    valid_observations: int
    missing_values: int
    start_time: datetime | None
    end_time: datetime | None
    latest_value: float | None


class StationObservation(BaseModel):
    station_id: str
    timestamp: datetime
    value: float | None


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


class MRCForecastResponse(BaseModel):
    station_id: str
    model: str
    feature_set: str
    forecast_timestamp: datetime
    predicted_water_level: float
    latest_observation_timestamp: datetime
    latest_water_level: float
    validation_mae: float
    validation_rmse: float
    train_rows: int
    test_rows: int
    validation_start: datetime
    validation_end: datetime


class HealthResponse(BaseModel):
    status: str