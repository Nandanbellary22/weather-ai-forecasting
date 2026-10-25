
import json
import time
from pathlib import Path

import pandas as pd
import requests


PROJECT_ROOT = Path(__file__).resolve().parents[3]

GRID_FILE = (
    PROJECT_ROOT / "data" / "config" / "vietnam_weather_grid_500.csv"
)

STAGING_DIR = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "weather_refresh_staging_2026-07-14_to_2026-10-16"
)

MANIFEST_FILE = STAGING_DIR / "refresh_manifest.json"

BASE_URL = "https://archive-api.open-meteo.com/v1/archive"
START_DATE = "2026-07-14"
END_DATE = "2026-10-16"

MAX_RETRIES = 5
REQUEST_TIMEOUT = 120
DELAY_BETWEEN_LOCATIONS = 12

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


def save_manifest(manifest):
    temporary_path = MANIFEST_FILE.with_suffix(".tmp")
    temporary_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    temporary_path.replace(MANIFEST_FILE)


def fetch_location(location):
    params = {
        "latitude": float(location["latitude"]),
        "longitude": float(location["longitude"]),
        "start_date": START_DATE,
        "end_date": END_DATE,
        "hourly": ",".join(HOURLY_VARIABLES),
        "timezone": "Asia/Ho_Chi_Minh",
        "temperature_unit": "celsius",
        "wind_speed_unit": "kmh",
        "precipitation_unit": "mm",
    }

    expected_timestamps = pd.date_range(
        start=f"{START_DATE} 00:00:00",
        end=f"{END_DATE} 23:00:00",
        freq="h",
    )

    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(
                BASE_URL,
                params=params,
                timeout=REQUEST_TIMEOUT,
            )

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                try:
                    wait_seconds = float(retry_after)
                except (TypeError, ValueError):
                    wait_seconds = min(60 * (2 ** (attempt - 1)), 600)

                if attempt == MAX_RETRIES:
                    response.raise_for_status()

                print(
                    f"    HTTP 429. Waiting {wait_seconds:.0f} seconds "
                    f"before retry {attempt + 1}/{MAX_RETRIES}."
                )
                time.sleep(wait_seconds)
                continue

            response.raise_for_status()
            payload = response.json()

            if not isinstance(payload, dict) or payload.get("error"):
                raise ValueError(
                    str(payload.get("reason", "Unexpected API response"))
                    if isinstance(payload, dict)
                    else "Unexpected API response format"
                )

            hourly = payload.get("hourly")

            if not isinstance(hourly, dict):
                raise ValueError("Response has no hourly data.")

            if "time" not in hourly:
                raise ValueError("Response has no hourly timestamps.")

            timestamps = pd.DatetimeIndex(
                pd.to_datetime(hourly["time"], errors="raise")
            )

            if not timestamps.equals(expected_timestamps):
                raise ValueError(
                    f"Hourly timestamp coverage mismatch: "
                    f"{len(timestamps)} timestamps received."
                )

            if timestamps.has_duplicates:
                raise ValueError("Duplicate hourly timestamps.")

            missing_variables = [
                variable
                for variable in HOURLY_VARIABLES
                if variable not in hourly
            ]

            if missing_variables:
                raise ValueError(
                    f"Missing variables: {missing_variables}"
                )

            for variable in HOURLY_VARIABLES:
                if len(hourly[variable]) != len(timestamps):
                    raise ValueError(
                        f"Unexpected length for {variable}."
                    )

            frame = pd.DataFrame({
                "location_id": str(location["location_id"]),
                "location_name": str(location["location_name"]),
                "latitude": float(location["latitude"]),
                "longitude": float(location["longitude"]),
                "timestamp": timestamps,
            })

            for variable in HOURLY_VARIABLES:
                frame[variable] = hourly[variable]

            frame = frame[OUTPUT_COLUMNS]

            missing_counts = {
                variable: int(frame[variable].isna().sum())
                for variable in HOURLY_VARIABLES
                if frame[variable].isna().any()
            }

            return frame, missing_counts

        except Exception as exc:
            last_error = str(exc)
            print(
                f"    Attempt {attempt}/{MAX_RETRIES} failed: "
                f"{last_error}"
            )

            if attempt < MAX_RETRIES:
                time.sleep(min(30 * (2 ** (attempt - 1)), 300))

    raise RuntimeError(
        f"Failed after {MAX_RETRIES} attempts: {last_error}"
    )


