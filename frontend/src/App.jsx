import { useEffect, useMemo, useState } from "react";
import {
  MapContainer,
  Marker,
  Popup,
  TileLayer,
  useMap,
} from "react-leaflet";
import L from "leaflet";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import "leaflet/dist/leaflet.css";
import "./App.css";

const API_BASE_URL = "http://127.0.0.1:8000";

const STATION_COORDINATES = {
  553000: [16.047, 108.206],
  553100: [16.067, 108.215],
  553200: [16.078, 108.200],
  553300: [16.055, 108.190],
  553400: [16.030, 108.220],
};

const defaultCenter = [16.055, 108.205];

const stationIcon = new L.Icon({
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  iconRetinaUrl:
    "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  shadowUrl:
    "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41],
});

function MapCenter({ position }) {
  const map = useMap();

  useEffect(() => {
    if (position) {
      map.setView(position, 12);
    }
  }, [map, position]);

  return null;
}

function App() {
  const [stations, setStations] = useState([]);
  const [selectedStation, setSelectedStation] = useState(null);
  const [forecast, setForecast] = useState(null);
  const [loadingStations, setLoadingStations] = useState(true);
  const [loadingForecast, setLoadingForecast] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadStations() {
      try {
        setLoadingStations(true);
        setError("");

        const response = await fetch(`${API_BASE_URL}/stations`);

        if (!response.ok) {
          throw new Error(`Stations request failed: ${response.status}`);
        }

        const data = await response.json();

        setStations(data);

        if (data.length > 0) {
          setSelectedStation(data[0]);
        }
      } catch (err) {
        setError(err.message);
      } finally {
        setLoadingStations(false);
      }
    }

    loadStations();
  }, []);

  useEffect(() => {
    async function loadForecast() {
      if (!selectedStation) {
        return;
      }

      try {
        setLoadingForecast(true);
        setError("");

        const response = await fetch(
          `${API_BASE_URL}/forecasts/${selectedStation.station_id}?model=random_forest`,
        );

        if (!response.ok) {
          throw new Error(`Forecast request failed: ${response.status}`);
        }

        const data = await response.json();

        setForecast(data);
      } catch (err) {
        setForecast(null);
        setError(err.message);
      } finally {
        setLoadingForecast(false);
      }
    }

    loadForecast();
  }, [selectedStation]);

  const selectedPosition = useMemo(() => {
    if (!selectedStation) {
      return defaultCenter;
    }

    return (
      STATION_COORDINATES[selectedStation.station_id] || defaultCenter
    );
  }, [selectedStation]);

  const chartData = useMemo(() => {
    if (!forecast) {
      return [];
    }

    return forecast.forecasts.map((point) => ({
      time: new Date(point.timestamp).toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
      }),
      value: Number(point.predicted_value.toFixed(3)),
    }));
  }, [forecast]);

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <h1>Hydrometeorological AI Forecasting</h1>
          <p>Hydrological monitoring and 24-hour forecasting WebGIS</p>
        </div>

        <div className="status">
          <span className="status-dot" />
          API Connected
        </div>
      </header>

      {error && <div className="error-banner">{error}</div>}

      <main className="dashboard">
        <aside className="sidebar">
          <section className="panel">
            <div className="panel-heading">
              <h2>Hydrological Stations</h2>
              <span>{stations.length}</span>
            </div>

            {loadingStations ? (
              <p className="muted">Loading stations...</p>
            ) : (
              <div className="station-list">
                {stations.map((station) => (
                  <button
                    key={station.station_id}
                    className={`station-item ${
                      selectedStation?.station_id === station.station_id
                        ? "selected"
                        : ""
                    }`}
                    onClick={() => setSelectedStation(station)}
                  >
                    <div>
                      <strong>Station {station.station_id}</strong>
                      <span>
                        Latest: {station.latest_value ?? "No value"}
                      </span>
                    </div>

                    <div className="station-missing">
                      {station.missing_value_count} missing
                    </div>
                  </button>
                ))}
              </div>
            )}
          </section>

          {selectedStation && (
            <section className="panel">
              <h2>Station Details</h2>

              <div className="detail-grid">
                <div>
                  <span>Station</span>
                  <strong>{selectedStation.station_id}</strong>
                </div>

                <div>
                  <span>Latest level</span>
                  <strong>{selectedStation.latest_value}</strong>
                </div>

                <div>
                  <span>Observations</span>
                  <strong>{selectedStation.observation_count}</strong>
                </div>

                <div>
                  <span>Missing</span>
                  <strong>{selectedStation.missing_value_count}</strong>
                </div>
              </div>
            </section>
          )}

          {forecast && (
            <section className="panel">
              <h2>Model Performance</h2>

              <div className="metric-grid">
                <div className="metric">
                  <span>Model</span>
                  <strong>{forecast.model}</strong>
                </div>

                <div className="metric">
                  <span>MAE</span>
                  <strong>{forecast.metrics.mae.toFixed(4)}</strong>
                </div>

                <div className="metric">
                  <span>RMSE</span>
                  <strong>{forecast.metrics.rmse.toFixed(4)}</strong>
                </div>

                <div className="metric">
                  <span>Horizon</span>
                  <strong>{forecast.forecast_horizon_hours}h</strong>
                </div>
              </div>
            </section>
          )}
        </aside>

        <section className="content">
          <div className="map-card">
            <MapContainer
              center={defaultCenter}
              zoom={12}
              scrollWheelZoom
              className="map"
            >
              <TileLayer
                attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              />

              <MapCenter position={selectedPosition} />

              {stations.map((station) => {
                const position =
                  STATION_COORDINATES[station.station_id];

                if (!position) {
                  return null;
                }

                return (
                  <Marker
                    key={station.station_id}
                    position={position}
                    icon={stationIcon}
                    eventHandlers={{
                      click: () => setSelectedStation(station),
                    }}
                  >
                    <Popup>
                      <strong>Station {station.station_id}</strong>
                      <br />
                      Latest level: {station.latest_value}
                      <br />
                      Missing: {station.missing_value_count}
                    </Popup>
                  </Marker>
                );
              })}
            </MapContainer>
          </div>

          <div className="chart-card">
            <div className="chart-heading">
              <div>
                <h2>24-Hour Water-Level Forecast</h2>
                {selectedStation && (
                  <p>
                    Station {selectedStation.station_id} · Random Forest
                  </p>
                )}
              </div>

              {loadingForecast && (
                <span className="muted">Generating forecast...</span>
              )}
            </div>

            {forecast && chartData.length > 0 ? (
              <div className="chart">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="time" />
                    <YAxis />
                    <Tooltip />
                    <Line
                      type="monotone"
                      dataKey="value"
                      strokeWidth={3}
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <div className="empty-chart">
                {loadingForecast
                  ? "Generating forecast..."
                  : "Select a station to view its forecast."}
              </div>
            )}
          </div>
        </section>
      </main>
    </div>
  );
}

export default App;