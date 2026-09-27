import { useEffect, useState } from "react";
import {
  CircleMarker,
  MapContainer,
  Popup,
  TileLayer,
} from "react-leaflet";
import {
  CartesianGrid,
  Legend,
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

// Temporary display coordinates.
// These are NOT verified real station coordinates.
const STATION_COORDINATES = {
  553000: [16.047, 108.206],
  553100: [16.067, 108.215],
  553200: [16.078, 108.200],
  553300: [16.055, 108.190],
  553400: [16.030, 108.220],
};

function App() {
  const [stations, setStations] = useState([]);
  const [selectedStation, setSelectedStation] = useState(null);
  const [forecast, setForecast] = useState(null);
  const [pcttLatest, setPcttLatest] = useState(null);

  const [loadingStations, setLoadingStations] = useState(true);
  const [loadingForecast, setLoadingForecast] = useState(false);
  const [loadingPctt, setLoadingPctt] = useState(true);

  const [error, setError] = useState(null);

  useEffect(() => {
    loadStations();
    loadPcttLatest();
  }, []);

  useEffect(() => {
    if (selectedStation) {
      loadForecast(selectedStation.station_id);
    }
  }, [selectedStation]);

  async function loadStations() {
    try {
      setLoadingStations(true);
      setError(null);

      const response = await fetch(`${API_BASE_URL}/stations`);

      if (!response.ok) {
        throw new Error("Failed to load stations.");
      }

      const data = await response.json();

      setStations(data);

      if (data.length > 0) {
        setSelectedStation(data[0]);
      }
    } catch (err) {
      console.error("Station loading error:", err);
      setError(err.message);
    } finally {
      setLoadingStations(false);
    }
  }

  async function loadForecast(stationId) {
    try {
      setLoadingForecast(true);
      setError(null);
      setForecast(null);

      const response = await fetch(
        `${API_BASE_URL}/forecasts/${stationId}?model=random_forest`
      );

      if (!response.ok) {
        throw new Error(
          `Failed to load forecast for station ${stationId}.`
        );
      }

      const data = await response.json();

      console.log("Forecast API response:", data);

      setForecast(data);
    } catch (err) {
      console.error("Forecast loading error:", err);
      setError(err.message);
    } finally {
      setLoadingForecast(false);
    }
  }

  async function loadPcttLatest() {
    try {
      setLoadingPctt(true);
      setError(null);

      const response = await fetch(`${API_BASE_URL}/pctt/latest`);

      if (!response.ok) {
        throw new Error("Failed to load PCTT data.");
      }

      const data = await response.json();

      console.log("PCTT API response:", data);

      setPcttLatest(data);
    } catch (err) {
      console.error("PCTT loading error:", err);
      setError(err.message);
    } finally {
      setLoadingPctt(false);
    }
  }

  // Backend returns "forecast", not "forecasts".
  const forecastChartData =
    forecast?.forecast?.map((item) => ({
      time: new Date(item.timestamp).toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
      }),
      value: item.value,
    })) ?? [];

  return (
    <div className="app">
      <header className="header">
        <div>
          <h1>Hydrometeorological AI Forecasting</h1>

          <p>
            Multi-source hydrology, hydropower and AI forecasting platform
          </p>
        </div>

        <div className="status">
          <span className="status-dot"></span>
          API Connected
        </div>
      </header>

      {error && <div className="error-banner">{error}</div>}

      <main className="dashboard">
        {/* =========================================================
            TOP SECTION
        ========================================================= */}
        <section className="top-grid">
          {/* =======================================================
              HYDROLOGY STATIONS
          ======================================================= */}
          <div className="card station-card">
            <div className="card-header">
              <h2>Hydrology Stations</h2>

              <span>
                {loadingStations
                  ? "Loading..."
                  : `${stations.length} stations`}
              </span>
            </div>

            {loadingStations ? (
              <p>Loading stations...</p>
            ) : stations.length === 0 ? (
              <p>No stations available.</p>
            ) : (
              <div className="station-list">
                {stations.map((station) => (
                  <button
                    key={station.station_id}
                    className={`station-item ${
                      selectedStation?.station_id === station.station_id
                        ? "active"
                        : ""
                    }`}
                    onClick={() => setSelectedStation(station)}
                  >
                    <div>
                      <strong>Station {station.station_id}</strong>

                      <span>
                        {station.valid_observations} valid observations
                      </span>
                    </div>

                    <div className="station-value">
                      {station.latest_value ?? "N/A"}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* =======================================================
              PCTT HYDROPOWER
          ======================================================= */}
          <div className="card pctt-card">
            <div className="card-header">
              <h2>PCTT Hydropower</h2>

              <span>Latest observation</span>
            </div>

            {loadingPctt ? (
              <p>Loading PCTT data...</p>
            ) : pcttLatest ? (
              <>
                <p className="observation-time">
                  {new Date(pcttLatest.timestamp).toLocaleString()}
                </p>

                <div className="pctt-grid">
                  <div className="metric">
                    <span>HTL 1</span>
                    <strong>{pcttLatest.htl1 ?? "N/A"}</strong>
                  </div>

                  <div className="metric">
                    <span>Inflow 1</span>
                    <strong>{pcttLatest.qvao1 ?? "N/A"}</strong>
                  </div>

                  <div className="metric">
                    <span>HTL 2</span>
                    <strong>{pcttLatest.htl2 ?? "N/A"}</strong>
                  </div>

                  <div className="metric">
                    <span>Inflow 2</span>
                    <strong>{pcttLatest.qvao2 ?? "N/A"}</strong>
                  </div>

                  <div className="metric">
                    <span>HTL 3</span>
                    <strong>{pcttLatest.htl3 ?? "N/A"}</strong>
                  </div>

                  <div className="metric">
                    <span>Inflow 3</span>
                    <strong>{pcttLatest.qvao3 ?? "N/A"}</strong>
                  </div>

                  <div className="metric">
                    <span>HTL 4</span>
                    <strong>{pcttLatest.htl4 ?? "N/A"}</strong>
                  </div>

                  <div className="metric">
                    <span>Inflow 4</span>
                    <strong>{pcttLatest.qvao4 ?? "N/A"}</strong>
                  </div>

                  <div className="metric">
                    <span>Vu Gia Flow</span>
                    <strong>{pcttLatest.qvevugia ?? "N/A"}</strong>
                  </div>

                  <div className="metric">
                    <span>Thu Bon Flow</span>
                    <strong>{pcttLatest.qvethubon ?? "N/A"}</strong>
                  </div>
                </div>
              </>
            ) : (
              <p>No PCTT data available.</p>
            )}
          </div>
        </section>

        {/* =========================================================
            WEBGIS MAP
        ========================================================= */}
        <section className="card map-card">
          <div className="card-header">
            <h2>Hydrology WebGIS</h2>

            <span>Station overview</span>
          </div>

          <MapContainer
            center={[16.047, 108.206]}
            zoom={11}
            scrollWheelZoom={true}
            className="map"
          >
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/">OpenStreetMap</a>'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />

            {stations.map((station) => {
              const coordinates =
                STATION_COORDINATES[station.station_id];

              if (!coordinates) {
                return null;
              }

              return (
                <CircleMarker
                  key={station.station_id}
                  center={coordinates}
                  radius={9}
                  pathOptions={{
                    fillOpacity: 0.8,
                  }}
                >
                  <Popup>
                    <strong>
                      Station {station.station_id}
                    </strong>

                    <br />

                    Latest value:{" "}
                    {station.latest_value ?? "N/A"}

                    <br />

                    Valid observations:{" "}
                    {station.valid_observations}
                  </Popup>
                </CircleMarker>
              );
            })}
          </MapContainer>
        </section>

        {/* =========================================================
            FORECAST
        ========================================================= */}
        <section className="bottom-grid">
          <div className="card forecast-card">
            <div className="card-header">
              <div>
                <h2>24-Hour Forecast</h2>

                {selectedStation && (
                  <span>
                    Station {selectedStation.station_id} · Random Forest
                  </span>
                )}
              </div>

              {loadingForecast && <span>Loading...</span>}
            </div>

            {forecast && (
              <div className="forecast-metrics">
                <div>
                  <span>MAE</span>

                  <strong>
                    {forecast.metrics?.mae?.toFixed(4) ?? "N/A"}
                  </strong>
                </div>

                <div>
                  <span>RMSE</span>

                  <strong>
                    {forecast.metrics?.rmse?.toFixed(4) ?? "N/A"}
                  </strong>
                </div>

                <div>
                  <span>Forecast Points</span>

                  <strong>
                    {forecast.forecast?.length ?? 0}
                  </strong>
                </div>
              </div>
            )}

            <div className="chart-container">
              {loadingForecast ? (
                <p>Generating forecast...</p>
              ) : forecastChartData.length > 0 ? (
                <ResponsiveContainer width="100%" height={320}>
                  <LineChart data={forecastChartData}>
                    <CartesianGrid strokeDasharray="3 3" />

                    <XAxis dataKey="time" />

                    <YAxis />

                    <Tooltip />

                    <Legend />

                    <Line
                      type="monotone"
                      dataKey="value"
                      name="Predicted value"
                      strokeWidth={2}
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <p>No forecast data available.</p>
              )}
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}

export default App;