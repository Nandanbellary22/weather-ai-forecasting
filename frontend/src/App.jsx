import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { CircleMarker, MapContainer, Popup, TileLayer, useMap } from "react-leaflet";

import "leaflet/dist/leaflet.css";

import "./App.css";
import RecentWeatherPanel from "./RecentWeatherPanel";
import TemperatureForecastPanel from "./TemperatureForecastPanel";

const API = "http://127.0.0.1:8000";

const NAV = [

  { id: "overview", label: "Overview", icon: "⌂", group: "Workspace" },

  { id: "map", label: "Weather map", icon: "◉", group: "Workspace" },

  { id: "analytics", label: "Weather analytics", icon: "⌁", group: "Workspace" },

  { id: "stations", label: "Hydrology stations", icon: "≋", group: "Monitoring" },

  { id: "reservoirs", label: "Reservoir monitoring", icon: "▤", group: "Monitoring" },

  { id: "forecasts", label: "Forecasts", icon: "↗", group: "Monitoring" },

];

const RESERVOIRS = [

  { id: 1, name: "A Vuong", latitude: 15.979, longitude: 107.519 },

  { id: 2, name: "Dak Mi 4", latitude: 15.936, longitude: 107.853 },

  { id: 3, name: "Song Bung 4", latitude: 15.912, longitude: 107.727 },

  { id: 4, name: "Song Tranh 2", latitude: 15.311, longitude: 108.143 },

];

const RES_FIELDS = {

  1: { level: "htl1", inflow: "qvao1", power: "luuluongnhamay1", spill: "qxaquacua1" },

  2: { level: "htl2", inflow: "qvao2", power: "luuluongnhamay2", spill: "qxaquacua2" },

  3: { level: "htl3", inflow: "qvao3", power: "luuluongnhamay3", spill: "qxaquacua3" },

  4: { level: "htl4", inflow: "qvao4", power: "luuluongnhamay4", spill: "qxaquacua4" },

};

const METRICS = [

  ["currentTemperature", "Temperature", "°C", "温"], ["currentRainfall", "Rainfall", "mm", "雨"],

  ["humidity", "Relative humidity", "%", "%"], ["dewPoint", "Dew point", "°C", "◌"],

  ["pressure", "Mean sea-level pressure", "hPa", "↕"], ["surfacePressure", "Surface pressure", "hPa", "⌑"],

  ["windSpeed", "Wind speed", "km/h", "↗"], ["windDirection", "Wind direction", "°", "➤"],

  ["windGusts", "Wind gusts", "km/h", "〰"], ["cloudCover", "Cloud cover", "%", "☁"],

];



async function getJson(url) {

  const response = await fetch(url);

  if (!response.ok) {

    let message = "Request failed (" + response.status + ").";

    try { const body = await response.json(); if (body && body.detail) message = body.detail; } catch { /* keep status message */ }

    throw new Error(message);

  }

  return response.json();

}

function value(v, digits = 1) {

  return v === null || v === undefined || v === "" || !Number.isFinite(Number(v)) ? "—" : Number(v).toFixed(digits);

}

function stamp(v) {

  if (!v) return "Timestamp unavailable";

  const d = new Date(v);

  return Number.isNaN(d.getTime()) ? "Timestamp unavailable" : d.toLocaleString();

}
function getWeatherFreshness(timestamp) {
  if (!timestamp) {
    return {
      stale: true,
      label: "Weather timestamp unavailable",
    };
  }

  const parsed = new Date(timestamp);

  if (Number.isNaN(parsed.getTime())) {
    return {
      stale: true,
      label: "Weather timestamp invalid",
    };
  }

  const ageHours = (Date.now() - parsed.getTime()) / 3600000;

  if (ageHours < -1) {
    return {
      stale: true,
      label: "Weather timestamp is in the future",
    };
  }

  if (ageHours > 3) {
    return {
      stale: true,
      label: `Weather data is ${ageHours.toFixed(1)} hours old`,
    };
  }

  return {
    stale: false,
    label: `Weather data is current (${Math.max(0, ageHours).toFixed(1)} hours old)`,
  };
}
function MapFocus({ point }) {

  const map = useMap();

  useEffect(() => { if (point && Number.isFinite(Number(point.latitude)) && Number.isFinite(Number(point.longitude))) map.setView([Number(point.latitude), Number(point.longitude)], 8, { animate: true }); }, [point, map]);

  return null;

}

function MapView({ locations, stations, selectedLocation, selectedStation, selectedReservoir, onWeather, onStation, onReservoir, metric, setMetric, layers, setLayers, compact = false }) {

  const point = selectedLocation || (selectedStation && selectedStation.latitude != null ? selectedStation : null);

  function color(item) {

    const n = Number(metric === "rainfall" ? item.currentRainfall : item.currentTemperature);

    if (!Number.isFinite(n)) return "#94a3b8";

    if (metric === "rainfall") return n <= 0 ? "#67e8f9" : n < 5 ? "#22d3ee" : n < 20 ? "#fbbf24" : "#fb7185";

    return n < 10 ? "#60a5fa" : n < 20 ? "#22d3ee" : n < 28 ? "#34d399" : "#fb923c";

  }

  return <div className={compact ? "map-frame map-frame-compact" : "map-frame"}>

    <MapContainer center={[16.5, 106]} zoom={6} scrollWheelZoom className="map-canvas">

      <TileLayer attribution="&copy; OpenStreetMap contributors" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />

      <MapFocus point={point} />

      {layers.weather && locations.map((item) => {

        const selected = selectedLocation && selectedLocation.code === item.code;

        return <CircleMarker key={item.code} center={[item.latitude, item.longitude]} radius={selected ? 3.5 : 2.5} pathOptions={{ color: selected ? "#082f49" : "#557988", fillColor: selected ? "#22d3ee" : color(item), fillOpacity: selected ? 0.95 : 0.55, weight: selected ? 1 : 0.6 }} eventHandlers={{ click: () => onWeather(item) }}><Popup><strong>{item.name}</strong></Popup></CircleMarker>;

      })}

      {layers.stations && stations.filter((s) => s.latitude != null && s.longitude != null && Number.isFinite(Number(s.latitude)) && Number.isFinite(Number(s.longitude))).map((s) => <CircleMarker key={s.station_id} center={[Number(s.latitude), Number(s.longitude)]} radius={selectedStation && selectedStation.station_id === s.station_id ? 9 : 7} pathOptions={{ color: "#064e3b", fillColor: "#34d399", fillOpacity: 0.95, weight: 2 }} eventHandlers={{ click: () => onStation(s) }}><Popup><strong>{s.station_name || "Station " + s.station_id}</strong><br />Hydrology station<br />Latest: {value(s.latest_value)} m</Popup></CircleMarker>)}

      {layers.reservoirs && RESERVOIRS.map((r) => <CircleMarker key={r.id} center={[r.latitude, r.longitude]} radius={selectedReservoir && selectedReservoir.id === r.id ? 10 : 8} pathOptions={{ color: "#fef3c7", fillColor: "#f59e0b", fillOpacity: 0.95, weight: 2 }} eventHandlers={{ click: () => onReservoir(r) }}><Popup><strong>{r.name}</strong><br />Configured reservoir marker<br />Select for latest PCTT snapshot.</Popup></CircleMarker>)}

    </MapContainer>

    <div className="map-controls"><div className="map-control-heading">Map layers</div>{[["weather", "Weather grid"], ["stations", "Hydrology stations"], ["reservoirs", "Reservoirs"]].map(([key, label]) => <label className="layer-toggle" key={key}><input type="checkbox" checked={layers[key]} onChange={(e) => setLayers((old) => ({ ...old, [key]: e.target.checked }))} /><span>{label}</span></label>)}

      {layers.weather && <div className="map-metric-toggle"><button className={metric === "temperature" ? "is-active" : ""} onClick={() => setMetric("temperature")}>Temp</button><button className={metric === "rainfall" ? "is-active" : ""} onClick={() => setMetric("rainfall")}>Rain</button></div>}

    </div>

    <div className="map-legend"><span><i className="legend-weather" />Weather location</span><span><i className="legend-station" />Station</span><span><i className="legend-reservoir" />Reservoir</span></div>

  </div>;

}

