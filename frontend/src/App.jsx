import { useState } from "react";
import {
  MapContainer,
  TileLayer,
  CircleMarker,
  Popup,
  useMap,
} from "react-leaflet";

import "leaflet/dist/leaflet.css";
import "./App.css";

const API_BASE_URL = "http://127.0.0.1:8000";

const WEATHER_LOCATIONS = [
  { code: "HN", name: "Hanoi", latitude: 21.0278, longitude: 105.8342 },
  { code: "HP", name: "Hai Phong", latitude: 20.8449, longitude: 106.6881 },
  { code: "DB", name: "Dien Bien Phu", latitude: 21.386, longitude: 103.023 },
  { code: "V", name: "Vinh", latitude: 18.6796, longitude: 105.6813 },
  { code: "HUE", name: "Hue", latitude: 16.4637, longitude: 107.5909 },
  { code: "DN", name: "Da Nang", latitude: 16.0544, longitude: 108.2022 },
  { code: "HOI_AN", name: "Hoi An", latitude: 15.8801, longitude: 108.338 },
  { code: "QN", name: "Quy Nhon", latitude: 13.782, longitude: 109.219 },
  { code: "NT", name: "Nha Trang", latitude: 12.2388, longitude: 109.1967 },
  { code: "DL", name: "Da Lat", latitude: 11.9404, longitude: 108.4583 },
  { code: "BMT", name: "Buon Ma Thuot", latitude: 12.6667, longitude: 108.0382 },
  { code: "PLEIKU", name: "Pleiku", latitude: 13.9833, longitude: 108.0 },
  { code: "HCM", name: "Ho Chi Minh City", latitude: 10.8231, longitude: 106.6297 },
  { code: "CT", name: "Can Tho", latitude: 10.0452, longitude: 105.7469 },
];

const RESERVOIRS = [
  {
    id: 1,
    name: "A Vuong",
    latitude: 15.979,
    longitude: 107.519,
  },
  {
    id: 2,
    name: "Dak Mi 4",
    latitude: 15.936,
    longitude: 107.853,
  },
  {
    id: 3,
    name: "Song Bung 4",
    latitude: 15.912,
    longitude: 107.727,
  },
  {
    id: 4,
    name: "Song Tranh 2",
    latitude: 15.311,
    longitude: 108.143,
  },
];

const HYDRO_FIELDS = {
  1: {
    htl: "htl1",
    qvao: "qvao1",
    power: "luuluongnhamay1",
    spill: "qxaquacua1",
  },
  2: {
    htl: "htl2",
    qvao: "qvao2",
    power: "luuluongnhamay2",
    spill: "qxaquacua2",
  },
  3: {
    htl: "htl3",
    qvao: "qvao3",
    power: "luuluongnhamay3",
    spill: "qxaquacua3",
  },
  4: {
    htl: "htl4",
    qvao: "qvao4",
    power: "luuluongnhamay4",
    spill: "qxaquacua4",
  },
};

function MapCenter({ location }) {
  const map = useMap();

  if (location) {
    map.setView(
      [location.latitude, location.longitude],
      8,
      { animate: true }
    );
  }

  return null;
}

