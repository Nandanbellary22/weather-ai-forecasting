
import json
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests


# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[3]

GRID_FILE = (
    PROJECT_ROOT
    / "data"
    / "config"
    / "vietnam_weather_grid_500.csv"
)

STAGING_DIR = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "weather_refresh_staging_2026-07-14_to_2026-10-21"
)

MANIFEST_FILE = STAGING_DIR / "refresh_manifest.json"

BASE_URL = "https://archive-api.open-meteo.com/v1/archive"

START_DATE = "2026-07-14"
END_DATE = "2026-10-21"

BATCH_SIZE = 20
MAX_RETRIES = 3
REQUEST_TIMEOUT = 120
DELAY_SECONDS = 1.0

HOURLY_VARIABLES = [
    "temperature_2m",
    "relative_humidity_2m",
    "dew_point_2m",
    "precipitation",
    "rain",
    "pressure_msl",
    "surface_pressure",
    "cloud_cover",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
]

OUTPUT_COLUMNS = [
    "location_id",
    "location_name",
    "latitude",
    "longitude",
    "timestamp",
    *HOURLY_VARIABLES,
]


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def write_manifest(manifest):
    """Write the progress report to the staging directory."""
    temporary_file = MANIFEST_FILE.with_suffix(".tmp")

    temporary_file.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    temporary_file.replace(MANIFEST_FILE)


def validate_date_range():
    start = date.fromisoformat(START_DATE)
    end = date.fromisoformat(END_DATE)

    if end < start:
        raise ValueError("END_DATE must not be earlier than START_DATE.")

    return (end - start).days * 24 + 24


def load_grid():
    if not GRID_FILE.exists():
        raise FileNotFoundError(f"Grid file not found: {GRID_FILE}")

    grid = pd.read_csv(
        GRID_FILE,
        dtype={"location_id": str},
    )

    required_columns = {
        "location_id",
        "latitude",
        "longitude",
    }

    missing_columns = required_columns - set(grid.columns)

    if missing_columns:
        raise ValueError(
            f"Grid file is missing columns: {sorted(missing_columns)}"
        )

    if "location_name" not in grid.columns:
        grid["location_name"] = grid["location_id"]

    grid["location_id"] = grid["location_id"].astype(str).str.strip()
    grid["latitude"] = pd.to_numeric(grid["latitude"], errors="raise")
    grid["longitude"] = pd.to_numeric(grid["longitude"], errors="raise")

    if grid["location_id"].eq("").any():
        raise ValueError("The grid contains an empty location_id.")

    if grid["location_id"].duplicated().any():
        raise ValueError("The grid contains duplicate location_id values.")

    if grid[["latitude", "longitude"]].isna().any().any():
        raise ValueError("The grid contains missing coordinates.")

    if not grid["latitude"].between(-90, 90).all():
        raise ValueError("The grid contains invalid latitudes.")

    if not grid["longitude"].between(-180, 180).all():
        raise ValueError("The grid contains invalid longitudes.")

    return grid