def main():
    if not MANIFEST_FILE.exists():
        raise FileNotFoundError(
            f"Manifest not found: {MANIFEST_FILE}"
        )

    if not GRID_FILE.exists():
        raise FileNotFoundError(f"Grid file not found: {GRID_FILE}")

    manifest = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))

    if manifest.get("start_date") != START_DATE:
        raise ValueError("Manifest start date does not match this script.")

    if manifest.get("end_date") != END_DATE:
        raise ValueError("Manifest end date does not match this script.")

    grid = pd.read_csv(GRID_FILE, dtype={"location_id": str})
    required = {"location_id", "latitude", "longitude"}

    if not required.issubset(grid.columns):
        raise ValueError(
            f"Grid is missing columns: {sorted(required - set(grid.columns))}"
        )

    if "location_name" not in grid.columns:
        grid["location_name"] = grid["location_id"]

    grid["location_id"] = grid["location_id"].astype(str).str.strip()

    successful_ids = {
        item["location_id"]
        for item in manifest.get("successful_locations", [])
    }

    # Recover only locations not already recorded as successful.
    missing_ids = [
        str(location_id)
        for batch in manifest.get("failed_batches", [])
        for location_id in batch.get("location_ids", [])
        if str(location_id) not in successful_ids
    ]

    # Preserve order while removing duplicate IDs.
    missing_ids = list(dict.fromkeys(missing_ids))

    if not missing_ids:
        print("No missing locations were found in the manifest.")
        return

    grid_lookup = grid.set_index("location_id", drop=False)

    unknown_ids = [
        location_id
        for location_id in missing_ids
        if location_id not in grid_lookup.index
    ]

    if unknown_ids:
        raise ValueError(f"IDs not found in grid: {unknown_ids}")

    # Refuse to overwrite any file, even if the manifest does not
    # currently list it as successful.
    for location_id in missing_ids:
        output_path = STAGING_DIR / f"weather_{location_id}.csv"
        if output_path.exists():
            raise FileExistsError(
                f"Refusing to overwrite existing file: {output_path}"
            )

    print("=" * 60)
    print("OPEN-METEO HISTORICAL RECOVERY")
    print("=" * 60)
    print(f"Locations to recover: {len(missing_ids)}")
    print(f"Delay between locations: {DELAY_BETWEEN_LOCATIONS} seconds")
    print("Existing successful files will not be overwritten.")
    print("PostgreSQL will not be modified.")
    print()

    recovered = 0
    failures = []

    for index, location_id in enumerate(missing_ids, start=1):
        location = grid_lookup.loc[location_id]

        print(f"[{index}/{len(missing_ids)}] {location_id}")

        try:
            frame, missing_counts = fetch_location(location)

            output_path = STAGING_DIR / f"weather_{location_id}.csv"
            temporary_path = output_path.with_suffix(".tmp")

            frame.to_csv(
                temporary_path,
                index=False,
                date_format="%Y-%m-%d %H:%M:%S",
            )
            temporary_path.replace(output_path)

            manifest.setdefault("successful_locations", []).append({
                "location_id": location_id,
                "rows": int(len(frame)),
                "first_timestamp": str(frame["timestamp"].min()),
                "last_timestamp": str(frame["timestamp"].max()),
                "file": output_path.name,
            })

            for variable, count in missing_counts.items():
                manifest.setdefault("missing_value_counts", {})
                manifest["missing_value_counts"][variable] = (
                    manifest["missing_value_counts"].get(variable, 0)
                    + count
                )

            # Record progress immediately, so an interrupted run
            # can safely resume without redownloading successful files.
            save_manifest(manifest)
            recovered += 1
            print(f"    Saved {len(frame):,} rows.")

        except Exception as exc:
            failures.append({
                "location_id": location_id,
                "error": str(exc),
            })
            print(f"    FAILED: {exc}")

            manifest.setdefault("recovery_failures", [])
            manifest["recovery_failures"] = [
                item
                for item in manifest["recovery_failures"]
                if item.get("location_id") != location_id
            ]
            manifest["recovery_failures"].append(failures[-1])
            save_manifest(manifest)

        if index < len(missing_ids):
            time.sleep(DELAY_BETWEEN_LOCATIONS)

    successful_ids = {
        item["location_id"]
        for item in manifest.get("successful_locations", [])
    }

    remaining_ids = [
        str(location_id)
        for batch in manifest.get("failed_batches", [])
        for location_id in batch.get("location_ids", [])
        if str(location_id) not in successful_ids
    ]

    remaining_ids = list(dict.fromkeys(remaining_ids))

    manifest["status"] = (
        "completed"
        if len(successful_ids) == len(grid) and not remaining_ids
        else "incomplete"
    )

    manifest["summary"] = {
        "successful_locations": len(successful_ids),
        "expected_locations": len(grid),
        "remaining_failed_locations": len(remaining_ids),
        "staged_rows": sum(
            int(item.get("rows", 0))
            for item in manifest.get("successful_locations", [])
        ),
        "recovery_successes_this_run": recovered,
        "recovery_failures_this_run": len(failures),
        "missing_value_counts": manifest.get("missing_value_counts", {}),
    }

    save_manifest(manifest)

    print()
    print("=" * 60)
    print("RECOVERY SUMMARY")
    print("=" * 60)
    print(f"Recovered this run: {recovered}")
    print(f"Successful locations total: {len(successful_ids)}/{len(grid)}")
    print(f"Locations still missing: {len(remaining_ids)}")
    print(f"Manifest status: {manifest['status']}")
    print(f"Manifest: {MANIFEST_FILE}")
    print("No existing successful files or database records were changed.")


if __name__ == "__main__":
    main()
