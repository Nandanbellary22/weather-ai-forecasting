-- Current Open-Meteo model inputs for production weather predictions.
-- Kept separate from historical weather_observations, whose source rows
-- must retain their original meaning and provenance.
CREATE TABLE IF NOT EXISTS public.weather_provider_inputs (
    location_code TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    fetched_at_utc TIMESTAMPTZ NOT NULL,
    source TEXT NOT NULL,
    data_type TEXT NOT NULL DEFAULT 'weather_model_output',
    is_verified_station_observation BOOLEAN NOT NULL DEFAULT FALSE,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    temperature_2m DOUBLE PRECISION,
    precipitation_mm DOUBLE PRECISION,
    relative_humidity_2m DOUBLE PRECISION,
    surface_pressure_hpa DOUBLE PRECISION,
    wind_speed_10m DOUBLE PRECISION,
    cloud_cover DOUBLE PRECISION,
    CONSTRAINT uq_weather_provider_input_location_timestamp
        UNIQUE (location_code, timestamp),
    CONSTRAINT ck_weather_provider_input_type
        CHECK (data_type = 'weather_model_output'),
    CONSTRAINT ck_weather_provider_input_unverified
        CHECK (is_verified_station_observation = FALSE),
    CONSTRAINT ck_weather_provider_input_latitude
        CHECK (latitude BETWEEN -90 AND 90),
    CONSTRAINT ck_weather_provider_input_longitude
        CHECK (longitude BETWEEN -180 AND 180)
);

CREATE INDEX IF NOT EXISTS idx_weather_provider_input_latest
    ON public.weather_provider_inputs (location_code, fetched_at_utc DESC, timestamp DESC);

COMMENT ON TABLE public.weather_provider_inputs IS
    'Open-Meteo model estimates, isolated from historical weather observations; the latest provider value is retained per location and timestamp.';
