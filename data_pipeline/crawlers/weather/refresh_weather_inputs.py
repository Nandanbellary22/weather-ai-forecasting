"""Collect multivariable Open-Meteo model inputs for ML forecasts."""
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from psycopg2.extras import execute_values

from backend.database import get_connection
from data_pipeline.crawlers.weather.collect_temperature_forecasts import load_grid

API_URL = "https://api.open-meteo.com/v1/forecast"
SCHEMA_FILE = Path(__file__).resolve().parents[3] / "database" / "weather_provider_inputs.sql"
TIMEZONE = "Asia/Ho_Chi_Minh"
LOCAL_ZONE = ZoneInfo(TIMEZONE)
BATCH_SIZE = 20
MAX_ATTEMPTS = 3
TIMEOUT_SECONDS = 45
REQUEST_DELAY_SECONDS = 1
HOURLY_FIELDS = (
    "temperature_2m,relative_humidity_2m,surface_pressure,wind_speed_10m,"
    "cloud_cover,precipitation"
)
FIELD_MAP = {
    "temperature_2m": "temperature_2m",
    "relative_humidity_2m": "relative_humidity_2m",
    "surface_pressure": "surface_pressure_hpa",
    "wind_speed_10m": "wind_speed_10m",
    "cloud_cover": "cloud_cover",
    "precipitation": "precipitation_mm",
}


def request_batch(session, locations):
    params = {
        "latitude": ",".join(str(item["latitude"]) for item in locations),
        "longitude": ",".join(str(item["longitude"]) for item in locations),
        "hourly": HOURLY_FIELDS,
        "past_hours": 48,
        "forecast_hours": 1,
        "timezone": TIMEZONE,
        "temperature_unit": "celsius",
        "wind_speed_unit": "kmh",
        "precipitation_unit": "mm",
    }
    error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = session.get(API_URL, params=params, timeout=TIMEOUT_SECONDS)
            response.raise_for_status()
            result = response.json()
            if isinstance(result, dict):
                result = [result]
            if not isinstance(result, list) or len(result) != len(locations):
                raise ValueError("Open-Meteo batch size does not match requested locations.")
            return result
        except (requests.RequestException, ValueError) as exc:
            error = exc
            if attempt < MAX_ATTEMPTS:
                time.sleep(attempt)
    raise RuntimeError(f"Open-Meteo request failed after {MAX_ATTEMPTS} attempts: {error}") from error


def parse_records(locations, payloads, fetched_at):
    records = []
    for location, payload in zip(locations, payloads):
        hourly = payload.get("hourly")
        if not isinstance(hourly, dict) or not isinstance(hourly.get("time"), list):
            raise ValueError(f"Missing hourly timestamps for {location['location_id']}.")
        timestamps = hourly["time"]
        if len(timestamps) < 25:
            raise ValueError(f"Insufficient hourly rows for {location['location_id']}: {len(timestamps)}.")
        for provider_field in FIELD_MAP:
            values = hourly.get(provider_field)
            if not isinstance(values, list) or len(values) != len(timestamps):
                raise ValueError(f"Invalid {provider_field} values for {location['location_id']}.")
        returned_lat = payload.get("latitude")
        returned_lon = payload.get("longitude")
        if returned_lat is None or returned_lon is None:
            raise ValueError(f"Open-Meteo omitted returned coordinates for {location['location_id']}.")
        if not (-90 <= float(returned_lat) <= 90 and -180 <= float(returned_lon) <= 180):
            raise ValueError(f"Open-Meteo returned invalid coordinates for {location['location_id']}.")
        seen = set()
        for index, stamp in enumerate(timestamps):
            try:
                parsed = datetime.fromisoformat(stamp)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Invalid timestamp for {location['location_id']}: {stamp!r}.") from exc
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=LOCAL_ZONE)
            parsed = parsed.astimezone(timezone.utc)
            if parsed in seen:
                raise ValueError(f"Duplicate timestamp for {location['location_id']}: {stamp}.")
            seen.add(parsed)
            values = {}
            for provider_field, db_field in FIELD_MAP.items():
                raw = hourly[provider_field][index]
                if raw is None:
                    values[db_field] = None
                    continue
                try:
                    numeric = float(raw)
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"Invalid {provider_field} for {location['location_id']} at {stamp}.") from exc
                if not (-1e6 < numeric < 1e6):
                    raise ValueError(f"Non-finite or unreasonable {provider_field} for {location['location_id']} at {stamp}.")
                values[db_field] = numeric
            records.append((
                location["location_id"], parsed, fetched_at,
                "Open-Meteo Forecast API", "weather_model_output", False,
                float(location["latitude"]), float(location["longitude"]),
                values["temperature_2m"], values["precipitation_mm"],
                values["relative_humidity_2m"], values["surface_pressure_hpa"],
                values["wind_speed_10m"], values["cloud_cover"],
            ))
    return records


def persist_records(records):
    sql = """INSERT INTO public.weather_provider_inputs (
        location_code, timestamp, fetched_at_utc, source, data_type,
        is_verified_station_observation, latitude, longitude, temperature_2m,
        precipitation_mm, relative_humidity_2m, surface_pressure_hpa,
        wind_speed_10m, cloud_cover
    ) VALUES %s ON CONFLICT (location_code, timestamp) DO UPDATE SET
        fetched_at_utc = EXCLUDED.fetched_at_utc,
        source = EXCLUDED.source,
        data_type = EXCLUDED.data_type,
        is_verified_station_observation = EXCLUDED.is_verified_station_observation,
        latitude = EXCLUDED.latitude,
        longitude = EXCLUDED.longitude,
        temperature_2m = EXCLUDED.temperature_2m,
        precipitation_mm = EXCLUDED.precipitation_mm,
        relative_humidity_2m = EXCLUDED.relative_humidity_2m,
        surface_pressure_hpa = EXCLUDED.surface_pressure_hpa,
        wind_speed_10m = EXCLUDED.wind_speed_10m,
        cloud_cover = EXCLUDED.cloud_cover"""
    with closing(get_connection()) as connection:
        with connection:
            with connection.cursor() as cursor:
                execute_values(cursor, sql, records, page_size=1000)


def ensure_schema():
    schema = SCHEMA_FILE.read_text(encoding="utf-8")
    with closing(get_connection()) as connection:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(schema)


def refresh(limit=None, session=None):
    ensure_schema()
    locations = load_grid(limit)
    fetched_at = datetime.now(timezone.utc)
    session = session or requests.Session()
    all_records = []
    batches = (len(locations) + BATCH_SIZE - 1) // BATCH_SIZE
    for number, start in enumerate(range(0, len(locations), BATCH_SIZE), 1):
        batch = locations[start:start + BATCH_SIZE]
        print(f"Fetching weather inputs batch {number}/{batches} ({len(batch)} locations)")
        payloads = request_batch(session, batch)
        all_records.extend(parse_records(batch, payloads, fetched_at))
        if number < batches:
            time.sleep(REQUEST_DELAY_SECONDS)
    if not all_records:
        raise ValueError("Open-Meteo returned no weather input records.")
    expected_locations = {item["location_id"] for item in locations}
    if {record[0] for record in all_records} != expected_locations:
        raise ValueError("Collected provider locations do not match requested locations.")
    persist_records(all_records)
    missing_values = sum(value is None for record in all_records for value in record[8:])
    if missing_values:
        print(f"Warning: provider returned {missing_values} null required-field values; affected prediction windows will be unavailable.")
    print(f"Upserted {len(all_records)} provider model-input rows for {len(expected_locations)} locations.")
    return len(all_records)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, help="Limit locations for a controlled run.")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    refresh(args.limit)