function MetricCard({ label, value: v, unit, icon }) {

  const missing = v === null || v === undefined || v === "" || !Number.isFinite(Number(v));

  return <article className="metric-card"><div className="metric-card-top"><span className="metric-icon">{icon}</span><span className="metric-label">{label}</span></div><strong className="metric-value">{missing ? "Unavailable" : <>{value(v)}<small> {unit}</small></>}</strong></article>;

}

function ForecastChart({ title, current, predicted, unit, timestamp, color }) {

  const asNumber = (v) => v === null || v === undefined || v === "" ? NaN : Number(v);

  const data = [["Model input", asNumber(current)], ["Next-hour forecast", asNumber(predicted)]].filter((p) => Number.isFinite(p[1])).map((p) => ({ time: p[0], amount: p[1] }));

  if (!data.length) return <div className="chart-empty">Forecast values are unavailable for this location.</div>;

  return <article className="panel-card chart-card"><div className="panel-card-heading"><div><span className="eyebrow">MODEL INPUT + FORECAST</span><h3>{title}</h3></div><span className="unit-pill">{unit}</span></div><p className="chart-caption">The model input at the returned timestamp and its next-hour estimate.</p><div className="chart-area"><ResponsiveContainer width="100%" height="100%"><LineChart data={data} margin={{ top: 12, right: 16, left: -18, bottom: 4 }}><CartesianGrid stroke="#e8eef5" strokeDasharray="3 3" vertical={false} /><XAxis dataKey="time" tick={{ fill: "#77869a", fontSize: 11 }} axisLine={false} tickLine={false} /><YAxis tick={{ fill: "#77869a", fontSize: 11 }} axisLine={false} tickLine={false} domain={["dataMin - 1", "dataMax + 1"]} /><Tooltip formatter={(v) => [value(v) + " " + unit, "Value"]} contentStyle={{ borderRadius: 10, borderColor: "#dbe4ee" }} /><Line type="monotone" dataKey="amount" stroke={color} strokeWidth={3} dot={{ r: 5, fill: color, stroke: "#fff", strokeWidth: 2 }} /></LineChart></ResponsiveContainer></div><div className="chart-footer"><span>Model input timestamp: {stamp(timestamp)}</span><span>Estimate horizon: next hour</span></div></article>;

}

function StationDetails({ station, history, loading, error, stats, chartData, onForecast, forecast, forecastLoading, forecastError }) {

  return <div className="detail-stack"><div className="detail-heading"><span className="eyebrow">HYDROLOGY STATION</span><h2>{station.station_name || "Station " + station.station_id}</h2><p>{station.station_type || station.source || "Station registry record"} · ID {station.station_id}</p></div>

    <div className="station-detail-stats"><div><span>Latest water level</span><strong>{value(stats ? stats.latest : station.latest_value)}<small> m</small></strong></div><div><span>Observations in view</span><strong>{history.length}</strong></div><div><span>Range in view</span><strong>{stats ? value(stats.min) + " – " + value(stats.max) : "—"}<small>{stats ? " m" : ""}</small></strong></div></div>

    {loading && <div className="state-box">Loading recent station observations…</div>}{error && <div className="state-box state-error">{error}</div>}{!loading && !error && history.length === 0 && <div className="state-box">No history observations were returned for this station.</div>}

    {!loading && !error && history.length > 0 && <article className="panel-card nested-chart"><div className="panel-card-heading"><div><span className="eyebrow">OBSERVED HISTORY</span><h3>Recent water-level trend</h3></div><span className="unit-pill">m</span></div><div className="chart-area"><ResponsiveContainer width="100%" height="100%"><LineChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}><CartesianGrid stroke="#e8eef5" strokeDasharray="3 3" /><XAxis dataKey="time" tick={{ fill: "#77869a", fontSize: 10 }} axisLine={false} tickLine={false} minTickGap={20} /><YAxis tick={{ fill: "#77869a", fontSize: 10 }} axisLine={false} tickLine={false} domain={["auto", "auto"]} /><Tooltip /><Line type="monotone" dataKey="value" name="Water level" stroke="#059669" strokeWidth={2.5} dot={false} connectNulls={false} /></LineChart></ResponsiveContainer></div><div className="chart-footer"><span>From {stamp(history[0].timestamp)}</span><span>To {stamp(history[history.length - 1].timestamp)}</span></div></article>}

    {stats && stats.change !== null && <div className="change-note">Change from previous returned observation: <strong>{stats.change > 0 ? "+" : ""}{value(stats.change)} m</strong></div>}

    <div className="station-forecast-callout"><div><strong>24-hour station forecast</strong><small>Existing hydrology model endpoint</small></div><button className="secondary-button" onClick={onForecast} disabled={forecastLoading}>{forecastLoading ? "Loading…" : forecast ? "Refresh" : "Load forecast"}</button></div>

    {forecastError && <div className="state-box state-error">{forecastError}</div>}{forecast && <div className="forecast-mini-summary"><span>Model <strong>{forecast.model}</strong></span><span>80/20 holdout RMSE (1-step) <strong>{value(forecast.metrics && forecast.metrics.rmse, 3)}</strong></span><span>Forecast points <strong>{forecast.forecast ? forecast.forecast.length : 0}</strong></span></div>}

  </div>;

}

