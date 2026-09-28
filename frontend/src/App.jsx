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

const VIETNAM_TIMEZONE = "Asia/Ho_Chi_Minh";

/*
 * Official PCTT normal operating water levels.
 *
 * Reservoir mapping:
 *
 * htl1 -> A Vương
 * htl2 -> Đăk Mi 4
 * htl3 -> Sông Bung 4
 * htl4 -> Sông Tranh 2
 *
 * Reference levels:
 *
 * A Vương      : 380 m
 * Đăk Mi 4     : 258 m
 * Sông Bung 4  : 222.5 m
 * Sông Tranh 2 : 175 m
 */
const PCTT_RESERVOIRS = {
  htl1: {
    name: "A Vương",
    normalLevel: 380,
    inflowKey: "qvao1",
  },

  htl2: {
    name: "Đăk Mi 4",
    normalLevel: 258,
    inflowKey: "qvao2",
  },

  htl3: {
    name: "Sông Bung 4",
    normalLevel: 222.5,
    inflowKey: "qvao3",
  },

  htl4: {
    name: "Sông Tranh 2",
    normalLevel: 175,
    inflowKey: "qvao4",
  },
};


/* ================================================================
   TIME FORMATTING
================================================================ */

function formatVietnamTime(timestamp) {
  if (!timestamp) {
    return "N/A";
  }

  const date = new Date(timestamp);

  if (Number.isNaN(date.getTime())) {
    return "N/A";
  }

  return `${new Intl.DateTimeFormat("en-GB", {
    timeZone: VIETNAM_TIMEZONE,
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date)} (Vietnam time)`;
}


/* ================================================================
   NUMBER FORMATTING
================================================================ */

function formatNumber(value, decimals = 2) {
  if (value === null || value === undefined || value === "") {
    return "N/A";
  }

  const number = Number(value);

  if (!Number.isFinite(number)) {
    return "N/A";
  }

  return number.toFixed(decimals);
}


/* ================================================================
   RESERVOIR NORMAL-LEVEL CALCULATIONS
================================================================ */

function calculateNormalPercentage(currentLevel, normalLevel) {
  const current = Number(currentLevel);
  const normal = Number(normalLevel);

  if (
    !Number.isFinite(current) ||
    !Number.isFinite(normal) ||
    normal === 0
  ) {
    return null;
  }

  return (current / normal) * 100;
}


/* ================================================================
   APP
================================================================ */

