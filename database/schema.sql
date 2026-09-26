-- ============================================================
-- Weather AI Forecasting - PostgreSQL/PostGIS Schema
-- ============================================================

CREATE EXTENSION IF NOT EXISTS postgis;

-- ============================================================
-- 1. Monitoring stations
-- ============================================================

CREATE TABLE IF NOT EXISTS stations (
    id SERIAL PRIMARY KEY,
    station_id VARCHAR(50) NOT NULL UNIQUE,
    station_name TEXT,
    station_type VARCHAR(50),
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    location GEOMETRY(Point, 4326),
    source VARCHAR(100),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_stations_location
ON stations
USING GIST (location);

CREATE INDEX IF NOT EXISTS idx_stations_station_id
ON stations (station_id);


-- ============================================================
-- 2. Hydrology observations
-- ============================================================

CREATE TABLE IF NOT EXISTS hydrology_observations (
    id BIGSERIAL PRIMARY KEY,
    station_id VARCHAR(50) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    value DOUBLE PRECISION,
    source VARCHAR(100) NOT NULL DEFAULT 'professor_hydrology_api',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_hydrology_station_timestamp
        UNIQUE (station_id, timestamp)
);

CREATE INDEX IF NOT EXISTS idx_hydrology_station_timestamp
ON hydrology_observations (station_id, timestamp);

CREATE INDEX IF NOT EXISTS idx_hydrology_timestamp
ON hydrology_observations (timestamp);


-- ============================================================
-- 3. PCTT hydrological / reservoir observations
-- ============================================================

CREATE TABLE IF NOT EXISTS pctt_observations (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,

    htl1 DOUBLE PRECISION,
    qvao1 DOUBLE PRECISION,
    luuluongnhamay1 DOUBLE PRECISION,
    qxaquacua1 DOUBLE PRECISION,

    htl2 DOUBLE PRECISION,
    qvao2 DOUBLE PRECISION,
    luuluongnhamay2 DOUBLE PRECISION,
    qxaquacua2 DOUBLE PRECISION,

    htl3 DOUBLE PRECISION,
    qvao3 DOUBLE PRECISION,
    luuluongnhamay3 DOUBLE PRECISION,
    qxaquacua3 DOUBLE PRECISION,

    htl4 DOUBLE PRECISION,
    qvao4 DOUBLE PRECISION,
    luuluongnhamay4 DOUBLE PRECISION,
    qxaquacua4 DOUBLE PRECISION,

    qvevugia DOUBLE PRECISION,
    qvethubon DOUBLE PRECISION,

    source VARCHAR(100) NOT NULL DEFAULT 'pctt_danang',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_pctt_timestamp UNIQUE (timestamp)
);

CREATE INDEX IF NOT EXISTS idx_pctt_timestamp
ON pctt_observations (timestamp);


-- ============================================================
-- 4. EVN reservoir observations
-- ============================================================

CREATE TABLE IF NOT EXISTS evn_reservoirs (
    id SERIAL PRIMARY KEY,

    reservoir_name TEXT NOT NULL UNIQUE,

    observation_time TIMESTAMPTZ,

    htl DOUBLE PRECISION,
    hdbt DOUBLE PRECISION,
    hc DOUBLE PRECISION,

    qve DOUBLE PRECISION,
    total_discharge DOUBLE PRECISION,
    powerhouse_discharge DOUBLE PRECISION,
    spillway_discharge DOUBLE PRECISION,

    ncxs DOUBLE PRECISION,
    ncxm DOUBLE PRECISION,

    source VARCHAR(100) NOT NULL DEFAULT 'evn',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_evn_reservoir_time
ON evn_reservoirs (observation_time);

CREATE INDEX IF NOT EXISTS idx_evn_reservoir_name
ON evn_reservoirs (reservoir_name);


-- ============================================================
-- 5. Forecast runs
-- ============================================================

CREATE TABLE IF NOT EXISTS forecast_runs (
    id BIGSERIAL PRIMARY KEY,

    station_id VARCHAR(50) NOT NULL,
    model_type VARCHAR(100) NOT NULL,

    training_start TIMESTAMPTZ,
    training_end TIMESTAMPTZ,

    train_rows INTEGER,
    test_rows INTEGER,

    mae DOUBLE PRECISION,
    rmse DOUBLE PRECISION,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_forecast_runs_station
ON forecast_runs (station_id, created_at);


-- ============================================================
-- 6. Forecast values
-- ============================================================

CREATE TABLE IF NOT EXISTS forecast_values (
    id BIGSERIAL PRIMARY KEY,

    forecast_run_id BIGINT NOT NULL
        REFERENCES forecast_runs(id)
        ON DELETE CASCADE,

    station_id VARCHAR(50) NOT NULL,
    forecast_timestamp TIMESTAMPTZ NOT NULL,
    predicted_value DOUBLE PRECISION NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_forecast_values_station_time
ON forecast_values (station_id, forecast_timestamp);

CREATE INDEX IF NOT EXISTS idx_forecast_values_run
ON forecast_values (forecast_run_id);


-- ============================================================
-- Done
-- ============================================================

COMMENT ON TABLE stations IS
'Monitoring stations used by the hydrometeorological forecasting platform.';

COMMENT ON TABLE hydrology_observations IS
'Water-level observations collected from the professor-provided hydrology API.';

COMMENT ON TABLE pctt_observations IS
'Raw/cleaned hydrological observations from the Da Nang PCTT API.';

COMMENT ON TABLE evn_reservoirs IS
'Reservoir observations collected from the EVN reservoir portal.';

COMMENT ON TABLE forecast_runs IS
'Metadata and evaluation metrics for trained forecasting models.';

COMMENT ON TABLE forecast_values IS
'Individual forecast values generated by a forecast run.';