function SpatialContext({ profile, loading, error, location }) {

  const mrc = profile && profile.nearest_mrc;

  const reference = profile && profile.nearest_reference_station;

  const distance = mrc && mrc.distance_km != null ? Number(mrc.distance_km) : null;

  return <section className="spatial-context panel-card"><div className="panel-card-heading"><div><span className="eyebrow">LOCATION CONTEXT</span><h3>Spatial &amp; hydrology context</h3></div></div><div className="context-location"><strong>Weather model location</strong><span>{location.name} · {value(location.latitude, 4)}, {value(location.longitude, 4)}</span><small>This is a weather-grid/model point, not a physical monitoring station.</small></div>{loading && <p className="context-note">Loading nearby hydrology context…</p>}{error && <div className="state-box state-error">Spatial context unavailable: {error}</div>}{mrc && <div className="context-grid"><div className="context-location context-station"><strong>Nearest MRC station</strong><span>{mrc.station_name || "Unnamed station"} · {mrc.station_id || "ID unavailable"}</span><small>{distance !== null && Number.isFinite(distance) ? value(distance, 2) + " km away" : "Distance unavailable"} · {mrc.river || "River unavailable"}</small></div><div className="context-stat"><span>Water level</span><strong>{mrc.water_level == null ? "Unavailable" : value(mrc.water_level) + " m"}</strong></div><div className="context-stat"><span>Rainfall</span><strong>{mrc.rainfall == null ? "Unavailable" : value(mrc.rainfall) + " mm"}</strong></div><div className="context-stat"><span>Latest measurement</span><strong>{stamp(mrc.latest_measurement)}</strong></div><div className="context-stat"><span>Historical discharge</span><strong>{mrc.discharge_available ? "Available" : "Unavailable"}</strong></div></div>}{reference && <div className="context-location context-reference"><strong>Hydrological reference metadata</strong><span>{reference.station_name || "Unnamed station"} · {reference.station_id || "ID unavailable"}</span><small>{reference.relevance_category || "Relevance unavailable"} · {reference.source || "Source unavailable"}{reference.source_year ? " (" + reference.source_year + ")" : ""}</small><em>Reference metadata; not a live observation.</em></div>}</section>;

}



