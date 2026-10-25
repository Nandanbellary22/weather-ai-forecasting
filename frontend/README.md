# Frontend — Weather AI Forecasting

The frontend is the web interface for the Weather AI Forecasting project. It provides an interactive map of Vietnam, weather analytics, forecast visualizations, hydrological monitoring, and access to the backend's forecasting services.

## Technology Stack

- **React** — UI components and interactive application views.
- **Vite** — development server and production build tool.
- **JavaScript** — application logic.
- **Leaflet and React Leaflet** — interactive maps and location markers.
- **CSS** — dashboard layout and styling.
- **FastAPI** — backend API supplying weather, hydrology, and forecast data.

## Features

- Vietnam weather-location map covering the configured 500-location grid.
- Weather analytics with location selection and charts.
- Temperature and rainfall prediction views.
- Recent weather-model output displayed in a dedicated panel.
- Flood and reservoir monitoring views.
- Forecast dashboard and multi-agent forecast integration.
- Hydrological station visualization.

The data shown by the application depends on backend availability and the freshness of the underlying datasets or API responses.

## Prerequisites

Install:

- Node.js and npm.
- The backend dependencies and database configuration described in the root project README.

## Install Dependencies

Open a terminal in the `frontend` directory:

```powershell
npm ci
```

Use `npm ci` to install dependencies from the committed `package-lock.json`.

## Start the Development Server

From the `frontend` directory:

```powershell
npm run dev
```

Vite will print the local development URL in the terminal. Open that URL in your browser.

For the full application, start the FastAPI backend separately from the repository root:

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn backend.main:app --reload
```

The backend normally runs at `http://127.0.0.1:8000`.

Keep both development servers running while using the application.

## Build for Production

From the `frontend` directory:

```powershell
npm run build
```

Vite generates the production build in the `frontend/dist/` directory.

To preview the production build locally:

```powershell
npm run preview
```

## Main Application Files

- `src/App.jsx` — main dashboard and application views.
- `src/App.css` — dashboard styling and layout.
- `src/RecentWeatherPanel.jsx` — recent weather-model output panel.
- `src/TemperatureForecastPanel.jsx` — temperature forecast interface.
- `package.json` — dependencies and available npm scripts.
- `package-lock.json` — locked dependency versions.
- `index.html` — frontend HTML entry point.

## Backend Integration

The frontend communicates with the FastAPI backend for location data, stored weather predictions, recent weather-model output, and coordinated weather/hydrology forecasts.

Important backend endpoints include:

- `GET /health`
- `GET /weather/locations`
- `GET /weather/temperature/{location_code}`
- `GET /weather/rainfall/{location_code}`
- `GET /weather/recent/{location_code}`
- `GET /coordinator/forecast`

The coordinator endpoint may return partial results when an agent has stale inputs or cannot produce a result. The frontend should not interpret stale forecasts as current observations.

## Recent Weather Data

The recent-weather panel retrieves hourly output from the Open-Meteo Forecast API through the backend.

**Important:** This output is weather-model data, not necessarily verified observations from local weather stations. The stored-data prediction services also depend on the timestamps and availability of their local feature datasets and model files.

## Troubleshooting

### The dashboard does not load data

1. Confirm the backend is running.
2. Open `http://127.0.0.1:8000/health` and check that it responds successfully.
3. Check the browser console and backend terminal for errors.
4. Confirm the required database tables and local model artifacts are available.

### Dependencies fail to install

Run the following from the `frontend` directory:

```powershell
npm ci
```

If installation still fails, check your Node.js and npm versions and review the error output before changing dependency versions.

### The production build fails

Run:

```powershell
npm run build
```

Review the first reported error. Do not delete the lockfile or upgrade packages indiscriminately to resolve a build problem.

### Forecasts appear stale

Check the timestamps and source labels returned by the backend. Stored weather data and recent weather-model output are different sources and should be interpreted separately.

## Development Notes

- Keep the frontend and backend API contracts consistent.
- Preserve existing dashboard functionality when modifying components.
- Run `npm run build` after frontend changes.
- Avoid committing `node_modules/`, generated build files, secrets, or local environment configuration.
- Refer to the root `README.md` for the overall project architecture, database setup, data pipelines, machine-learning services, and testing instructions.
