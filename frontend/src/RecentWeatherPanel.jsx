
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

function formatTime(timestamp) {
  if (!timestamp) return "Unavailable";

  const date = new Date(timestamp);

  if (Number.isNaN(date.getTime())) return timestamp;

  return date.toLocaleString([], {
    timeZone: "Asia/Ho_Chi_Minh",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

async function getJson(url, signal) {
  const response = await fetch(url, { signal });

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

function Metric({ label, value, unit }) {
  const display =
    value === null || value === undefined || !Number.isFinite(Number(value))
      ? "—"
      : Number(value).toFixed(1);

  return (
    <div className="forecast-metric">
      <span>{label}</span>
      <strong>
        {display}
        {display !== "—" ? ` ${unit}` : ""}
      </strong>
    </div>
  );
}

export default function RecentWeatherPanel({ api, locationCode, locationName }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [view, setView] = useState("all");

  useEffect(() => {
    if (!locationCode) {
      setData(null);
      setError(null);
      setLoading(false);
      return undefined;
    }

    const controller = new AbortController();
    let active = true;

    async function load() {
      setLoading(true);
      setError(null);
      setData(null);

      try {
        const result = await getJson(
          `${api}/weather/recent/${encodeURIComponent(locationCode)}`,
          controller.signal
        );

        if (!Array.isArray(result.hourly)) {
          throw new Error("The recent-weather response has an unexpected format.");
        }

        if (active) setData(result);
      } catch (err) {
        if (active && err.name !== "AbortError") {
          setError(err.message || "Unable to load recent weather.");
        }
      } finally {
        if (active) setLoading(false);
      }
    }

    load();

    return () => {
      active = false;
      controller.abort();
    };
  }, [api, locationCode]);

  const chartRecords = (data?.hourly || []).map((item) => ({
    ...item,
    chartTime: formatTime(item.timestamp),
    temperature: Number(item.temperature_c),
    rainfall: Number(item.precipitation_mm),
  }));

  const displayedRecords =
    view === "past"
      ? chartRecords.slice(0, 24)
      : view === "forecast"
        ? chartRecords.slice(-24)
        : chartRecords;

  const latest = chartRecords.length
    ? chartRecords[Math.floor((chartRecords.length - 1) / 2)]
    : null;

  return (
    <section
      className="panel-card"
      style={{ marginTop: 20, padding: 22 }}
    >
      <div className="panel-card-heading">
        <div>
          <span className="eyebrow">RECENT PROVIDER WEATHER</span>
          <h2>Recent weather &amp; 24-hour outlook</h2>
        </div>
        <span className="unit-pill">OPEN-METEO</span>
      </div>

      <p className="chart-caption">
        {locationName || locationCode
          ? `Location: ${locationName || locationCode} (${locationCode}). `
          : ""}
        Hourly provider-model data fetched on demand. These values are
        separate from the project's trained ML forecasts and are not
        independently verified station observations.
      </p>

      {!locationCode && (
        <div className="state-box">
          Select a weather-grid location to load recent provider weather.
        </div>
      )}

      {loading && (
        <div className="state-box">
          Fetching recent weather from Open-Meteo…
        </div>
      )}

      {error && (
        <div className="state-box state-error">
          <strong>Recent weather unavailable</strong>
          <p>{error}</p>
          <button
            className="secondary-button"
            onClick={() => setView((current) => current)}
          >
            Check location selection
          </button>
        </div>
      )}

      {data && !loading && !error && (
        <>
          <div className="notice-strip" style={{ marginTop: 14 }}>
            <span>i</span>
            <p>
              Source: {data.source}. All timestamps use {data.timezone}.
              This response does not update PostgreSQL or any trained model.
            </p>
          </div>

          <div className="forecast-metrics-row" style={{ marginTop: 16 }}>
            <span>
              Hourly records
              <strong>{data.returned_hour_count}</strong>
            </span>
            <span>
              First timestamp
              <strong>
                {formatTime(data.hourly[0]?.timestamp)}
              </strong>
            </span>
            <span>
              Last timestamp
              <strong>
                {formatTime(data.hourly[data.hourly.length - 1]?.timestamp)}
              </strong>
            </span>
          </div>

          <div
            className="selector-panel"
            style={{
              marginTop: 18,
              padding: 0,
              border: 0,
              display: "flex",
              gap: 8,
              flexWrap: "wrap",
            }}
          >
            <button
              className={view === "all" ? "primary-button" : "secondary-button"}
              onClick={() => setView("all")}
            >
              All hours
            </button>
            <button
              className={view === "past" ? "primary-button" : "secondary-button"}
              onClick={() => setView("past")}
            >
              First 24 hours
            </button>
            <button
              className={
                view === "forecast" ? "primary-button" : "secondary-button"
              }
              onClick={() => setView("forecast")}
            >
              Last 24 hours
            </button>
          </div>

          <div className="forecast-metrics-row" style={{ marginTop: 18 }}>
            <Metric
              label="Temperature"
              value={latest?.temperature_c}
              unit="°C"
            />
            <Metric
              label="Rainfall"
              value={latest?.precipitation_mm}
              unit="mm"
            />
            <Metric
              label="Humidity"
              value={latest?.relative_humidity_2m}
              unit="%"
            />
            <Metric
              label="Wind speed"
              value={latest?.wind_speed_kmh}
              unit="km/h"
            />
          </div>

          <h3 style={{ marginTop: 24 }}>Hourly temperature</h3>
          <div className="chart-area" style={{ height: 300, marginTop: 12 }}>
            {displayedRecords.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart
                  data={displayedRecords}
                  margin={{ top: 12, right: 16, left: 4, bottom: 34 }}
                >
                  <CartesianGrid
                    stroke="#e8eef5"
                    strokeDasharray="3 3"
                    vertical={false}
                  />
                  <XAxis
                    dataKey="chartTime"
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
                    formatter={(value) => [
                      `${Number(value).toFixed(1)} °C`,
                      "Provider-model temperature",
                    ]}
                    labelFormatter={(label) => `Vietnam time: ${label}`}
                  />
                  <Line
                    type="monotone"
                    dataKey="temperature"
                    name="Temperature"
                    stroke="#0e7490"
                    strokeWidth={2.5}
                    dot={false}
                    connectNulls={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="state-box">No hourly data to chart.</div>
            )}
          </div>

          <h3 style={{ marginTop: 24 }}>Hourly details</h3>
          <div style={{ overflowX: "auto", marginTop: 10 }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={{ textAlign: "left", padding: 9 }}>Time</th>
                  <th style={{ textAlign: "right", padding: 9 }}>Temp °C</th>
                  <th style={{ textAlign: "right", padding: 9 }}>Rain mm</th>
                  <th style={{ textAlign: "right", padding: 9 }}>Humidity %</th>
                  <th style={{ textAlign: "right", padding: 9 }}>Wind km/h</th>
                </tr>
              </thead>
              <tbody>
                {displayedRecords.map((item) => (
                  <tr key={item.timestamp}>
                    <td style={{ padding: 9, whiteSpace: "nowrap" }}>
                      {formatTime(item.timestamp)}
                    </td>
                    <td style={{ textAlign: "right", padding: 9 }}>
                      {item.temperature_c ?? "—"}
                    </td>
                    <td style={{ textAlign: "right", padding: 9 }}>
                      {item.precipitation_mm ?? "—"}
                    </td>
                    <td style={{ textAlign: "right", padding: 9 }}>
                      {item.relative_humidity_2m ?? "—"}
                    </td>
                    <td style={{ textAlign: "right", padding: 9 }}>
                      {item.wind_speed_kmh ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p className="chart-caption" style={{ marginTop: 14 }}>
            The endpoint requests 24 past hours and 24 forecast hours.
            The provider determines the timestamps returned. Past values
            are not guaranteed to be measured observations.
          </p>
        </>
      )}
    </section>
  );
}