def fetch_batch(batch, expected_hours):
    """Fetch and validate a complete batch before saving its files."""
    latitudes = ",".join(
        format(float(value), ".6f")
        for value in batch["latitude"]
    )

    longitudes = ",".join(
        format(float(value), ".6f")
        for value in batch["longitude"]
    )

    params = {
        "latitude": latitudes,
        "longitude": longitudes,
        "start_date": START_DATE,
        "end_date": END_DATE,
        "hourly": ",".join(HOURLY_VARIABLES),
        "timezone": "Asia/Ho_Chi_Minh",
        "temperature_unit": "celsius",
        "wind_speed_unit": "kmh",
        "precipitation_unit": "mm",
    }

    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(
                BASE_URL,
                params=params,
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()

            if isinstance(payload, dict):
                if payload.get("error"):
                    raise RuntimeError(
                        payload.get("reason", "Open-Meteo API error")
                    )

                # A multi-location request should return one result
                # per requested location.
                if len(batch) != 1:
                    raise ValueError(
                        "Expected a list of location results, "
                        "but the API returned a single object."
                    )

                payload = [payload]

            if not isinstance(payload, list):
                raise ValueError("Unexpected API response format.")

            if len(payload) != len(batch):
                raise ValueError(
                    f"Requested {len(batch)} locations, "
                    f"received {len(payload)} results."
                )

            validated = []

            for (_, location), result in zip(
                batch.iterrows(), payload
            ):
                if not isinstance(result, dict):
                    raise ValueError(
                        f"Invalid response for {location['location_id']}."
                    )

                if result.get("error"):
                    raise ValueError(
                        f"API error for {location['location_id']}: "
                        f"{result.get('reason', 'unknown error')}"
                    )

                hourly = result.get("hourly")

                if not isinstance(hourly, dict):
                    raise ValueError(
                        f"Missing hourly data for {location['location_id']}."
                    )

                if "time" not in hourly:
                    raise ValueError(
                        f"Missing timestamps for {location['location_id']}."
                    )

                timestamps = pd.to_datetime(
                    hourly["time"],
                    errors="raise",
                )

                if len(timestamps) != expected_hours:
                    raise ValueError(
                        f"{location['location_id']}: expected "
                        f"{expected_hours} timestamps, got {len(timestamps)}."
                    )

                if timestamps.has_duplicates:
                    raise ValueError(
                        f"Duplicate timestamps for {location['location_id']}."
                    )

                expected_index = pd.date_range(
                    start=f"{START_DATE} 00:00:00",
                    end=f"{END_DATE} 23:00:00",
                    freq="h",
                )

                if not timestamps.equals(expected_index):
                    raise ValueError(
                        f"Unexpected hourly coverage for "
                        f"{location['location_id']}: "
                        f"{timestamps.min()} to {timestamps.max()}."
                    )

                missing_variables = [
                    variable
                    for variable in HOURLY_VARIABLES
                    if variable not in hourly
                ]

                if missing_variables:
                    raise ValueError(
                        f"{location['location_id']} is missing variables: "
                        f"{missing_variables}"
                    )

                row_lengths = {
                    len(hourly[variable])
                    for variable in HOURLY_VARIABLES
                }

                if row_lengths != {expected_hours}:
                    raise ValueError(
                        f"Hourly variable lengths do not match for "
                        f"{location['location_id']}."
                    )

                output = pd.DataFrame({
                    "location_id": location["location_id"],
                    "location_name": location["location_name"],
                    "latitude": float(location["latitude"]),
                    "longitude": float(location["longitude"]),
                    "timestamp": timestamps,
                })

                for variable in HOURLY_VARIABLES:
                    output[variable] = hourly[variable]

                output = output[OUTPUT_COLUMNS]

                # Missing weather values are reported in the manifest.
                # They are not silently filled or replaced.
                missing_counts = {
                    variable: int(output[variable].isna().sum())
                    for variable in HOURLY_VARIABLES
                    if output[variable].isna().any()
                }

                validated.append({
                    "location_id": location["location_id"],
                    "data": output,
                    "missing_counts": missing_counts,
                })

            return validated

        except Exception as exc:
            last_error = str(exc)

            print(
                f"  Attempt {attempt}/{MAX_RETRIES} failed: "
                f"{last_error}"
            )

            if attempt < MAX_RETRIES:
                time.sleep(2 * attempt)

    raise RuntimeError(
        f"Batch failed after {MAX_RETRIES} attempts: {last_error}"
    )


# ---------------------------------------------------------
# Main refresh
# ---------------------------------------------------------

def main():
    expected_hours = validate_date_range()
    grid = load_grid()

    print("=" * 65)
    print("OPEN-METEO HISTORICAL WEATHER REFRESH")
    print("=" * 65)
    print(f"Grid locations: {len(grid)}")
    print(f"Date range: {START_DATE} through {END_DATE}")
    print(f"Expected hours per location: {expected_hours:,}")
    print(f"Expected total rows: {len(grid) * expected_hours:,}")
    print(f"Staging directory: {STAGING_DIR}")
    print()

    # Refuse to reuse an old staging directory. This prevents a
    # previous partial run from being mistaken for a clean run.
    if STAGING_DIR.exists():
        raise FileExistsError(
            f"Staging directory already exists:\n{STAGING_DIR}\n\n"
            "Inspect or rename that staging directory before starting "
            "a fresh run. Existing data will not be deleted."
        )

    STAGING_DIR.mkdir(parents=True)

    manifest = {
        "status": "running",
        "source": "Open-Meteo Archive API",
        "start_date": START_DATE,
        "end_date": END_DATE,
        "expected_hours_per_location": expected_hours,
        "expected_locations": int(len(grid)),
        "expected_total_rows": int(len(grid) * expected_hours),
        "hourly_variables": HOURLY_VARIABLES,
        "batch_size": BATCH_SIZE,
        "successful_locations": [],
        "failed_batches": [],
        "missing_value_counts": {},
        "notes": [
            "Staging only; original historical CSVs are not modified.",
            "PostgreSQL is not modified.",
            "Forecast API data is not used.",
            "Missing weather values are reported, not imputed.",
        ],
    }

    write_manifest(manifest)

    batches = [
        grid.iloc[start:start + BATCH_SIZE].copy()
        for start in range(0, len(grid), BATCH_SIZE)
    ]

    with requests.Session() as session:
        # requests.Session is initialized for connection reuse;
        # fetch_batch uses requests.get so each request has a clear timeout.
        del session

    for batch_number, batch in enumerate(batches, start=1):
        first_id = batch.iloc[0]["location_id"]
        last_id = batch.iloc[-1]["location_id"]

        print(
            f"[{batch_number}/{len(batches)}] "
            f"Fetching {len(batch)} locations "
            f"({first_id} to {last_id})..."
        )

        try:
            results = fetch_batch(batch, expected_hours)

            # Save only after every location in this batch validates.
            for result in results:
                location_id = result["location_id"]
                output = result["data"]

                output_path = STAGING_DIR / f"weather_{location_id}.csv"
                temporary_path = output_path.with_suffix(".tmp")

                output.to_csv(
                    temporary_path,
                    index=False,
                    date_format="%Y-%m-%d %H:%M:%S",
                )
                temporary_path.replace(output_path)

                manifest["successful_locations"].append({
                    "location_id": location_id,
                    "rows": int(len(output)),
                    "first_timestamp": str(output["timestamp"].min()),
                    "last_timestamp": str(output["timestamp"].max()),
                    "file": output_path.name,
                })

                for variable, count in result["missing_counts"].items():
                    manifest["missing_value_counts"][variable] = (
                        manifest["missing_value_counts"].get(variable, 0)
                        + count
                    )

            print(f"  Saved and validated {len(results)} locations.")

        except Exception as exc:
            error = {
                "batch_number": batch_number,
                "location_ids": batch["location_id"].tolist(),
                "error": str(exc),
            }

            manifest["failed_batches"].append(error)
            print(f"  BATCH FAILED: {exc}")

        write_manifest(manifest)
        time.sleep(DELAY_SECONDS)

    success_count = len(manifest["successful_locations"])
    failure_count = len(grid) - success_count

    if failure_count == 0:
        manifest["status"] = "completed"
    else:
        manifest["status"] = "incomplete"

    manifest["summary"] = {
        "successful_locations": success_count,
        "unsuccessful_locations": failure_count,
        "failed_batches": len(manifest["failed_batches"]),
        "staged_rows": sum(
            item["rows"] for item in manifest["successful_locations"]
        ),
        "missing_value_counts": manifest["missing_value_counts"],
    }

    write_manifest(manifest)

    print()
    print("=" * 65)
    print("REFRESH SUMMARY")
    print("=" * 65)
    print(f"Status: {manifest['status']}")
    print(f"Successful locations: {success_count}/{len(grid)}")
    print(f"Unsuccessful locations: {failure_count}")
    print(f"Staged rows: {manifest['summary']['staged_rows']:,}")
    print(f"Manifest: {MANIFEST_FILE}")

    if manifest["missing_value_counts"]:
        print("\nMissing values by variable:")
        for variable, count in manifest["missing_value_counts"].items():
            print(f"  {variable}: {count:,}")

    print("\nNo existing historical CSVs or database records were changed.")

    if failure_count:
        raise SystemExit(
            "Refresh is incomplete. Review the manifest before proceeding."
        )


if __name__ == "__main__":
    main()

