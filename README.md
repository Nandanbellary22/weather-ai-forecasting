# weather-ai-forecasting# Weather AI Forecasting

A multi-source weather and hydrological forecasting system for Vietnam. The project combines weather data collection, machine-learning forecasts, hydrological time-series analysis, multi-agent coordination, and an interactive WebGIS dashboard.

## Main Features

- Weather data processing for 500 locations.
- Next-hour temperature and rainfall prediction.
- Hydrological station forecasting and evaluation.
- Mekong River Commission (MRC) hydrometeorological data integration.
- Coordinated weather and hydrology agents.
- Interactive Vietnam map, weather analytics, and forecast views.
- Recent weather-model output through the Open-Meteo Forecast API.

## Technology Stack

| Component | Technology |
|---|---|
| Backend | Python, FastAPI, Uvicorn |
| Data processing | Pandas, NumPy |
| Machine learning | Scikit-learn, Joblib |
| Database | PostgreSQL, with PostGIS for spatial functionality |
| Frontend | React, Vite |
| Mapping | Leaflet, React Leaflet |
| Testing | Python `unittest` |

## Project Structure

- `agents/` — weather and hydrology agents and coordinator.
- `backend/` — API application and routes.
- `data/config/` — location and weather-grid configuration.
- `data_pipeline/` — data collection, cleaning, and database imports.
- `database/` — database schema and loading utilities.
- `frontend/` — React/Vite dashboard.
- `ml/features/` — weather and hydrology feature generation.
- `ml/models/` — model validation and evaluation scripts.
- `ml/services/` — prediction services.
- `scripts/` — audits, backtests, and diagnostics.
- `tests/` — automated tests.
- `models/` — local model artifacts, excluded from Git.

## Requirements

- Python and the dependencies listed in `requirements.txt`.
- Node.js and npm.
- PostgreSQL configured for the project.
- Compatible weather model files and processed feature datasets for the stored-data prediction services.

## Python Setup

Run these commands from the repository root in Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Configure the database connection and required environment variables locally. Do not commit `.env` files, credentials, or API secrets.

Review `database/schema.sql` and the relevant database loading scripts before initializing a database. Back up any existing database before making schema or data changes.

## Frontend Setup

```powershell
cd frontend
npm ci
npm run dev
```

To create a production build:

```powershell
npm run build
```

## Run the Backend

From the repository root:

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn backend.main:app --reload
```

The backend normally runs at `http://127.0.0.1:8000`.

Useful endpoints include:

- `GET /health`
- `GET /weather/locations`
- `GET /weather/temperature/{location_code}`
- `GET /weather/rainfall/{location_code}`
- `GET /weather/recent/{location_code}`
- `GET /coordinator/forecast`

Consult the route implementations for query parameters and response details.

## Weather Feature Generation

The 500-location feature pipeline reads hourly observations from PostgreSQL and creates temporal, lag, rolling-statistic, and next-hour target features.

From the repository root:

```powershell
python -m ml.features.weather_features_500
```

Expected output files:

- `data/processed/weather_features/temperature_features_500.csv`
- `data/processed/weather_features/rainfall_features_500.csv`

Feature generation reads the existing database; it does not itself download new weather observations.

## Production Model Files

The current weather prediction services expect:

- `models/weather/temperature_500_model.joblib`
- `models/weather/rainfall_500_model.joblib`

They also depend on the generated weather feature CSVs.

**Reproducibility limitation:** Model files and most processed datasets are excluded from Git. The current `ml/models/train_weather_500.py` script validates datasets and chronological splits; it does not train or save the production models. Older scripts may use different feature schemas and configurations and have not been verified as replacements. A fresh checkout therefore requires compatible model artifacts and feature datasets supplied or generated through a separately verified process.

## Hydrology and Multi-Agent System

Hydrology feature processing and model evaluation scripts are under `ml/features/` and `ml/models/`. Database schema and import utilities are under `database/` and `data_pipeline/database/`.

The coordinator combines weather and hydrology agent outputs and reports their individual statuses. Weather results may be marked stale when their input data exceeds the configured age threshold.

One-hour and 24-hour hydrology evaluations represent different forecast horizons and should be reported separately.

## Run Tests

From the repository root:

```powershell
python -m unittest discover -s tests -v
```

Build the frontend with:

```powershell
cd frontend
npm run build
```

## Data and Evaluation Limitations

- Stored weather features currently end on October 21, 2026; check timestamps before interpreting stored-data forecasts.
- The recent-weather endpoint retrieves Open-Meteo weather-model output, which is not necessarily verified station observation data.
- Hydrological source quality varies by station. Missing values, repeated readings, invalid source values, and station-level performance differences can affect evaluation.
- Historical backtest performance does not guarantee future forecast accuracy.
- Large model artifacts and processed datasets are not currently included in the repository.

## Security and Reproducibility

- Never commit credentials, tokens, or private environment files.
- Avoid committing large generated datasets, model files, temporary diagnostics, and backups without a deliberate decision.
- Keep dependency declarations and lockfiles updated.
- Record dataset provenance, date coverage, feature definitions, and evaluation procedures when preparing research results.

## Current Development Status

The application has passed the current frontend production build, automated test suite, and a six-endpoint API check in the development environment. The next priorities are repository cleanup, model/data reproducibility documentation, and final demo and research-paper preparation.
