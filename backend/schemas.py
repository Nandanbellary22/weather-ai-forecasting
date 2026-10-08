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


class MRCStationSummary(BaseModel):
    station_id: str
    station_name: str | None
    latitude: float | None
    longitude: float | None
    river: str | None
    country: str | None
    station_type: str | None

    water_level: float | None
    rainfall: float | None
    rainfall_1h: float | None
    rainfall_6h: float | None
    rainfall_12h: float | None
    rainfall_24h: float | None
    rainfall_7to7: float | None
    temperature: float | None
    battery: float | None

    flood_stage: float | None
    alarm_stage: float | None
    mean_sea_level: float | None

    water_level_sensor: bool
    rainfall_sensor: bool
    temperature_sensor: bool
    battery_sensor: bool

    success_rate: float | None
    last_status: str | None
    last_measurement: datetime | None
    telemetry_available: bool


class MRCObservation(BaseModel):
    station_id: str
    timestamp: datetime
    water_level: float | None
    rainfall: float | None
    temperature: float | None
    battery: float | None


class SpatialMRCResponse(BaseModel):
    requested_latitude: float
    requested_longitude: float

    station_id: str
    station_name: str | None

    station_latitude: float
    station_longitude: float

    river: str | None
    country: str | None
    station_type: str | None

    distance_km: float

    water_level: float | None
    rainfall: float | None
    temperature: float | None
    battery: float | None
    latest_measurement: datetime | None

    flood_stage: float | None
    alarm_stage: float | None

    discharge_available: bool
    discharge_observations: int
    discharge_first_date: object | None
    discharge_last_date: object | None
    minimum_discharge_m3s: float | None
    maximum_discharge_m3s: float | None


class HealthResponse(BaseModel):
    status: str