function App() {

  const [section, setSection] = useState("overview");

  const [metric, setMetric] = useState("temperature");

  const [layers, setLayers] = useState({ weather: true, stations: false, reservoirs: false });

  const [mobileOpen, setMobileOpen] = useState(false);

  const [locations, setLocations] = useState([]), [locationsLoading, setLocationsLoading] = useState(true), [locationsError, setLocationsError] = useState(null);

  const weatherRequest = useRef(0), historyRequest = useRef(0);
  const candidateRequest = useRef(0);

  const [selectedLocation, setSelectedLocation] = useState(null);

  const [temperature, setTemperature] = useState(null), [rainfall, setRainfall] = useState(null), [weatherLoading, setWeatherLoading] = useState(false), [weatherError, setWeatherError] = useState(null);
const [temperatureCandidate, setTemperatureCandidate] = useState(null);
const [temperatureCandidateLoading, setTemperatureCandidateLoading] = useState(false);
const [temperatureCandidateError, setTemperatureCandidateError] = useState(null);
  const [spatial, setSpatial] = useState(null), [spatialLoading, setSpatialLoading] = useState(false), [spatialError, setSpatialError] = useState(null);

  const [stations, setStations] = useState([]), [stationsLoaded, setStationsLoaded] = useState(false), [stationsLoading, setStationsLoading] = useState(false), [stationsError, setStationsError] = useState(null);

  const [stationSearch, setStationSearch] = useState("");

  const [selectedStation, setSelectedStation] = useState(null), [history, setHistory] = useState([]), [historyLoading, setHistoryLoading] = useState(false), [historyError, setHistoryError] = useState(null);

  const [stationForecast, setStationForecast] = useState(null), [stationForecastLoading, setStationForecastLoading] = useState(false), [stationForecastError, setStationForecastError] = useState(null);

  const [selectedReservoir, setSelectedReservoir] = useState(null), [reservoir, setReservoir] = useState(null), [reservoirLoading, setReservoirLoading] = useState(false), [reservoirError, setReservoirError] = useState(null);



  const loadLocations = useCallback(async () => {

    setLocationsLoading(true); setLocationsError(null);

    try {

      const data = await getJson(API + "/weather/locations?limit=500");

      if (!Array.isArray(data)) throw new Error("Weather locations response was not a JSON array.");

      const normalized = data.map((item) => { const code = String(item.location_code || ""); return { code, name: code.startsWith("GRID_") ? "Weather grid " + code.slice(5) : code, latitude: item.latitude == null ? NaN : Number(item.latitude), longitude: item.longitude == null ? NaN : Number(item.longitude), timestamp: item.timestamp, currentTemperature: item.temperature_c, currentRainfall: item.rainfall_mm, humidity: item.relative_humidity_2m ?? item.humidity, dewPoint: item.dew_point_2m ?? item.dew_point, pressure: item.pressure_msl, surfacePressure: item.surface_pressure_hpa, windSpeed: item.wind_speed_10m ?? item.wind_speed, windDirection: item.wind_direction_10m ?? item.wind_direction, windGusts: item.wind_gusts_10m ?? item.wind_gusts, cloudCover: item.cloud_cover }; }).filter((item) => item.code && Number.isFinite(item.latitude) && Number.isFinite(item.longitude));

      setLocations(normalized);

      if (data.length && !normalized.length) throw new Error("Weather locations response contained no usable coordinates.");

    } catch (e) { setLocations([]); setLocationsError(e.message || "Unable to load weather locations."); }

    finally { setLocationsLoading(false); }

  }, []);

  const stationRequest = useRef(null);

  const loadStations = useCallback(() => {

    if (stationRequest.current) return stationRequest.current;

    const request = (async () => {

      setStationsLoading(true); setStationsError(null);

      try { const data = await getJson(API + "/stations"); if (!Array.isArray(data)) throw new Error("Stations response was not a JSON array."); setStations(data); setStationsLoaded(true); }

      catch (e) { setStationsError(e.message || "Unable to load hydrology stations."); setStationsLoaded(false); }

      finally { setStationsLoading(false); stationRequest.current = null; }

    })();

    stationRequest.current = request;

    return request;

  }, []);

  const loadTemperatureCandidate = useCallback(async (locationCode) => {
    const requestId = ++candidateRequest.current;

    setTemperatureCandidate(null);
    setTemperatureCandidateError(null);
    setTemperatureCandidateLoading(true);

    try {
      const data = await getJson(
        API + "/weather/temperature-candidate?location_code=" +
          encodeURIComponent(locationCode)
      );

      if (requestId !== candidateRequest.current) return;

      if (
        data.status !== "experimental_candidate" ||
        !Array.isArray(data.predictions)
      ) {
        throw new Error("Unexpected candidate API response.");
      }

      const prediction = data.predictions.find(
        (item) => String(item.location_code) === String(locationCode)
      );

      if (!prediction) {
        throw new Error("No candidate prediction returned for this location.");
      }

      setTemperatureCandidate(data);
    } catch (e) {
      if (requestId === candidateRequest.current) {
        setTemperatureCandidateError(
          e.message || "Candidate temperature prediction unavailable."
        );
      }
    } finally {
      if (requestId === candidateRequest.current) {
        setTemperatureCandidateLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      loadLocations();
      loadStations();
    }, 0);

    return () => window.clearTimeout(timer);
  }, [loadLocations, loadStations]);



  const chooseWeather = useCallback(async (item) => {

    const requestId = ++weatherRequest.current;
    loadTemperatureCandidate(item.code);

    ++historyRequest.current;

    setSelectedLocation(item); setSelectedStation(null); setSelectedReservoir(null); setWeatherLoading(true); setWeatherError(null); setSpatial(null); setSpatialError(null); setSpatialLoading(true); setTemperature(null); setRainfall(null);

    let profile = null;

    try {

      profile = await getJson(API + "/spatial/location/" + encodeURIComponent(item.code));

      if (requestId === weatherRequest.current) setSpatial(profile);

    } catch (e) {

      if (requestId === weatherRequest.current) setSpatialError(e.message || "Spatial context unavailable.");

    } finally {

      if (requestId === weatherRequest.current) setSpatialLoading(false);

    }

    let nextTemperature = profile && profile.weather_forecast && profile.weather_forecast.temperature;

    let nextRainfall = profile && profile.weather_forecast && profile.weather_forecast.rainfall;

    const failures = [];

    if (!nextTemperature) {

      try { nextTemperature = await getJson(API + "/weather/temperature/" + encodeURIComponent(item.code)); }

      catch (e) { failures.push("Temperature: " + (e.message || "unavailable")); }

    }

    if (!nextRainfall) {

      try { nextRainfall = await getJson(API + "/weather/rainfall/" + encodeURIComponent(item.code)); }

      catch (e) { failures.push("Rainfall: " + (e.message || "unavailable")); }

    }

    if (requestId === weatherRequest.current) {

      setTemperature(nextTemperature || null);

      setRainfall(nextRainfall || null);

      if (failures.length) setWeatherError(failures.join(" · "));

      setWeatherLoading(false);

    }

  }, [loadTemperatureCandidate]);



  const chooseStation = useCallback(async (item) => {

    ++weatherRequest.current;

    const requestId = ++historyRequest.current;

    setSelectedStation(item); setSelectedLocation(null); setSelectedReservoir(null); setHistory([]); setHistoryError(null); setStationForecast(null); setStationForecastError(null); setHistoryLoading(true);

    try { const data = await getJson(API + "/stations/" + encodeURIComponent(item.station_id) + "/history?limit=24"); if (!Array.isArray(data)) throw new Error("Station history response was not a JSON array."); if (requestId === historyRequest.current) setHistory(data); }

    catch (e) { if (requestId === historyRequest.current) setHistoryError(e.message || "Unable to load station history."); }

    finally { if (requestId === historyRequest.current) setHistoryLoading(false); }

  }, []);

  const loadStationForecast = useCallback(async () => {

    if (!selectedStation || !/^\d+$/.test(String(selectedStation.station_id))) { setStationForecastError("The existing forecast endpoint requires a numeric station ID."); return; }

    setStationForecastLoading(true); setStationForecastError(null);

    try { setStationForecast(await getJson(API + "/forecasts/" + encodeURIComponent(selectedStation.station_id))); }

    catch (e) { setStationForecastError(e.message || "Station forecast unavailable."); }

    finally { setStationForecastLoading(false); }

  }, [selectedStation]);

  const chooseReservoir = useCallback(async (item) => {

    ++weatherRequest.current;

    ++historyRequest.current;

    setSelectedReservoir(item); setSelectedLocation(null); setSelectedStation(null); setReservoir(null); setReservoirLoading(true); setReservoirError(null);

    try { setReservoir(await getJson(API + "/pctt/latest")); }

    catch (e) { setReservoirError(e.message || "Reservoir snapshot unavailable."); }

    finally { setReservoirLoading(false); }

  }, []);

  function navigate(id) {

    setSection(id); setMobileOpen(false);

    if (id === "reservoirs" && !reservoir && !reservoirLoading) { setReservoirLoading(true); setReservoirError(null); getJson(API + "/pctt/latest").then(setReservoir).catch((e) => setReservoirError(e.message)).finally(() => setReservoirLoading(false)); }

  }



  const stats = useMemo(() => { const vals = history.map((x) => x.value === null || x.value === undefined || x.value === "" ? NaN : Number(x.value)).filter(Number.isFinite); return vals.length ? { latest: vals[vals.length - 1], min: Math.min(...vals), max: Math.max(...vals), change: vals.length > 1 ? vals[vals.length - 1] - vals[vals.length - 2] : null } : null; }, [history]);

  const historyChart = history.map((x) => ({ time: new Date(x.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }), value: x.value }));

  const reservoirValue = (id, field) => reservoir && RES_FIELDS[id] ? reservoir[RES_FIELDS[id][field]] : null;

  const sectionTitle = (NAV.find((n) => n.id === section) || NAV[0]).label;

  const renderMap = (compact = false) => <MapView locations={locations} stations={stations} selectedLocation={selectedLocation} selectedStation={selectedStation} selectedReservoir={selectedReservoir} onWeather={chooseWeather} onStation={chooseStation} onReservoir={chooseReservoir} metric={metric} setMetric={setMetric} layers={layers} setLayers={setLayers} compact={compact} />;

  const renderMetrics = (item) => <div className="weather-metric-grid">{METRICS.map((m) => <MetricCard key={m[0]} label={m[1]} value={item && item[m[0]]} unit={m[2]} icon={m[3]} />)}</div>;

  const renderStationDetails = () => selectedStation ? <StationDetails station={selectedStation} history={history} loading={historyLoading} error={historyError} stats={stats} chartData={historyChart} onForecast={loadStationForecast} forecast={stationForecast} forecastLoading={stationForecastLoading} forecastError={stationForecastError} /> : <div className="empty-panel"><span>≋</span><strong>Select a hydrology station</strong><p>Recent station history is loaded from the existing station-history endpoint.</p></div>;

  const renderReservoirDetails = () => <div className="detail-stack"><div className="detail-heading"><span className="eyebrow">PCTT RESERVOIR SNAPSHOT</span><h2>{selectedReservoir.name}</h2><p>Existing configured reservoir marker</p></div>{reservoirLoading && <div className="state-box">Loading latest PCTT observation…</div>}{reservoirError && <div className="state-box state-error">{reservoirError}</div>}{reservoir && <><p className="detail-timestamp">Observed {stamp(reservoir.timestamp)}</p><div className="reservoir-values">{[["Water level", "level", "m"], ["Inflow", "inflow", "m³/s"], ["Powerhouse discharge", "power", "m³/s"], ["Spillway discharge", "spill", "m³/s"]].map(([label, key, unit]) => <div key={key}><span>{label}</span><strong>{value(reservoirValue(selectedReservoir.id, key))}<small>{reservoirValue(selectedReservoir.id, key) == null ? "" : " " + unit}</small></strong></div>)}</div></>}<div className="notice-strip compact-notice"><span>i</span><p>Only values returned by the latest PCTT snapshot are shown. Missing values remain unavailable.</p></div></div>;

  const weatherCharts = <div className="chart-grid">{temperature && <ForecastChart title="Temperature" current={temperature.current_temperature_c} predicted={temperature.predicted_next_hour_temperature_c} unit="°C" timestamp={temperature.timestamp} color="#0e7490" />}{rainfall && <ForecastChart title="Rainfall" current={rainfall.current_rainfall_mm} predicted={rainfall.predicted_next_hour_rainfall_mm} unit="mm" timestamp={rainfall.timestamp} color="#2563eb" />}</div>;



  return <div className="app-shell">

    <aside className={mobileOpen ? "sidebar sidebar-open" : "sidebar"}>

      <div className="brand-lockup"><div className="brand-mark"><span>W</span><i /></div><div><strong>Weather AI</strong><small>FORECASTING</small></div><button className="mobile-close" aria-label="Close navigation" onClick={() => setMobileOpen(false)}>×</button></div>

      <div className="sidebar-caption">MONITORING WORKSPACE</div>

      {["Workspace", "Monitoring"].map((group) => <nav className="nav-group" key={group} aria-label={group}><span className="nav-group-title">{group}</span>{NAV.filter((item) => item.group === group).map((item) => <button key={item.id} className={section === item.id ? "nav-item nav-item-active" : "nav-item"} onClick={() => navigate(item.id)} aria-current={section === item.id ? "page" : undefined}><span className="nav-icon" aria-hidden="true">{item.icon}</span><span>{item.label}</span>{item.id === "stations" && stationsLoaded && <small className="nav-count">{stations.length}</small>}</button>)}</nav>)}

      <div className="sidebar-bottom"><span className={locationsError ? "connection-dot connection-error" : "connection-dot"} /><div><strong>{locationsError ? "Weather API unavailable" : locationsLoading ? "Connecting to data" : "Data connection active"}</strong><small>FastAPI · PostgreSQL</small></div></div><div className="sidebar-footnote">Weather observations and hydrology context in one workspace.</div>

    </aside>

    {mobileOpen && <button className="nav-scrim" aria-label="Close navigation" onClick={() => setMobileOpen(false)} />}

    <div className="main-shell"><header className="topbar"><button className="menu-button" aria-label="Open navigation" onClick={() => setMobileOpen(true)}>☰</button><div className="breadcrumb"><span>Weather AI Forecasting</span><b>/</b><strong>{sectionTitle}</strong></div><div className="topbar-status"><span className={locationsError ? "status-led status-led-error" : "status-led"} />{locationsError ? "Connection issue" : locationsLoading ? "Loading data" : "Data services available"}</div></header>

      <main className="page-content"><div className="page-heading"><div><span className="eyebrow">VIETNAM · WEATHER &amp; WATER</span><h1>{sectionTitle}</h1><p>{section === "overview" ? "A clear view of current weather observations and hydrological monitoring." : section === "map" ? "Explore weather-grid locations, hydrology stations and reservoir markers." : section === "analytics" ? "Atmospheric conditions and next-hour model outputs for a selected location." : section === "stations" ? "Station registry and recent observed water levels." : section === "reservoirs" ? "Latest available PCTT reservoir snapshot." : "Forecast horizons supported by the existing model services."}</p></div></div>
