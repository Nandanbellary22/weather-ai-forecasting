
import argparse
import csv
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests


API_URL = "https://api.open-meteo.com/v1/forecast"
GRID_FILE = Path("data/config/vietnam_weather_grid_500.csv")
OUTPUT_DIR = Path("data/processed/temperature_forecast_snapshots")

TIMEZONE = "Asia/Ho_Chi_Minh"
FORECAST_HOURS = 48
BATCH_SIZE = 20
REQUEST_DELAY_SECONDS = 1.0
MAX_ATTEMPTS = 3
REQUEST_TIMEOUT_SECONDS = 90

COLUMNS = [
    "collection_time_utc",
    "target_time_local",
    "timezone",
    "source",
    "location_id",
    "location_name",
    "requested_latitude",
    "requested_longitude",
    "returned_latitude",
    "returned_longitude",
    "forecast_temperature_c",
]


def load_grid(limit=None):
    if not GRID_FILE.is_file():
        raise FileNotFoundError(f"Grid file not found: {GRID_FILE}")

    with GRID_FILE.open("r", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        required = {
            "location_id",
            "location_name",
            "latitude",
            "longitude",
        }

        if not required.issubset(reader.fieldnames or []):
            raise ValueError(
                f"Grid must contain columns: {sorted(required)}"
            )

        locations = list(reader)

    if not locations:
        raise ValueError("The grid contains no locations.")

    seen_ids = set()

    for location in locations:
        location["location_id"] = location["location_id"].strip()
        location["location_name"] = location["location_name"].strip()

        if not location["location_id"]:
            raise ValueError("A grid location has an empty ID.")

        if location["location_id"] in seen_ids:
            raise ValueError(
                f"Duplicate location ID: {location['location_id']}"
            )

        seen_ids.add(location["location_id"])

        try:
            location["latitude"] = float(location["latitude"])
            location["longitude"] = float(location["longitude"])
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Invalid coordinates for {location['location_id']}"
            ) from exc

        if not -90 <= location["latitude"] <= 90:
            raise ValueError(
                f"Invalid latitude for {location['location_id']}"
            )

        if not -180 <= location["longitude"] <= 180:
            raise ValueError(
                f"Invalid longitude for {location['location_id']}"
            )

    if limit is not None:
        locations = locations[:limit]

    return locations


def request_batch(session, batch):
    params = {
        "latitude": ",".join(str(item["latitude"]) for item in batch),
        "longitude": ",".join(str(item["longitude"]) for item in batch),
        "hourly": "temperature_2m",
        "forecast_hours": FORECAST_HOURS,
        "timezone": TIMEZONE,
        "temperature_unit": "celsius",
    }

    last_error = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = session.get(
                API_URL,
                params=params,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload = response.json()

            if isinstance(payload, dict):
                payload = [payload]

            if not isinstance(payload, list) or len(payload) != len(batch):
                raise ValueError(
                    "API response count does not match batch size: "
                    f"{len(payload) if isinstance(payload, list) else 'invalid'} "
                    f"!= {len(batch)}"
                )

            return payload

        except (requests.RequestException, ValueError) as exc:
            last_error = exc

            if attempt < MAX_ATTEMPTS:
                time.sleep(attempt * 2)

    raise RuntimeError(
        f"API batch failed after {MAX_ATTEMPTS} attempts."
    ) from last_error


def collect_forecasts(locations):
    collection_time = datetime.now(timezone.utc).isoformat(
        timespec="seconds"
    )
    local_zone = ZoneInfo(TIMEZONE)
    records = []

    with requests.Session() as session:
        total_batches = (
            len(locations) + BATCH_SIZE - 1
        ) // BATCH_SIZE

        for batch_number, start in enumerate(
            range(0, len(locations), BATCH_SIZE),
            start=1,
        ):
            batch = locations[start:start + BATCH_SIZE]

            print(
                f"Fetching batch {batch_number}/{total_batches} "
                f"({len(batch)} locations)..."
            )

            responses = request_batch(session, batch)

            for location, payload in zip(batch, responses):
                hourly = payload.get("hourly")

                if not isinstance(hourly, dict):
                    raise ValueError(
                        f"Missing hourly data for "
                        f"{location['location_id']}"
                    )

                times = hourly.get("time")
                temperatures = hourly.get("temperature_2m")

                if (
                    not isinstance(times, list)
                    or not isinstance(temperatures, list)
                    or len(times) != len(temperatures)
                    or len(times) != FORECAST_HOURS
                ):
                    raise ValueError(
                        f"Unexpected forecast length for "
                        f"{location['location_id']}"
                    )

                for target_time, temperature in zip(times, temperatures):
                    if temperature is None:
                        continue

                    try:
                        numeric_temperature = float(temperature)
                        parsed_time = datetime.fromisoformat(target_time)
                    except (TypeError, ValueError) as exc:
                        raise ValueError(
                            f"Invalid forecast value for "
                            f"{location['location_id']}: "
                            f"{target_time}, {temperature}"
                        ) from exc

                    if parsed_time.tzinfo is None:
                        parsed_time = parsed_time.replace(tzinfo=local_zone)
                    else:
                        parsed_time = parsed_time.astimezone(local_zone)

                    records.append({
                        "collection_time_utc": collection_time,
                        "target_time_local": parsed_time.isoformat(
                            timespec="minutes"
                        ),
                        "timezone": TIMEZONE,
                        "source": "Open-Meteo Forecast API",
                        "location_id": location["location_id"],
                        "location_name": location["location_name"],
                        "requested_latitude": location["latitude"],
                        "requested_longitude": location["longitude"],
                        "returned_latitude": payload.get("latitude"),
                        "returned_longitude": payload.get("longitude"),
                        "forecast_temperature_c": numeric_temperature,
                    })

            time.sleep(REQUEST_DELAY_SECONDS)

    expected_minimum = len(locations) * FORECAST_HOURS

    if len(records) < expected_minimum:
        raise ValueError(
            f"Incomplete collection: {len(records)} rows; "
            f"expected at least {expected_minimum}."
        )

    unique_pairs = {
        (row["location_id"], row["target_time_local"])
        for row in records
    }

    if len(unique_pairs) != len(records):
        raise ValueError(
            "Duplicate location/target-time records detected."
        )

    return records


def save_snapshot(records):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    run_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_file = OUTPUT_DIR / f"temperature_forecast_{run_stamp}.csv"

    # Exclusive creation prevents accidentally overwriting an existing run.
    with output_file.open(
        "x",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.DictWriter(file, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(records)

    return output_file


def main():
    parser = argparse.ArgumentParser(
        description="Collect isolated Open-Meteo temperature forecast snapshots."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit the number of locations for a test run.",
    )
    args = parser.parse_args()

    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1.")

    locations = load_grid(args.limit)

    print(f"Locations: {len(locations)}")
    print(f"Forecast horizon: {FORECAST_HOURS} hours")
    print(f"Output directory: {OUTPUT_DIR}")

    records = collect_forecasts(locations)
    output_file = save_snapshot(records)

    print("\nCollection completed.")
    print(f"Locations collected: {len(locations)}")
    print(f"Rows saved: {len(records):,}")
    print(f"Snapshot: {output_file}")


if __name__ == "__main__":
    main()