function App() {
  const [mode, setMode] = useState("weather");

  const [selectedLocation, setSelectedLocation] = useState(null);

  const [temperature, setTemperature] = useState(null);
  const [rainfall, setRainfall] = useState(null);

  const [hydrology, setHydrology] = useState(null);
  const [selectedReservoir, setSelectedReservoir] = useState(null);

  const [loading, setLoading] = useState(false);
  const [hydroLoading, setHydroLoading] = useState(false);

  const [error, setError] = useState(null);
  const [hydroError, setHydroError] = useState(null);

  async function loadWeather(location) {
    setSelectedLocation(location);
    setTemperature(null);
    setRainfall(null);
    setError(null);
    setLoading(true);

    try {
      const [temperatureResponse, rainfallResponse] =
        await Promise.all([
          fetch(
            `${API_BASE_URL}/weather/temperature/${location.code}`
          ),
          fetch(
            `${API_BASE_URL}/weather/rainfall/${location.code}`
          ),
        ]);

      if (
        !temperatureResponse.ok ||
        !rainfallResponse.ok
      ) {
        throw new Error(
          "Unable to load weather forecast."
        );
      }

      const temperatureData =
        await temperatureResponse.json();

      const rainfallData =
        await rainfallResponse.json();

      setTemperature(temperatureData);
      setRainfall(rainfallData);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function loadHydrology(reservoir) {
    setSelectedReservoir(reservoir);
    setHydrology(null);
    setHydroError(null);
    setHydroLoading(true);

    try {
      const response = await fetch(
        `${API_BASE_URL}/pctt/latest`
      );

      if (!response.ok) {
        throw new Error(
          "Unable to load hydrological data."
        );
      }

      const data = await response.json();

      setHydrology(data);
    } catch (err) {
      setHydroError(err.message);
    } finally {
      setHydroLoading(false);
    }
  }

  function changeMode(newMode) {
    setMode(newMode);

    setSelectedLocation(null);
    setSelectedReservoir(null);

    setTemperature(null);
    setRainfall(null);
    setHydrology(null);

    setError(null);
    setHydroError(null);
  }

  function getHydroValue(reservoirId, field) {
    if (!hydrology) {
      return null;
    }

    const fields = HYDRO_FIELDS[reservoirId];

    if (!fields) {
      return null;
    }

    return hydrology[fields[field]];
  }

  return (
    <div className="app">

      <header className="header">

        <div>
          <h1>
            Vietnam Hydrometeorological
            Forecasting WebGIS
          </h1>

          <p>
            Multi-source data • Machine Learning •
            Weather & Hydrology
          </p>
        </div>

        <div className="mode-buttons">

          <button
            className={
              mode === "weather"
                ? "mode-button active"
                : "mode-button"
            }
            onClick={() =>
              changeMode("weather")
            }
          >
            Weather
          </button>

          <button
            className={
              mode === "hydrology"
                ? "mode-button hydro active"
                : "mode-button hydro"
            }
            onClick={() =>
              changeMode("hydrology")
            }
          >
            Hydrology
          </button>

        </div>

      </header>

      <main className="main-layout">

        <section className="map-section">

          <MapContainer
            center={[16.5, 106]}
            zoom={6}
            scrollWheelZoom={true}
            className="map"
          >

            <TileLayer
              attribution="&copy; OpenStreetMap contributors"
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />

            {mode === "weather" &&
              selectedLocation && (
                <MapCenter
                  location={selectedLocation}
                />
              )}

            {mode === "weather" &&
              WEATHER_LOCATIONS.map((location) => (
                <CircleMarker
                  key={location.code}
                  center={[
                    location.latitude,
                    location.longitude,
                  ]}
                  radius={
                    selectedLocation?.code ===
                    location.code
                      ? 10
                      : 7
                  }
                  pathOptions={{
                    color:
                      selectedLocation?.code ===
                      location.code
                        ? "#dc2626"
                        : "#2563eb",

                    fillColor:
                      selectedLocation?.code ===
                      location.code
                        ? "#ef4444"
                        : "#3b82f6",

                    fillOpacity: 0.85,
                    weight: 2,
                  }}
                  eventHandlers={{
                    click: () =>
                      loadWeather(location),
                  }}
                >
                  <Popup>
                    <strong>
                      {location.name}
                    </strong>
                    <br />
                    Click for ML forecast.
                  </Popup>
                </CircleMarker>
              ))}

            {mode === "hydrology" &&
              RESERVOIRS.map((reservoir) => (
                <CircleMarker
                  key={reservoir.id}
                  center={[
                    reservoir.latitude,
                    reservoir.longitude,
                  ]}
                  radius={
                    selectedReservoir?.id ===
                    reservoir.id
                      ? 12
                      : 9
                  }
                  pathOptions={{
                    color:
                      selectedReservoir?.id ===
                      reservoir.id
                        ? "#065f46"
                        : "#047857",

                    fillColor:
                      selectedReservoir?.id ===
                      reservoir.id
                        ? "#059669"
                        : "#10b981",

                    fillOpacity: 0.9,
                    weight: 2,
                  }}
                  eventHandlers={{
                    click: () =>
                      loadHydrology(reservoir),
                  }}
                >
                  <Popup>
                    <strong>
                      {reservoir.name}
                    </strong>
                    <br />
                    Click for hydrological data.
                  </Popup>
                </CircleMarker>
              ))}

          </MapContainer>

          <div className="map-legend">

            {mode === "weather" ? (
              <>
                <span className="legend-dot weather-dot" />
                Weather / ML location
              </>
            ) : (
              <>
                <span className="legend-dot hydro-dot" />
                Hydropower reservoir
              </>
            )}

          </div>

        </section>

        <aside className="forecast-panel">

          <div className="panel-title">

            <span>
              {mode === "weather"
                ? "GENERAL WEATHER"
                : "HYDROLOGY"}
            </span>

            <h2>
              {mode === "weather"
                ? "Weather Forecast"
                : "Hydrological Monitoring"}
            </h2>

          </div>

          {!selectedLocation &&
            !selectedReservoir && (
              <div className="empty-state">

                <div className="big-icon">
                  {mode === "weather"
                    ? "☁"
                    : "💧"}
                </div>

                <h3>
                  Select a location
                </h3>

                <p>
                  {mode === "weather"
                    ? "Click a blue marker to view the machine-learning forecast."
                    : "Click a green reservoir to view real hydrological observations."}
                </p>

              </div>
            )}

          {mode === "weather" &&
            selectedLocation && (
              <div>

                <div className="location-header">

                  <span>
                    Selected location
                  </span>

                  <h2>
                    {selectedLocation.name}
                  </h2>

                  <p>
                    {selectedLocation.latitude.toFixed(4)}
                    {" · "}
                    {selectedLocation.longitude.toFixed(4)}
                  </p>

                </div>

                {loading && (
                  <div className="loading">
                    Loading ML forecast...
                  </div>
                )}

                {error && (
                  <div className="error">
                    {error}
                  </div>
                )}

                {!loading &&
                  !error &&
                  temperature &&
                  rainfall && (
                    <div className="forecast-content">

                      <div className="forecast-card">

                        <span>
                          Current temperature
                        </span>

                        <strong>
                          {
                            temperature.current_temperature_c
                          }
                          °C
                        </strong>

                        <p>
                          ML prediction — next hour
                        </p>

                        <div className="prediction-value">
                          {
                            temperature.predicted_next_hour_temperature_c
                          }
                          °C
                        </div>

                      </div>

                      <div className="forecast-card rainfall-card">

                        <span>
                          Current rainfall
                        </span>

                        <strong>
                          {
                            rainfall.current_rainfall_mm
                          }{" "}
                          mm
                        </strong>

                        <p>
                          ML prediction — next hour
                        </p>

                        <div className="prediction-value">
                          {
                            rainfall.predicted_next_hour_rainfall_mm
                          }{" "}
                          mm
                        </div>

                      </div>

                      <div className="model-info">

                        <strong>
                          Machine-learning models
                        </strong>

                        <p>
                          Temperature: Random Forest
                        </p>

                        <p>
                          Rainfall: Linear Regression
                        </p>

                      </div>

                      <div className="timestamp">
                        Data timestamp:
                        <br />
                        {new Date(
                          temperature.timestamp
                        ).toLocaleString()}
                      </div>

                    </div>
                  )}

              </div>
            )}

          {mode === "hydrology" &&
            selectedReservoir && (
              <div>

                <div className="location-header">

                  <span>
                    Selected reservoir
                  </span>

                  <h2>
                    {selectedReservoir.name}
                  </h2>

                  <p>
                    Central Vietnam
                  </p>

                </div>

                {hydroLoading && (
                  <div className="loading">
                    Loading hydrological observations...
                  </div>
                )}

                {hydroError && (
                  <div className="error">
                    {hydroError}
                  </div>
                )}

                {!hydroLoading &&
                  !hydroError &&
                  hydrology && (
                    <div className="forecast-content">

                      <div className="hydro-timestamp">

                        <span>
                          Latest observation
                        </span>

                        <strong>
                          {new Date(
                            hydrology.timestamp
                          ).toLocaleString()}
                        </strong>

                      </div>

                      <div className="hydro-card">

                        <span>
                          Reservoir water level
                        </span>

                        <strong>
                          {
                            getHydroValue(
                              selectedReservoir.id,
                              "htl"
                            )
                          }
                        </strong>

                        <p>
                          Htl — water level
                        </p>

                      </div>

                      <div className="hydro-card">

                        <span>
                          Inflow
                        </span>

                        <strong>
                          {
                            getHydroValue(
                              selectedReservoir.id,
                              "qvao"
                            )
                          }
                        </strong>

                        <p>
                          Qvao — inflow
                        </p>

                      </div>

                      <div className="hydro-card">

                        <span>
                          Powerhouse discharge
                        </span>

                        <strong>
                          {
                            getHydroValue(
                              selectedReservoir.id,
                              "power"
                            )
                          }
                        </strong>

                        <p>
                          Powerhouse flow
                        </p>

                      </div>

                      <div className="hydro-card">

                        <span>
                          Spillway discharge
                        </span>

                        <strong>
                          {
                            getHydroValue(
                              selectedReservoir.id,
                              "spill"
                            )
                          }
                        </strong>

                        <p>
                          Qxa qua cua — spillway flow
                        </p>

                      </div>

                      <div className="hydro-info">

                        <div>
                          <span>
                            Data source
                          </span>

                          <strong>
                            PCTT Da Nang
                          </strong>
                        </div>

                        <div>
                          <span>
                            Backend
                          </span>

                          <strong>
                            PostgreSQL + FastAPI
                          </strong>
                        </div>

                        <div>
                          <span>
                            Visualization
                          </span>

                          <strong>
                            React + Leaflet WebGIS
                          </strong>
                        </div>

                      </div>

                    </div>
                  )}

              </div>
            )}

        </aside>

      </main>

    </div>
  );
}

export default App;