
import { useEffect, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const FRESHNESS_LIMIT_MS = 3 * 60 * 60 * 1000;

function formatTime(value) {
  if (!value) return "Unavailable";

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) return value;

  return date.toLocaleString([], {
    timeZone: "Asia/Ho_Chi_Minh",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

async function getJson(url) {
  const response = await fetch(url);

  if (!response.ok) {
    let message = `Request failed (${response.status}).`;

    try {
      const body = await response.json();
      if (body?.detail) message = body.detail;
    } catch {
      // Keep the HTTP status message.
    }

    throw new Error(message);
  }

  return response.json();
}

export default function TemperatureForecastPanel({ api }) {
  const [locations, setLocations] = useState([]);
  const [locationId, setLocationId] = useState("");
  const [forecast, setForecast] = useState(null);
  const [loadingLocations, setLoadingLocations] = useState(true);
  const [loadingForecast, setLoadingForecast] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    let active = true;

    async function loadLocations() {
      setLoadingLocations(true);
      setError(null);

      try {
        const data = await getJson(
          `${api}/api/temperature-forecasts/locations`
        );

        if (!Array.isArray(data.locations)) {
          throw new Error("Unexpected forecast locations response.");
        }

        if (!active) return;

        setLocations(data.locations);

        if (data.locations.length) {
          setLocationId((current) =>
            data.locations.some(
              (item) => item.location_id === current
            )
              ? current
              : data.locations[0].location_id
          );
        }
      } catch (err) {
        if (active) {
          setError(err.message || "Unable to load forecast locations.");
        }
      } finally {
        if (active) setLoadingLocations(false);
      }
    }

    loadLocations();

    return () => {
      active = false;
    };
  }, [api]);

  useEffect(() => {
    if (!locationId) {
      setForecast(null);
      return;
    }

    let active = true;

    async function loadForecast() {
      setLoadingForecast(true);
      setError(null);
      setForecast(null);

      try {
        const data = await getJson(
          `${api}/api/temperature-forecasts/${encodeURIComponent(locationId)}?limit=48`
        );

        if (!active) return;

        if (!Array.isArray(data.forecasts)) {
          throw new Error("Unexpected temperature forecast response.");
        }

        setForecast(data);
      } catch (err) {
        if (active) {
          setError(err.message || "Unable to load the temperature forecast.");
        }
      } finally {
        if (active) setLoadingForecast(false);
      }
    }

    loadForecast();

    return () => {
      active = false;
    };
  }, [api, locationId]);

  const collectionDate = forecast?.collection_time_utc
    ? new Date(forecast.collection_time_utc)
    : null;

  const ageMs = collectionDate
    ? Date.now() - collectionDate.getTime()
    : null;

  const isStale =
    ageMs === null ||
    !Number.isFinite(ageMs) ||
    ageMs < 0 ||
    ageMs > FRESHNESS_LIMIT_MS;

  const chartData = (forecast?.forecasts || []).map((item) => ({
    time: formatTime(item.target_time_local),
    temperature: Number(item.temperature_c),
  })).filter((item) => Number.isFinite(item.temperature));

  return (
    <section className="panel-card" style={{ marginTop: 20, padding: 22 }}>
      <div className="panel-card-heading">
        <div>
          <span className="eyebrow">COLLECTED WEATHER FORECAST</span>
          <h2>48-hour temperature outlook</h2>
        </div>
        <span className="unit-pill">°C</span>
      </div>

      <p className="chart-caption">
        Hourly forecasts collected from Open-Meteo and stored in PostgreSQL.
        These are external forecasts, not predictions from the experimental
        temperature model.
      </p>

      <label
        htmlFor="collected-forecast-location"
        style={{ display: "block", margin: "16px 0 8px", fontWeight: 600 }}
      >
        Forecast location
      </label>

      <select
        id="collected-forecast-location"
        value={locationId}
        onChange={(event) => setLocationId(event.target.value)}
        disabled={loadingLocations || locations.length === 0}
        style={{
          width: "100%",
          maxWidth: 440,
          padding: "10px 12px",
          border: "1px solid #dbe4ee",
          borderRadius: 10,
          background: "#fff",
        }}
      >
        {locations.length === 0 && (
          <option value="">
            {loadingLocations ? "Loading locations..." : "No locations available"}
          </option>
        )}

        {locations.map((item) => (
          <option key={item.location_id} value={item.location_id}>
            {item.location_name} · {item.location_id}
          </option>
        ))}
      </select>

      {loadingLocations && (
        <div className="state-box">Loading forecast locations...</div>
      )}

      {loadingForecast && (
        <div className="state-box">Loading hourly temperatures...</div>
      )}

      {error && <div className="state-box state-error">{error}</div>}

      {forecast && !loadingForecast && !error && (
        <>
          <div className="forecast-metrics-row" style={{ marginTop: 18 }}>
            <span>
              Location
              <strong>{forecast.location_name}</strong>
            </span>
            <span>
              Forecast points
              <strong>{chartData.length}</strong>
            </span>
            <span>
              Collected
              <strong>{formatTime(forecast.collection_time_utc)}</strong>
            </span>
          </div>

          {isStale && (
            <div className="notice-strip" style={{ marginTop: 16 }}>
              <span>!</span>
              <p>
                This snapshot is older than three hours, or its freshness
                could not be verified. It may no longer represent the latest
                available forecast. Import a newer GitHub Actions artifact
                before treating it as current.
              </p>
            </div>
          )}

          {chartData.length > 0 ? (
            <div className="chart-area" style={{ height: 340, marginTop: 20 }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart
                  data={chartData}
                  margin={{ top: 12, right: 18, left: 0, bottom: 32 }}
                >
                  <CartesianGrid
                    stroke="#e8eef5"
                    strokeDasharray="3 3"
                    vertical={false}
                  />
                  <XAxis
                    dataKey="time"
                    tick={{ fill: "#77869a", fontSize: 10 }}
                    angle={-35}
                    textAnchor="end"
                    interval="preserveStartEnd"
                  />
                  <YAxis
                    unit="°C"
                    tick={{ fill: "#77869a", fontSize: 11 }}
                    domain={["auto", "auto"]}
                  />
                  <Tooltip
                    labelFormatter={(label) => `Vietnam time: ${label}`}
                    formatter={(value) => [
                      `${Number(value).toFixed(1)} °C`,
                      "Forecast temperature",
                    ]}
                  />
                  <Line
                    type="monotone"
                    dataKey="temperature"
                    name="Temperature"
                    stroke="#0e7490"
                    strokeWidth={2.5}
                    dot={false}
                    activeDot={{ r: 5 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="state-box">
              No valid temperature values were returned for this location.
            </div>
          )}
        </>
      )}
    </section>
  );
}