function App() {
  const [stations, setStations] = useState([]);
  const [selectedStation, setSelectedStation] = useState(null);
  const [forecast, setForecast] = useState(null);
  const [pcttLatest, setPcttLatest] = useState(null);

  const [loadingStations, setLoadingStations] = useState(true);
  const [loadingForecast, setLoadingForecast] = useState(false);
  const [loadingPctt, setLoadingPctt] = useState(true);

  const [error, setError] = useState(null);


  /* ==============================================================
     INITIAL DATA LOAD
  ============================================================== */

  useEffect(() => {
    loadStations();
    loadPcttLatest();
  }, []);


  /* ==============================================================
     LOAD FORECAST WHEN STATION CHANGES
  ============================================================== */

  useEffect(() => {
    if (selectedStation) {
      loadForecast(selectedStation.station_id);
    }
  }, [selectedStation]);


  /* ==============================================================
     LOAD HYDROLOGY STATIONS
  ============================================================== */

  async function loadStations() {
    try {
      setLoadingStations(true);
      setError(null);

      const response = await fetch(
        `${API_BASE_URL}/stations`
      );

      if (!response.ok) {
        throw new Error(
          "Failed to load stations."
        );
      }

      const data = await response.json();

      setStations(data);

      if (data.length > 0) {
        setSelectedStation(data[0]);
      }

    } catch (err) {

      console.error(
        "Station loading error:",
        err
      );

      setError(err.message);

    } finally {

      setLoadingStations(false);
    }
  }


  /* ==============================================================
     LOAD FORECAST
  ============================================================== */

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

      console.log(
        "Forecast API response:",
        data
      );

      setForecast(data);

    } catch (err) {

      console.error(
        "Forecast loading error:",
        err
      );

      setError(err.message);

    } finally {

      setLoadingForecast(false);
    }
  }


  /* ==============================================================
     LOAD PCTT LATEST DATA
  ============================================================== */

  async function loadPcttLatest() {

    try {

      setLoadingPctt(true);
      setError(null);

      const response = await fetch(
        `${API_BASE_URL}/pctt/latest`
      );

      if (!response.ok) {
        throw new Error(
          "Failed to load PCTT data."
        );
      }

      const data = await response.json();

      console.log(
        "PCTT API response:",
        data
      );

      setPcttLatest(data);

    } catch (err) {

      console.error(
        "PCTT loading error:",
        err
      );

      setError(err.message);

    } finally {

      setLoadingPctt(false);
    }
  }


  /* ==============================================================
     FORECAST CHART DATA
  ============================================================== */

  const forecastChartData =
    forecast?.forecast?.map((item) => ({
      time: new Date(
        item.timestamp
      ).toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
      }),

      value: item.value,
    })) ?? [];


  /* ==============================================================
     STATIONS WITH VERIFIED COORDINATES
  ============================================================== */

  const stationsWithCoordinates =
    stations.filter(
      (station) =>
        station.latitude !== null &&
        station.longitude !== null &&
        Number.isFinite(
          Number(station.latitude)
        ) &&
        Number.isFinite(
          Number(station.longitude)
        )
    );


  /* ==============================================================
     RESERVOIR METRIC COMPONENT
  ============================================================== */

  function ReservoirMetric({
    reservoirKey,
    waterLevel,
    inflow,
  }) {

    const reservoir =
      PCTT_RESERVOIRS[reservoirKey];

    const currentLevel =
      Number(waterLevel);

    const normalLevel =
      Number(reservoir.normalLevel);

    const hasValidLevels =
      Number.isFinite(currentLevel) &&
      Number.isFinite(normalLevel) &&
      normalLevel !== 0;

    const difference =
      hasValidLevels
        ? currentLevel - normalLevel
        : null;

    const percentage =
      calculateNormalPercentage(
        currentLevel,
        normalLevel
      );


    return (
      <>

        {/* ========================================================
            WATER LEVEL
        ======================================================== */}

        <div className="metric reservoir-level-metric">

          <span>
            {reservoir.name} Water Level (m)
          </span>

          <strong>
            {formatNumber(waterLevel)}
          </strong>

          <small>
            Normal operating level:{" "}
            {formatNumber(
              reservoir.normalLevel
            )}{" "}
            m
          </small>

          {difference !== null && (
            <small>
              Difference from normal:{" "}
              {difference >= 0
                ? "+"
                : ""}
              {formatNumber(
                difference
              )}{" "}
              m
            </small>
          )}

          {percentage !== null && (
            <small>
              {formatNumber(
                percentage
              )}
              % of normal level
            </small>
          )}

        </div>


        {/* ========================================================
            INFLOW
        ======================================================== */}

        <div className="metric">

          <span>
            {reservoir.name} Inflow (m³/s)
          </span>

          <strong>
            {formatNumber(inflow)}
          </strong>

        </div>

      </>
    );
  }


  /* ==============================================================
     UI
  ============================================================== */

  return (
    <div className="app">

      {/* =========================================================
          HEADER
      ========================================================= */}

      <header className="header">

        <div>

          <h1>
            Hydrometeorological AI Forecasting
          </h1>

          <p>
            Multi-source hydrology, hydropower and AI forecasting platform
          </p>

        </div>


        <div className="status">

          <span className="status-dot"></span>

          API Connected

        </div>

      </header>


      {/* =========================================================
          ERROR MESSAGE
      ========================================================= */}

      {error && (
        <div className="error-banner">
          {error}
        </div>
      )}


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

              <h2>
                Hydrology Stations
              </h2>

              <span>

                {loadingStations
                  ? "Loading..."
                  : `${stations.length} stations`}

              </span>

            </div>


            {loadingStations ? (

              <p>
                Loading stations...
              </p>

            ) : stations.length === 0 ? (

              <p>
                No stations available.
              </p>

            ) : (

              <div className="station-list">

                {stations.map(
                  (station) => (

                    <button
                      key={
                        station.station_id
                      }

                      className={`station-item ${
                        selectedStation?.station_id ===
                        station.station_id
                          ? "active"
                          : ""
                      }`}

                      onClick={() =>
                        setSelectedStation(
                          station
                        )
                      }
                    >

                      <div>

                        <strong>
                          Station{" "}
                          {
                            station.station_id
                          }
                        </strong>

                        <span>

                          {
                            station.valid_observations
                          }{" "}
                          valid observations

                        </span>

                      </div>


                      <div className="station-value">

                        {
                          station.latest_value ??
                          "N/A"
                        }

                      </div>

                    </button>

                  )
                )}

              </div>

            )}

          </div>


          {/* =======================================================
              PCTT HYDROPOWER
          ======================================================= */}

          <div className="card pctt-card">

            <div className="card-header">

              <div>

                <h2>
                  PCTT Hydropower
                </h2>

                <span>
                  Latest observation · Vietnam time
                </span>

              </div>

            </div>


            {loadingPctt ? (

              <p>
                Loading PCTT data...
              </p>

            ) : pcttLatest ? (

              <>

                {/* =================================================
                    OBSERVATION TIME
                ================================================= */}

                <p className="observation-time">

                  {formatVietnamTime(
                    pcttLatest.timestamp
                  )}

                </p>


                {/* =================================================
                    RESERVOIR METRICS
                ================================================= */}

                <div className="pctt-grid">


                  {/* =================================================
                      A VƯƠNG
                  ================================================= */}

                  <ReservoirMetric
                    reservoirKey="htl1"
                    waterLevel={
                      pcttLatest.htl1
                    }
                    inflow={
                      pcttLatest.qvao1
                    }
                  />


                  {/* =================================================
                      ĐĂK MI 4
                  ================================================= */}

                  <ReservoirMetric
                    reservoirKey="htl2"
                    waterLevel={
                      pcttLatest.htl2
                    }
                    inflow={
                      pcttLatest.qvao2
                    }
                  />


                  {/* =================================================
                      SÔNG BUNG 4
                  ================================================= */}

                  <ReservoirMetric
                    reservoirKey="htl3"
                    waterLevel={
                      pcttLatest.htl3
                    }
                    inflow={
                      pcttLatest.qvao3
                    }
                  />


                  {/* =================================================
                      SÔNG TRANH 2
                  ================================================= */}

                  <ReservoirMetric
                    reservoirKey="htl4"
                    waterLevel={
                      pcttLatest.htl4
                    }
                    inflow={
                      pcttLatest.qvao4
                    }
                  />


                  {/* =================================================
                      VU GIA
                  ================================================= */}

                  <div className="metric">

                    <span>
                      Vu Gia Flow (m³/s)
                    </span>

                    <strong>

                      {
                        formatNumber(
                          pcttLatest.qvevugia
                        )
                      }

                    </strong>

                  </div>


                  {/* =================================================
                      THU BON
                  ================================================= */}

                  <div className="metric">

                    <span>
                      Thu Bon Flow (m³/s)
                    </span>

                    <strong>

                      {
                        formatNumber(
                          pcttLatest.qvethubon
                        )
                      }

                    </strong>

                  </div>


                </div>

              </>

            ) : (

              <p>
                No PCTT data available.
              </p>

            )}

          </div>

        </section>


        {/* =========================================================
            WEBGIS MAP
        ========================================================= */}

        <section className="card map-card">


          <div className="card-header">

            <div>

              <h2>
                Hydrology WebGIS
              </h2>

              <span>
                Database-driven station locations
              </span>

            </div>


            <span>

              {
                stationsWithCoordinates.length
              }{" "}
              mapped

            </span>

          </div>


          <MapContainer
            center={[
              16.0,
              108.0,
            ]}
            zoom={7}
            scrollWheelZoom={true}
            className="map"
          >

            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/">OpenStreetMap</a>'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />


            {stationsWithCoordinates.map(
              (station) => {

                const coordinates = [
                  Number(
                    station.latitude
                  ),

                  Number(
                    station.longitude
                  ),
                ];


                return (

                  <CircleMarker
                    key={
                      station.station_id
                    }

                    center={
                      coordinates
                    }

                    radius={9}

                    pathOptions={{
                      fillOpacity: 0.8,
                    }}
                  >

                    <Popup>

                      <strong>

                        Station{" "}
                        {
                          station.station_id
                        }

                      </strong>

                      <br />

                      Type:{" "}
                      {
                        station.station_type ??
                        "N/A"
                      }

                      <br />

                      Latest value:{" "}
                      {
                        station.latest_value ??
                        "N/A"
                      }

                      <br />

                      Valid observations:{" "}
                      {
                        station.valid_observations
                      }

                    </Popup>

                  </CircleMarker>

                );

              }
            )}

          </MapContainer>


          {stationsWithCoordinates.length === 0 && (

            <p className="observation-time">

              Station coordinates have not been
              verified and stored yet.
              The map is therefore showing no
              station markers.

            </p>

          )}

        </section>


        {/* =========================================================
            FORECAST
        ========================================================= */}

        <section className="bottom-grid">


          <div className="card forecast-card">


            <div className="card-header">

              <div>

                <h2>
                  24-Hour Forecast
                </h2>


                {selectedStation && (

                  <span>

                    Station{" "}
                    {
                      selectedStation.station_id
                    }{" "}
                    · Random Forest

                  </span>

                )}

              </div>


              {loadingForecast && (

                <span>
                  Loading...
                </span>

              )}

            </div>


            {forecast && (

              <div className="forecast-metrics">


                <div>

                  <span>
                    MAE
                  </span>

                  <strong>

                    {
                      forecast.metrics?.mae?.toFixed(
                        4
                      ) ?? "N/A"
                    }

                  </strong>

                </div>


                <div>

                  <span>
                    RMSE
                  </span>

                  <strong>

                    {
                      forecast.metrics?.rmse?.toFixed(
                        4
                      ) ?? "N/A"
                    }

                  </strong>

                </div>


                <div>

                  <span>
                    Forecast Points
                  </span>

                  <strong>

                    {
                      forecast.forecast?.length ??
                      0
                    }

                  </strong>

                </div>


              </div>

            )}


            <div className="chart-container">


              {loadingForecast ? (

                <p>
                  Generating forecast...
                </p>

              ) : forecastChartData.length > 0 ? (

                <ResponsiveContainer
                  width="100%"
                  height={320}
                >

                  <LineChart
                    data={
                      forecastChartData
                    }
                  >

                    <CartesianGrid
                      strokeDasharray="3 3"
                    />

                    <XAxis
                      dataKey="time"
                    />

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

                <p>
                  No forecast data available.
                </p>

              )}

            </div>


          </div>

        </section>


      </main>

    </div>
  );
}

export default App;