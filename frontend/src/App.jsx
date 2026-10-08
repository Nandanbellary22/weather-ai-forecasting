import { useEffect, useRef, useState } from "react";



import {

  CircleMarker,

  MapContainer,

  Popup,

  TileLayer,

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



  useEffect(() => {

    if (!location) {

      return;

    }



    map.setView(

      [location.latitude, location.longitude],

      8,

      { animate: true }

    );

  }, [location, map]);



  return null;

}



function App() {

  const [mode, setMode] = useState("weather");
  const [weatherMetric, setWeatherMetric] = useState("temperature");



  // Weather

  const [selectedLocation, setSelectedLocation] = useState(null);
  const [weatherLocations, setWeatherLocations] = useState([]);
  const [weatherLocationsLoading, setWeatherLocationsLoading] = useState(false);
  const [weatherLocationsError, setWeatherLocationsError] = useState(null);

  const [temperature, setTemperature] = useState(null);

  const [rainfall, setRainfall] = useState(null);

  const [loading, setLoading] = useState(false);

  const [error, setError] = useState(null);
  const [spatialProfile, setSpatialProfile] = useState(null);
  const [spatialLoading, setSpatialLoading] = useState(false);
  const [spatialError, setSpatialError] = useState(null);
  const spatialRequestId = useRef(0);



  // PCTT reservoirs

  const [hydrology, setHydrology] = useState(null);

  const [selectedReservoir, setSelectedReservoir] = useState(null);

  const [hydroLoading, setHydroLoading] = useState(false);

  const [hydroError, setHydroError] = useState(null);



  // Hydrology stations

  const [stations, setStations] = useState([]);

  const [stationsLoading, setStationsLoading] = useState(false);

  const [stationsError, setStationsError] = useState(null);



  const [selectedStation, setSelectedStation] = useState(null);

  const [stationHistory, setStationHistory] = useState([]);

  const [stationHistoryLoading, setStationHistoryLoading] = useState(false);

  const [stationHistoryError, setStationHistoryError] = useState(null);



  async function loadWeatherLocations() {
    setWeatherLocationsLoading(true);
    setWeatherLocationsError(null);

    try {
      const response = await fetch(`${API_BASE_URL}/weather/locations?limit=500`);
      if (!response.ok) {
        throw new Error(`Weather locations request failed (${response.status}).`);
      }

      const data = await response.json();
      const normalized = (Array.isArray(data) ? data : [])
        .map((item) => ({
          code: String(item.location_code),
          name: String(item.location_code).startsWith("GRID_")
            ? `Weather Grid ${String(item.location_code).replace("GRID_", "")}`
            : String(item.location_code),
          latitude: Number(item.latitude),
          longitude: Number(item.longitude),
          timestamp: item.timestamp,
          currentTemperature: item.temperature_c,
          currentRainfall: item.rainfall_mm,
          humidity: item.relative_humidity_2m ?? item.humidity,
          dewPoint: item.dew_point_2m ?? item.dew_point,
          pressure: item.pressure_msl ?? item.surface_pressure,
          surfacePressure: item.surface_pressure,
          windSpeed: item.wind_speed_10m ?? item.wind_speed,
          windDirection: item.wind_direction_10m ?? item.wind_direction,
          windGusts: item.wind_gusts_10m ?? item.wind_gusts,
          cloudCover: item.cloud_cover,
        }))
        .filter(
          (item) => Number.isFinite(item.latitude) && Number.isFinite(item.longitude)
        );

      if (!normalized.length) {
        throw new Error("No weather locations were returned by the API.");
      }

      setWeatherLocations(normalized);
    } catch (err) {
      setWeatherLocationsError(err.message || "Unable to load weather locations.");
      setWeatherLocations([]);
    } finally {
      setWeatherLocationsLoading(false);
    }
  }

  useEffect(() => {
    loadWeatherLocations();
  }, []);

  async function loadWeather(location) {
    const requestId = ++spatialRequestId.current;

    setSelectedLocation(location);

    setSelectedReservoir(null);

    setSelectedStation(null);



    setTemperature(null);

    setRainfall(null);

    setError(null);

    setSpatialProfile(null);
    setSpatialError(null);
    setSpatialLoading(true);

    fetch(`${API_BASE_URL}/spatial/location/${encodeURIComponent(location.code)}`)
      .then(async (response) => {
        if (!response.ok) throw new Error(`Spatial profile request failed (${response.status}).`);
        return response.json();
      })
      .then((profile) => {
        if (requestId === spatialRequestId.current) setSpatialProfile(profile);
      })
      .catch((err) => {
        if (requestId === spatialRequestId.current) {
          setSpatialError(err.message || "Unable to load spatial context.");
        }
      })
      .finally(() => {
        if (requestId === spatialRequestId.current) setSpatialLoading(false);
      });



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



      const [temperatureData, rainfallData] =

        await Promise.all([

          temperatureResponse.json(),

          rainfallResponse.json(),

        ]);



      setTemperature(temperatureData);

      setRainfall(rainfallData);

    } catch (err) {

      setError(

        err.message ||

          "Unable to load weather forecast."

      );

    } finally {

      setLoading(false);

    }

  }



  async function loadHydrology(reservoir) {

    setSelectedReservoir(reservoir);

    setSelectedStation(null);



    setStationHistory([]);

    setStationHistoryError(null);



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

      setHydroError(

        err.message ||

          "Unable to load hydrological data."

      );

    } finally {

      setHydroLoading(false);

    }

  }



  async function loadStations() {

    setStationsLoading(true);

    setStationsError(null);



    try {

      const response = await fetch(

        `${API_BASE_URL}/stations`

      );



      if (!response.ok) {

        throw new Error(

          "Unable to load hydrology stations."

        );

      }



      const data = await response.json();



      setStations(

        Array.isArray(data)

          ? data

          : []

      );

    } catch (err) {

      setStationsError(

        err.message ||

          "Unable to load hydrology stations."

      );

    } finally {

      setStationsLoading(false);

    }

  }



  async function loadStationHistory(station) {

    setSelectedStation(station);

    setSelectedReservoir(null);



    setStationHistory([]);

    setStationHistoryError(null);

    setStationHistoryLoading(true);



    try {

      const response = await fetch(

        `${API_BASE_URL}/stations/${station.station_id}/history?limit=24`

      );



      if (!response.ok) {

        let message =

          `Unable to load history for station ${station.station_id}.`;



        try {

          const data = await response.json();



          if (data?.detail) {

            message = data.detail;

          }

        } catch {

          // Keep default message.

        }



        throw new Error(message);

      }



      const data = await response.json();



      setStationHistory(

        Array.isArray(data)

          ? data

          : []

      );

    } catch (err) {

      setStationHistoryError(

        err.message ||

          "Unable to load station history."

      );

    } finally {

      setStationHistoryLoading(false);

    }

  }



  function changeMode(newMode) {

    setMode(newMode);



    setSelectedLocation(null);

    setSelectedReservoir(null);

    setSelectedStation(null);



    setTemperature(null);

    setRainfall(null);

    setHydrology(null);

    setStationHistory([]);



    setError(null);

    setHydroError(null);

    setStationsError(null);

    setStationHistoryError(null);



    if (

      newMode === "hydrology" &&

      stations.length === 0

    ) {

      loadStations();

    }

  }



  function getStationStats() {
    const values = stationHistory
      .map((item) => Number(item.value))
      .filter((value) => Number.isFinite(value));

    if (!values.length) {
      return { latest: null, previous: null, change: null, min: null, max: null };
    }

    const latest = values[values.length - 1];
    const previous = values.length > 1 ? values[values.length - 2] : null;

    return {
      latest,
      previous,
      change: previous === null ? null : latest - previous,
      min: Math.min(...values),
      max: Math.max(...values),
    };
  }

  function getHydroValue(

    reservoirId,

    field

  ) {

    if (!hydrology) {

      return null;

    }



    const fields =

      HYDRO_FIELDS[reservoirId];



    if (!fields) {

      return null;

    }



    return hydrology[

      fields[field]

    ];

  }



  function getWeatherMetricValue(location) {
    return weatherMetric === "rainfall"
      ? Number(location.currentRainfall)
      : Number(location.currentTemperature);
  }

  function getWeatherMarkerColor(location) {
    const value = getWeatherMetricValue(location);
    if (!Number.isFinite(value)) return "#64748b";
    if (weatherMetric === "rainfall") {
      if (value <= 0) return "#60a5fa";
      if (value < 1) return "#38bdf8";
      if (value < 5) return "#22c55e";
      if (value < 15) return "#f59e0b";
      return "#dc2626";
    }
    if (value < 10) return "#2563eb";
    if (value < 18) return "#06b6d4";
    if (value < 24) return "#22c55e";
    if (value < 30) return "#f59e0b";
    return "#dc2626";
  }

  function formatValue(

    value,

    digits = 2

  ) {

    if (

      value === null ||

      value === undefined ||

      value === ""

    ) {

      return "—";

    }



    const numericValue =

      Number(value);



    if (

      !Number.isFinite(numericValue)

    ) {

      return "—";

    }



    return numericValue.toFixed(

      digits

    );

  }

  function displayValue(value, digits = 2) {
    return value === null || value === undefined || value === "" || !Number.isFinite(Number(value))
      ? "—"
      : Number(value).toFixed(digits);
  }

  const nearestMrc = spatialProfile?.nearest_mrc;
  const rawMrcDistance = nearestMrc?.distance_km;
  const mrcDistance = rawMrcDistance === null || rawMrcDistance === undefined || String(rawMrcDistance).trim() === ""
    ? null
    : Number(rawMrcDistance);
  const hasMrcDistance = mrcDistance !== null && Number.isFinite(mrcDistance);
  const proximity = hasMrcDistance
    ? mrcDistance <= 25 ? "Nearby" : mrcDistance <= 75 ? "Regional" : mrcDistance <= 150 ? "Distant" : "Limited nearby hydrological coverage"
    : null;



  return (

    <div className="app">



      <header className="header">
        <div>
          <h1>Vietnam Weather</h1>
          <p>Weather conditions and forecasts across Vietnam</p>
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



          {mode === "weather" && (
            <div
              style={{
                position: "absolute", top: 12, left: 12, zIndex: 1000,
                background: "rgba(255,255,255,0.96)", padding: "9px 11px",
                borderRadius: 10, boxShadow: "0 3px 12px rgba(15,23,42,0.18)",
                fontSize: 12, fontWeight: 600, minWidth: 185,
              }}
            >
              <div style={{ marginBottom: "7px", color: "#334155", fontWeight: 700 }}>
                Map layer
              </div>
              <div style={{ display: "flex", gap: "5px" }}>
                {[
                  ["temperature", "Temperature"],
                  ["rainfall", "Rainfall"],
                ].map(([metric, label]) => (
                  <button
                    key={metric}
                    type="button"
                    onClick={() => setWeatherMetric(metric)}
                    style={{
                      border: "1px solid #cbd5e1", borderRadius: "999px", padding: "4px 8px",
                      background: weatherMetric === metric ? "#eff6ff" : "white",
                      color: weatherMetric === metric ? "#1d4ed8" : "#475569",
                      fontSize: "11px", fontWeight: 700, cursor: "pointer",
                    }}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
          )}

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

              weatherLocations.map(

                (location) => (

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
                        selectedLocation?.code === location.code
                          ? "#111827"
                          : getWeatherMarkerColor(location),

                      fillColor:
                        selectedLocation?.code === location.code
                          ? "#ef4444"
                          : getWeatherMarkerColor(location),

                      fillOpacity: selectedLocation?.code === location.code ? 0.95 : 0.65,
                      weight: selectedLocation?.code === location.code ? 2 : 1,

                    }}

                    eventHandlers={{

                      click: () =>

                        loadWeather(

                          location

                        ),

                    }}

                  >



                    <Popup>
                      <strong>{location.name}</strong>
                      <br />
                      {location.code}
                      <br />
                      {location.currentTemperature !== undefined && location.currentTemperature !== null
                        ? `Temperature: ${formatValue(location.currentTemperature, 1)} °C`
                        : "Temperature: —"}
                      <br />
                      {location.currentRainfall !== undefined && location.currentRainfall !== null
                        ? `Rainfall: ${formatValue(location.currentRainfall, 2)} mm`
                        : "Rainfall: —"}
                      <br />
                      View forecast
                    </Popup>



                  </CircleMarker>

                )

              )}



            {mode === "hydrology" &&

              RESERVOIRS.map(

                (reservoir) => (

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

                        loadHydrology(

                          reservoir

                        ),

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

                )

              )}



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



          {/* ========================= */}

          {/* WEATHER MODE               */}

          {/* ========================= */}



          {mode === "weather" &&

            !selectedLocation && (

              <div className="empty-state">



                <div className="big-icon">

                  ☁

                </div>



                <h3>

                  Select a location

                </h3>



                <p>

                  Select a location to view

                  weather details and the next-hour forecast.

                </p>



              </div>

            )}



          {mode === "weather" &&

            selectedLocation && (

              <div>



                <div className="location-header">



                  <span>

                    Weather conditions

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

                    Loading forecast...

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

                      <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "10px", marginBottom: "12px" }}>
                        <div className="forecast-card">
                          <span>Latest temperature</span>
                          <strong>{temperature.current_temperature_c}°C</strong>
                          <p>Next hour forecast</p>
                          <div className="prediction-value">{temperature.predicted_next_hour_temperature_c}°C</div>
                        </div>
                        <div className="forecast-card rainfall-card">
                          <span>Latest rainfall</span>
                          <strong>{rainfall.current_rainfall_mm} mm</strong>
                          <p>Next hour forecast</p>
                          <div className="prediction-value">{rainfall.predicted_next_hour_rainfall_mm} mm</div>
                        </div>
                      </div>

                      <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "10px" }}>
                        {[
                          ["Humidity", selectedLocation.humidity, "%"],
                          ["Wind speed", selectedLocation.windSpeed, "km/h"],
                          ["Wind gusts", selectedLocation.windGusts, "km/h"],
                          ["Pressure", selectedLocation.pressure, "hPa"],
                          ["Cloud cover", selectedLocation.cloudCover, "%"],
                          ["Dew point", selectedLocation.dewPoint, "°C"],
                          ["Wind direction", selectedLocation.windDirection, "°"],
                        ].map(([label, value, unit]) => (
                          <div key={label} className="hydro-card" style={{ margin: 0 }}>
                            <span>{label}</span>
                            <strong>{value === null || value === undefined || Number.isNaN(Number(value)) ? "—" : `${formatValue(value, 1)} ${unit}`}</strong>
                          </div>
                        ))}
                      </div>

                      <div className="timestamp" style={{ marginTop: "12px" }}>
                        Latest available observation:
                        <br />
                        {new Date(temperature.timestamp).toLocaleString()}
                      </div>
                    </div>
                  )}

                <section className="spatial-context">
                  <h3>Spatial &amp; Hydrological Context</h3>
                  <div className="spatial-point">
                    <strong>Weather grid/model location</strong>
                    <span>{displayValue(spatialProfile?.location?.latitude ?? selectedLocation.latitude, 4)}, {displayValue(spatialProfile?.location?.longitude ?? selectedLocation.longitude, 4)}</span>
                    <span>Location type: {String(selectedLocation.code).startsWith("GRID_") ? "Weather grid point" : "Weather location / model point"}</span>
                  </div>
                  {spatialLoading && <p className="timestamp">Loading hydrological context…</p>}
                  {spatialError && <p className="spatial-error">Spatial context unavailable: {spatialError}</p>}
                  {nearestMrc && <>
                    <div className="spatial-point station-point">
                      <strong>Actual hydrological monitoring station</strong>
                      <span>{nearestMrc.station_name || "Unnamed station"} ({nearestMrc.station_id || "—"})</span>
                      <span>Coordinates: {displayValue(nearestMrc.station_latitude, 4)}, {displayValue(nearestMrc.station_longitude, 4)}</span>
                      <span>Distance: {hasMrcDistance ? `${displayValue(mrcDistance, 3)} km · ${proximity}` : "Distance unavailable"}</span>
                      {hasMrcDistance && mrcDistance > 75 && <em>This station may not represent conditions at the weather location precisely.</em>}
                    </div>
                    <div className="spatial-grid">
                      <div><span>River</span><strong>{nearestMrc.river || "—"}</strong></div>
                      <div><span>Water level</span><strong>{displayValue(nearestMrc.water_level)}{nearestMrc.water_level == null ? "" : " m"}</strong></div>
                      <div><span>MRC rainfall</span><strong>{displayValue(nearestMrc.rainfall)}{nearestMrc.rainfall == null ? "" : " mm"}</strong></div>
                      <div><span>MRC observation</span><strong>{nearestMrc.latest_measurement ? new Date(nearestMrc.latest_measurement).toLocaleString() : "Unavailable"}</strong></div>
                      <div><span>Historical discharge</span><strong>{nearestMrc.discharge_available ? "Available" : "Unavailable"}</strong></div>
                      <div><span>Discharge observations</span><strong>{displayValue(nearestMrc.discharge_observations, 0)}</strong></div>
                      <div className="spatial-range"><span>Discharge date range</span><strong>{nearestMrc.discharge_first_date && nearestMrc.discharge_last_date ? `${new Date(nearestMrc.discharge_first_date).toLocaleDateString()} – ${new Date(nearestMrc.discharge_last_date).toLocaleDateString()}` : "Unavailable"}</strong></div>
                    </div>
                  </>}
                  {!spatialLoading && !spatialError && spatialProfile && !nearestMrc && <p className="timestamp">No nearby MRC station data is available.</p>}
                </section>

              </div>

            )}



          {/* ========================= */}

          {/* HYDROLOGY MODE             */}

          {/* ========================= */}



          {mode === "hydrology" && (

            <div>



              {/* Station registry */}



              <div

                className="hydro-section"

                style={{

                  marginBottom: "20px",

                }}

              >



                <div className="location-header">



                  <span>

                    Confirmed hydrology network

                  </span>



                  <h2>

                    {stations.length || 28} stations

                  </h2>



                  <p>

                    Station registry from

                    PostgreSQL + FastAPI.

                    Coordinates are shown only

                    when reliable metadata is available.

                  </p>



                </div>



                {stationsLoading && (

                  <div className="loading">

                    Loading hydrology stations...

                  </div>

                )}



                {stationsError && (

                  <div className="error">

                    {stationsError}

                  </div>

                )}



                {!stationsLoading &&

                  !stationsError &&

                  stations.length > 0 && (



                    <div

                      style={{

                        display: "grid",

                        gridTemplateColumns:

                          "repeat(2, minmax(0, 1fr))",

                        gap: "8px",

                        maxHeight: "250px",

                        overflowY: "auto",

                        paddingRight: "4px",

                      }}

                    >



                      {stations.map(

                        (station) => {



                          const isSelected =

                            selectedStation?.station_id ===

                            station.station_id;



                          return (

                            <button

                              key={

                                station.station_id

                              }

                              type="button"

                              onClick={() =>

                                loadStationHistory(

                                  station

                                )

                              }

                              style={{

                                textAlign: "left",

                                border: isSelected

                                  ? "2px solid #047857"

                                  : "1px solid #d1d5db",

                                borderRadius: "10px",

                                padding: "9px 10px",

                                background:

                                  isSelected

                                    ? "#ecfdf5"

                                    : "white",

                                cursor: "pointer",

                              }}

                            >



                              <strong>

                                Station{" "}

                                {

                                  station.station_id

                                }

                              </strong>



                              <div

                                style={{

                                  fontSize: "12px",

                                  marginTop: "4px",

                                }}

                              >

                                {

                                  station.observations

                                }{" "}

                                observations

                              </div>



                              <div

                                style={{

                                  fontSize: "12px",

                                  marginTop: "2px",

                                }}

                              >

                                Latest:{" "}

                                {formatValue(

                                  station.latest_value

                                )}

                              </div>



                            </button>

                          );

                        }

                      )}



                    </div>

                  )}



              </div>



              {/* Selected station */}



              {selectedStation && (

                <div

                  className="forecast-content"

                  style={{

                    marginBottom: "20px",

                  }}

                >



                  <div className="location-header">



                    <span>

                      Selected hydrology station

                    </span>



                    <h2>

                      {

                        selectedStation.station_id

                      }

                    </h2>



                    <p>

                      {selectedStation.station_name ||

                        "Metadata name unavailable"}

                    </p>



                  </div>



                  {stationHistoryLoading && (

                    <div className="loading">

                      Loading recent observations...

                    </div>

                  )}



                  {stationHistoryError && (

                    <div className="error">

                      {stationHistoryError}

                    </div>

                  )}



                  {!stationHistoryLoading &&
                    !stationHistoryError &&
                    stationHistory.length > 0 && (
                      <>
                        {(() => {
                          const stats = getStationStats();
                          const latestObservation = stationHistory[stationHistory.length - 1];
                          const trendUp = stats.change !== null && stats.change > 0;
                          const trendDown = stats.change !== null && stats.change < 0;

                          return (
                            <>
                              <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "10px" }}>
                                <div className="hydro-card" style={{ margin: 0 }}>
                                  <span>Water level</span>
                                  <strong>{formatValue(stats.latest)}</strong>
                                  <p>{new Date(latestObservation.timestamp).toLocaleString()}</p>
                                </div>
                                <div className="hydro-card" style={{ margin: 0 }}>
                                  <span>Change</span>
                                  <strong>{stats.change === null ? "—" : `${stats.change > 0 ? "+" : ""}${formatValue(stats.change)}`}</strong>
                                  <p>vs previous observation</p>
                                </div>
                                <div className="hydro-card" style={{ margin: 0 }}>
                                  <span>24-hour minimum</span>
                                  <strong>{formatValue(stats.min)}</strong>
                                  <p>Recent station range</p>
                                </div>
                                <div className="hydro-card" style={{ margin: 0 }}>
                                  <span>24-hour maximum</span>
                                  <strong>{formatValue(stats.max)}</strong>
                                  <p>Recent station range</p>
                                </div>
                              </div>

                              <div style={{ marginTop: "14px", padding: "12px", borderRadius: "12px", background: "#f8fafc", border: "1px solid #e2e8f0" }}>
                                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
                                  <strong style={{ fontSize: "13px", color: "#334155" }}>Recent water-level trend</strong>
                                  <span style={{ fontSize: "12px", fontWeight: 700, color: trendUp ? "#15803d" : trendDown ? "#dc2626" : "#64748b" }}>{trendUp ? "Rising" : trendDown ? "Falling" : "Stable"}</span>
                                </div>
                                <div style={{ display: "flex", alignItems: "end", gap: "3px", height: "90px" }}>
                                  {stationHistory.map((observation, index) => {
                                    const value = Number(observation.value);
                                    const span = stats.max - stats.min;
                                    const height = span > 0 && Number.isFinite(value) ? 15 + ((value - stats.min) / span) * 65 : 35;
                                    return <div key={`${observation.station_id}-${observation.timestamp}`} title={`${new Date(observation.timestamp).toLocaleString()} — ${formatValue(value)}`} style={{ flex: 1, minWidth: "2px", height: `${height}px`, borderRadius: "3px 3px 1px 1px", background: index === stationHistory.length - 1 ? "#2563eb" : "#93c5fd" }} />;
                                  })}
                                </div>
                                <div style={{ marginTop: "8px", fontSize: "11px", color: "#64748b", display: "flex", justifyContent: "space-between" }}>
                                  <span>{new Date(stationHistory[0].timestamp).toLocaleString()}</span>
                                  <span>{new Date(latestObservation.timestamp).toLocaleString()}</span>
                                </div>
                              </div>
                            </>
                          );
                        })()}
                      </>
                    )}

                </div>
              )}
              {/* Existing PCTT reservoir panel */}



              {selectedReservoir && (

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



              {!selectedReservoir &&

                !selectedStation && (

                  <div className="empty-state">



                    <div className="big-icon">

                      💧

                    </div>



                    <h3>

                      Select a hydrology station

                      or reservoir

                    </h3>



                    <p>

                      Choose a station from the

                      list for recent observations,

                      or click a green reservoir

                      on the map for PCTT monitoring

                      data.

                    </p>



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