<div className="heading-meta">
  <span className="freshness-dot" />
  {locations[0]
    ? "Latest weather " + stamp(locations[0].timestamp)
    : locationsLoading
      ? "Checking weather feed…"
      : "Weather timestamp unavailable"}

  {(() => {
    const freshness = getWeatherFreshness(
      locations[0] && locations[0].timestamp
    );

    return (
      <span
        style={{
          marginLeft: 10,
          color: freshness.stale ? "#b45309" : "#047857",
          fontWeight: 600,
        }}
      >
        · {freshness.label}
      </span>
    );
  })()}
</div>
      {section === "overview" && <>

        <section className="summary-grid"><article className="summary-card"><span className="summary-icon icon-blue">◉</span><div><span>Weather locations</span><strong>{locationsLoading ? "…" : locationsError ? "Unavailable" : locations.length}</strong><small>{locationsError ? "API request failed" : "Latest observation points"}</small></div><i className="summary-accent accent-blue" /></article><article className="summary-card"><span className="summary-icon icon-green">≋</span><div><span>Hydrology stations</span><strong>{stationsLoading ? "…" : stationsError ? "Unavailable" : stationsLoaded ? stations.length : "Not loaded"}</strong><small>{stationsLoaded ? "Station registry" : stationsError ? "API request failed" : "Available in station view"}</small></div><i className="summary-accent accent-green" /></article><article className="summary-card"><span className="summary-icon icon-amber">▤</span><div><span>Reservoir markers</span><strong>{RESERVOIRS.length}</strong><small>Configured PCTT map markers</small></div><i className="summary-accent accent-amber" /></article><article className="summary-card"><span className="summary-icon icon-cyan">↗</span><div><span>Weather forecast</span><strong>1 hour</strong><small>Temperature &amp; rainfall models</small></div><i className="summary-accent accent-cyan" /></article></section>

        <section className="overview-grid"><article className="panel-card overview-map-card"><div className="panel-card-heading"><div><span className="eyebrow">GEOGRAPHIC OVERVIEW</span><h2>Vietnam monitoring map</h2></div><button className="text-button" onClick={() => navigate("map")}>Open full map <span>→</span></button></div>{locationsLoading ? <div className="map-placeholder">Loading weather locations…</div> : locationsError ? <div className="state-box state-error"><strong>Weather map unavailable</strong><p>{locationsError}</p><button className="secondary-button" onClick={loadLocations}>Try again</button></div> : locations.length === 0 ? <div className="map-placeholder">No weather locations were returned by the API.</div> : renderMap(true)}</article>

          <article className="panel-card overview-detail-card"><div className="panel-card-heading"><div><span className="eyebrow">INVESTIGATE</span><h2>{selectedLocation ? selectedLocation.name : "Select a location"}</h2></div><span className="live-tag"><i /> OBSERVATIONS</span></div>{selectedLocation ? <><div className="selected-summary"><span>Weather location</span><strong>{selectedLocation.code}</strong><small>{stamp(selectedLocation.timestamp)}</small></div><div className="compact-metrics"><MetricCard label="Temperature" value={selectedLocation.currentTemperature} unit="°C" icon="温" /><MetricCard label="Rainfall" value={selectedLocation.currentRainfall} unit="mm" icon="雨" /><MetricCard label="Humidity" value={selectedLocation.humidity} unit="%" icon="%" /></div>{weatherError && <div className="inline-error">Forecast unavailable: {weatherError}</div>}<button className="primary-button full-button" onClick={() => navigate("analytics")}>View weather analytics <span>→</span></button></> : <><p className="muted-copy">Choose a weather-grid point on the map to inspect its latest observation and model outputs.</p><div className="data-note"><strong>Data freshness</strong><span>{locations[0] ? stamp(locations[0].timestamp) : "Not available from current response"}</span></div><button className="secondary-button full-button" onClick={() => navigate("map")}>Explore map</button></>}</article></section>

        <div className="notice-strip"><span>i</span><p><strong>Data context:</strong> weather cards show the latest available observation; forecast outputs are separate model estimates. Reservoir count refers to configured map markers, not a database inventory.</p></div>

      </>}

      {section === "map" && <section className="map-workspace"><div className="map-workspace-main panel-card"><div className="panel-card-heading"><div><span className="eyebrow">INTERACTIVE WEBGIS</span><h2>Weather &amp; hydrology map</h2></div><div className="mode-switch"><button className={layers.weather ? "is-active" : ""} onClick={() => setLayers({ weather: true, stations: false, reservoirs: false })}>Weather</button><button className={layers.stations || layers.reservoirs ? "is-active" : ""} onClick={() => setLayers({ weather: false, stations: true, reservoirs: true })}>Hydrology</button></div></div>

          {layers.weather && locationsLoading && <div className="state-box">Loading weather locations…</div>}

          {layers.weather && locationsError && <div className="state-box state-error"><strong>Weather layer unavailable</strong><p>{locationsError}</p><button className="secondary-button" onClick={loadLocations}>Retry weather locations</button></div>}

          {layers.weather && !locationsLoading && !locationsError && locations.length === 0 && <div className="state-box">Weather locations API succeeded, but returned an empty list.</div>}

          {layers.stations && stationsLoading && <div className="state-box">Loading hydrology stations…</div>}

          {layers.stations && stationsError && <div className="state-box state-error"><strong>Hydrology stations unavailable</strong><p>{stationsError}</p><button className="secondary-button" onClick={() => { setStationsLoaded(false); loadStations(); }}>Retry hydrology stations</button></div>}

          {layers.stations && stationsLoaded && stations.length === 0 && <div className="state-box">Hydrology stations API succeeded, but returned no stations.</div>}

          {renderMap()}

          <div className="map-source-note">Weather locations are model/grid points; green markers are physical stations with coordinates; amber markers are configured reservoir points. © OpenStreetMap contributors.</div></div>

        <aside className="map-side-panel panel-card">
            <div className="panel-card-heading"><div><span className="eyebrow">HYDROLOGY NETWORK</span><h2>All stations</h2></div><span className="count-pill">{stationsLoaded ? stations.length + " stations" : stationsLoading ? "Loading" : "—"}</span></div>
            <input className="station-search" type="search" value={stationSearch} onChange={(e) => setStationSearch(e.target.value)} placeholder="Search station ID or name…" aria-label="Search hydrology stations" />
            {stationsError && <div className="state-box state-error">{stationsError}<button className="secondary-button" onClick={() => { setStationsLoaded(false); loadStations(); }}>Retry</button></div>}
            {!stationsLoaded && !stationsLoading && !stationsError && <button className="secondary-button" onClick={loadStations}>Load hydrology stations</button>}
            {stationsLoading && <div className="state-box">Loading hydrology stations…</div>}
            {stationsLoaded && <div className="map-station-list">{stations.filter((s) => (String(s.station_id || "") + " " + String(s.station_name || "")).toLowerCase().includes(stationSearch.trim().toLowerCase())).map((s) => <button key={s.station_id} className={selectedStation && String(selectedStation.station_id) === String(s.station_id) ? "station-row station-row-active" : "station-row"} onClick={() => chooseStation(s)}><span className="station-dot" /><span className="station-row-main"><strong>{s.station_name || "Station " + s.station_id}</strong><small>ID {s.station_id}{s.latitude != null && s.longitude != null ? " · mapped" : " · coordinates unavailable"}</small></span><span className="station-row-value">{value(s.latest_value)}<small>latest m</small></span></button>)}
              {stations.filter((s) => (String(s.station_id || "") + " " + String(s.station_name || "")).toLowerCase().includes(stationSearch.trim().toLowerCase())).length === 0 && <div className="state-box">No stations match your search.</div>}
            </div>}
            <div className="map-selection-details">
            <div className="panel-card-heading"><div><span className="eyebrow">SELECTION DETAILS</span><h2>{selectedLocation ? selectedLocation.name : selectedStation ? (selectedStation.station_name || "Station " + selectedStation.station_id) : selectedReservoir ? selectedReservoir.name : "No selection"}</h2></div></div>{selectedLocation ? <><span className="detail-type">WEATHER LOCATION · {selectedLocation.code}</span><p className="detail-timestamp">{stamp(selectedLocation.timestamp)}</p>{renderMetrics(selectedLocation)}<SpatialContext profile={spatial} loading={spatialLoading} error={spatialError} location={selectedLocation} />{weatherLoading && <div className="state-box">Loading next-hour models…</div>}{weatherError && <div className="state-box state-error">{weatherError}</div>}<button className="text-button" onClick={() => navigate("analytics")}>Open analytics →</button></> : selectedStation ? renderStationDetails() : selectedReservoir ? renderReservoirDetails() : <div className="empty-panel"><span>⌖</span><strong>Select a map marker</strong><p>Choose a station from the list above, or click a mapped location.</p></div>}</div></aside></section>}

      {section === "analytics" && <><section className="selector-panel panel-card"><div><span className="eyebrow">LOCATION</span><h2>Choose a weather location</h2></div><select value={selectedLocation ? selectedLocation.code : ""} onChange={(e) => { const item = locations.find((x) => x.code === e.target.value); if (item) chooseWeather(item); }} disabled={locationsLoading || !locations.length}><option value="">Select location</option>{locations.map((x) => <option key={x.code} value={x.code}>{x.name} · {x.code}</option>)}</select></section>{locationsLoading && <div className="state-box">Loading weather locations…</div>}{locationsError && <div className="state-box state-error">{locationsError}</div>}{!locationsLoading && !locationsError && !locations.length && <div className="state-box">No weather locations are available from the API.</div>}{selectedLocation ? <><div className="section-title-row"><div><h2>{selectedLocation.name}</h2><p>Latest observation · {stamp(selectedLocation.timestamp)}</p></div>{weatherLoading && <span className="loading-chip">Loading models…</span>}</div>{renderMetrics(selectedLocation)}<SpatialContext profile={spatial} loading={spatialLoading} error={spatialError} location={selectedLocation} />{weatherError && <div className="state-box state-error">Forecast services unavailable: {weatherError}</div>}{weatherCharts}
<RecentWeatherPanel
  api={API}
  locationCode={selectedLocation.code}
  locationName={selectedLocation.name}
/>
        <section className="panel-card candidate-panel" style={{ marginTop: 20, padding: 22, border: "1px solid #dbe4ee", borderRadius: 16 }}>
          <div className="panel-card-heading">
            <div>
              <span className="eyebrow">EXPERIMENTAL MODEL · NOT FOR PRODUCTION</span>
              <h3>Candidate temperature comparison</h3>
            </div>
            <span className="unit-pill">°C</span>
          </div>
          <p className="chart-caption">This candidate is shown separately from the existing production forecast. It has not been independently verified as an operational forecast.</p>
          {temperatureCandidateLoading && <div className="state-box">Loading experimental candidate…</div>}
          {temperatureCandidateError && <div className="state-box state-error">{temperatureCandidateError}</div>}
          {!temperatureCandidateLoading && !temperatureCandidateError && temperatureCandidate && (() => {
            const candidate = temperatureCandidate.predictions.find(
              (item) => String(item.location_code) === String(selectedLocation.code)
            );
            if (!candidate) return <div className="state-box">No candidate result is available for this location.</div>;
            return <>
              <div className="forecast-metrics-row" style={{ marginTop: 16 }}>
                <span>Current temperature <strong>{value(candidate.current_temperature_c)} °C</strong></span>
                <span>MLP prediction <strong>{value(candidate.mlp_prediction_c)} °C</strong></span>
                <span>Hybrid candidate <strong>{value(candidate.hybrid_prediction_c)} °C</strong></span>
                <span>Selection rule <strong>{candidate.selection_rule || "Unavailable"}</strong></span>
              </div>
              <div className="chart-footer" style={{ marginTop: 14 }}>
                <span>Source timestamp: {stamp(candidate.source_timestamp || temperatureCandidate.source_timestamp)}</span>
                <span>Calibration alpha: {value(candidate.calibration_alpha, 2)}</span>
              </div>
              <div className="notice-strip compact-notice" style={{ marginTop: 16 }}>
                <span>i</span>
                <p>
                  {temperatureCandidate.forecast_validation === "not_independently_verified"
                    ? "Forecast validation has not been independently verified."
                    : "Validation status: " + String(temperatureCandidate.forecast_validation || "Unavailable") + "."}
                  {temperatureCandidate.source_data_stale
                    ? " Source data is stale"
                      + (temperatureCandidate.source_data_age_hours != null
                        ? " (" + value(temperatureCandidate.source_data_age_hours, 1) + " hours old)."
                        : ".")
                    : " Source data is not marked stale."}
                  {" "}{temperatureCandidate.warning || ""}
                </p>
              </div>
            </>;
          })()}
        </section>
        <div className="notice-strip"><span>i</span><p>Weather history is not exposed by the current API. Charts compare the latest observation with its next-hour model output; they are not historical time series.</p></div></> : <div className="empty-panel large-empty"><span>⌁</span><strong>Select a location to view its weather</strong><p>Measurements come from the latest weather API response. Forecast charts appear when model endpoints return successfully.</p></div>}</>}

      {section === "stations" && <section className="stations-layout"><article className="panel-card station-registry"><div className="panel-card-heading"><div><span className="eyebrow">HYDROLOGY NETWORK</span><h2>Station registry</h2></div><span className="count-pill">{stationsLoading ? "Loading" : stationsError ? "Unavailable" : stationsLoaded ? stations.length + " stations" : "—"}</span></div>{stationsLoading && <div className="state-box">Loading station registry…</div>}{stationsError && <div className="state-box state-error"><p>{stationsError}</p><button className="secondary-button" onClick={() => { setStationsLoaded(false); loadStations(); }}>Retry</button></div>}{!stationsLoading && !stationsError && stationsLoaded && !stations.length && <div className="state-box">Stations API succeeded with an empty list.</div>}{stationsLoaded && stations.length > 0 && <div className="station-list">{stations.map((s) => <button key={s.station_id} className={selectedStation && selectedStation.station_id === s.station_id ? "station-row station-row-active" : "station-row"} onClick={() => chooseStation(s)}><span className="station-dot" /><span className="station-row-main"><strong>{s.station_name || "Station " + s.station_id}</strong><small>{s.station_type || s.source || "Hydrology station"} · ID {s.station_id}</small></span><span className="station-row-value">{value(s.latest_value)}<small>latest</small></span></button>)}</div>}</article><article className="panel-card station-detail">{renderStationDetails()}</article></section>}

      {section === "reservoirs" && <><div className="data-banner"><span>SNAPSHOT</span><p>Values are from the latest available PCTT observation. Map locations are the project’s existing configured markers.</p></div>{reservoirLoading && <div className="state-box">Loading latest PCTT snapshot…</div>}{reservoirError && <div className="state-box state-error">Latest reservoir data unavailable: {reservoirError}</div>}{reservoir && <div className="snapshot-time">Latest PCTT observation · {stamp(reservoir.timestamp)}</div>}<section className="reservoir-grid">{RESERVOIRS.map((r) => <article className="panel-card reservoir-card" key={r.id}><div className="reservoir-card-heading"><span className="reservoir-icon">▤</span><div><span className="eyebrow">PCTT MONITORING</span><h2>{r.name}</h2></div><button className="icon-button" aria-label={"Show " + r.name + " on map"} onClick={() => { setSelectedReservoir(r); setSection("map"); setLayers((v) => ({ ...v, reservoirs: true })); }}>↗</button></div>{!reservoir && !reservoirLoading ? <div className="muted-copy">Snapshot unavailable.</div> : <div className="reservoir-values">{[["Water level", "level", "m"], ["Inflow", "inflow", "m³/s"], ["Powerhouse discharge", "power", "m³/s"], ["Spillway discharge", "spill", "m³/s"]].map(([label, key, unit]) => <div key={key}><span>{label}</span><strong>{value(reservoirValue(r.id, key))}<small>{reservoir && reservoirValue(r.id, key) != null ? " " + unit : ""}</small></strong></div>)}</div>}<button className="text-button" onClick={() => { setSelectedReservoir(r); setSection("map"); setLayers((v) => ({ ...v, reservoirs: true })); if (!reservoir && !reservoirLoading) chooseReservoir(r); }}>View map detail →</button></article>)}</section></>}

      {section === "forecasts" && <><div className="forecast-intro"><div><span className="eyebrow">AVAILABLE MODEL SERVICES</span><h2>Forecast outputs</h2><p>Only horizons returned by the current services are displayed.</p></div><span className="horizon-pill">NEXT HOUR · WEATHER</span></div><section className="panel-card forecast-select"><div><strong>Weather forecast location</strong><small>Temperature and rainfall models</small></div><select value={selectedLocation ? selectedLocation.code : ""} onChange={(e) => { const item = locations.find((x) => x.code === e.target.value); if (item) chooseWeather(item); }}><option value="">Select a weather location</option>{locations.map((x) => <option key={x.code} value={x.code}>{x.name}</option>)}</select></section>{locationsError && <div className="state-box state-error">{locationsError}</div>}{weatherLoading && <div className="state-box">Loading forecast models…</div>}{weatherError && <div className="state-box state-error">{weatherError}</div>}{selectedLocation && <><div className="forecast-location-label">{selectedLocation.name} <span>· Observed {stamp(selectedLocation.timestamp)}</span></div>{weatherCharts}</>}

        <section className="panel-card hydro-forecast-section"><TemperatureForecastPanel api={API} /><div className="panel-card-heading"><div><span className="eyebrow">HYDROLOGY FORECAST</span><h2>Station model output</h2><p>Existing endpoint: 24-hour recursive forecast plus chronological 80/20 one-step holdout metrics.</p></div>{selectedStation && <button className="secondary-button" onClick={loadStationForecast} disabled={stationForecastLoading}>{stationForecastLoading ? "Loading…" : "Load forecast"}</button>}</div>{!selectedStation ? <div className="state-box">Select a station from Hydrology Stations first. Forecast requests require a numeric station ID.</div> : <><p className="forecast-location-label">{selectedStation.station_name || "Station " + selectedStation.station_id}</p>{stationForecastError && <div className="state-box state-error">{stationForecastError}</div>}{stationForecast && <><div className="forecast-metrics-row"><span>Model <strong>{stationForecast.model}</strong></span><span>MAE <strong>{value(stationForecast.metrics && stationForecast.metrics.mae, 3)}</strong></span><span>RMSE <strong>{value(stationForecast.metrics && stationForecast.metrics.rmse, 3)}</strong></span><span>Points <strong>{stationForecast.forecast ? stationForecast.forecast.length : 0}</strong></span></div>{stationForecast.forecast && <div className="chart-area chart-area-large"><ResponsiveContainer width="100%" height="100%"><LineChart data={stationForecast.forecast.map((x) => ({ time: stamp(x.timestamp), value: x.value }))}><CartesianGrid stroke="#e8eef5" strokeDasharray="3 3" /><XAxis dataKey="time" hide /><YAxis /><Tooltip /><Line dataKey="value" stroke="#0e7490" strokeWidth={2.5} dot={false} /></LineChart></ResponsiveContainer></div>}<p className="chart-caption">Latest observation: {stamp(stationForecast.last_observation && stationForecast.last_observation.timestamp)}. Values and timestamps are returned by the station forecast service.</p></>}</>}</section><div className="notice-strip"><span>i</span><p>No flood-warning endpoint or validated operational flood thresholds are exposed. This view does not calculate or imply flood risk.</p></div></>}

      </main><footer className="app-footer"><span>Weather AI Forecasting</span><span>Vietnam weather and hydrology monitoring</span></footer>

    </div>

  </div>;

}

export default App;
