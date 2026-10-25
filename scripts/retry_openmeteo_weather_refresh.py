
import json
import os
import sys
import time
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data_pipeline.crawlers.weather import refresh_openmeteo_historical as refresh

STAGING_DIR = Path(
    os.environ.get(
        "WEATHER_STAGING_DIR",
        str(
            PROJECT_ROOT
            / "data"
            / "processed"
            / "weather_refresh_staging_2026-07-14_to-2026-10-21"
        ),
    )
).resolve()

MANIFEST_FILE = STAGING_DIR / "refresh_manifest.json"
BATCH_SIZE = 2
MAX_ATTEMPTS = 4
RATE_LIMIT_WAIT = 120
DELAY_BETWEEN_BATCHES = 15


def save_manifest(manifest):
    temp = MANIFEST_FILE.with_suffix(".tmp")
    temp.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    temp.replace(MANIFEST_FILE)


def verify_csv(path, expected_hours, expected_index):
    try:
        frame = pd.read_csv(path)
        required = {"location_id", "timestamp", *refresh.HOURLY_VARIABLES}
        if not required.issubset(frame.columns):
            return None

        timestamps = pd.to_datetime(frame["timestamp"], errors="raise")
        if (
            len(frame) != expected_hours
            or timestamps.duplicated().any()
            or not timestamps.reset_index(drop=True).equals(
                pd.Series(expected_index)
            )
        ):
            return None

        location_id = str(frame["location_id"].iloc[0])
        return {
            "location_id": location_id,
            "rows": len(frame),
            "first_timestamp": str(timestamps.min()),
            "last_timestamp": str(timestamps.max()),
        }
    except Exception:
        return None


def main():
    if not STAGING_DIR.is_dir():
        raise FileNotFoundError(f"Staging directory not found: {STAGING_DIR}")
    if not MANIFEST_FILE.is_file():
        raise FileNotFoundError(f"Manifest not found: {MANIFEST_FILE}")

    manifest = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))

    refresh.STAGING_DIR = STAGING_DIR
    refresh.MANIFEST_FILE = MANIFEST_FILE
    refresh.MAX_RETRIES = 1

    grid = refresh.load_grid()
    expected_hours = refresh.validate_date_range()
    expected_index = pd.date_range(
        start=f"{refresh.START_DATE} 00:00:00",
        end=f"{refresh.END_DATE} 23:00:00",
        freq="h",
    )

    verified = {}
    for location_id in grid["location_id"].astype(str):
        path = STAGING_DIR / f"weather_{location_id}.csv"
        if path.is_file():
            entry = verify_csv(path, expected_hours, expected_index)
            if entry and entry["location_id"] == location_id:
                verified[location_id] = entry

    pending = grid[
        ~grid["location_id"].astype(str).isin(verified)
    ].copy()

    print(f"Staging: {STAGING_DIR}")
    print(f"Verified existing CSVs: {len(verified)}/{len(grid)}")
    print(f"Locations to download: {len(pending)}")

    if pending.empty:
        manifest["successful_locations"] = list(verified.values())
        manifest["failed_batches"] = []
        manifest["status"] = "complete"
        save_manifest(manifest)
        print("All locations are already staged.")
        return

    failures = []
    batches = [
        pending.iloc[i:i + BATCH_SIZE]
        for i in range(0, len(pending), BATCH_SIZE)
    ]

    for number, batch in enumerate(batches, 1):
        ids = batch["location_id"].astype(str).tolist()
        print(f"\nBatch {number}/{len(batches)}: {', '.join(ids)}")
        error_text = "No successful response"
        succeeded = False

        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                results = refresh.fetch_batch(batch, expected_hours)
                result_map = {
                    str(item["location_id"]): item for item in results
                }
                if set(result_map) != set(ids):
                    raise RuntimeError("Returned locations do not match request.")

                # Validate all results before writing the batch.
                for location_id in ids:
                    output = result_map[location_id]["data"]
                    timestamps = pd.to_datetime(
                        output["timestamp"], errors="raise"
                    )
                    if (
                        len(output) != expected_hours
                        or timestamps.duplicated().any()
                        or not timestamps.reset_index(drop=True).equals(
                            pd.Series(expected_index)
                        )
                    ):
                        raise RuntimeError(
                            f"Data validation failed for {location_id}"
                        )

                for location_id in ids:
                    output = result_map[location_id]["data"]
                    destination = STAGING_DIR / f"weather_{location_id}.csv"
                    temporary = destination.with_suffix(".tmp")
                    output.to_csv(temporary, index=False)
                    temporary.replace(destination)

                    entry = verify_csv(
                        destination, expected_hours, expected_index
                    )
                    if not entry or entry["location_id"] != location_id:
                        raise RuntimeError(
                            f"Saved CSV validation failed for {location_id}"
                        )
                    verified[location_id] = entry

                succeeded = True
                print(f"Recovered {len(ids)} locations.")
                break

            except Exception as exc:
                error_text = str(exc)
                print(f"Attempt {attempt}/{MAX_ATTEMPTS} failed: {error_text[:180]}")
                if attempt < MAX_ATTEMPTS:
                    wait = (
                        min(RATE_LIMIT_WAIT * attempt, 600)
                        if "429" in error_text or "Too Many Requests" in error_text
                        else min(15 * attempt, 90)
                    )
                    print(f"Waiting {wait} seconds.")
                    time.sleep(wait)

        if not succeeded:
            failures.append({
                "batch_number": number,
                "location_ids": [
                    location_id for location_id in ids
                    if location_id not in verified
                ],
                "error": error_text,
            })

        manifest["successful_locations"] = list(verified.values())
        manifest["failed_batches"] = failures
        manifest["status"] = (
            "complete" if len(verified) == len(grid) else "incomplete"
        )
        save_manifest(manifest)

        print(f"Progress: {len(verified)}/{len(grid)}")

        if number < len(batches):
            time.sleep(DELAY_BETWEEN_BATCHES)

    manifest["successful_locations"] = list(verified.values())
    manifest["failed_batches"] = failures
    manifest["status"] = (
        "complete" if len(verified) == len(grid) else "incomplete"
    )
    save_manifest(manifest)

    print("\n--- Final recovery status ---")
    print(f"Verified: {len(verified)}/{len(grid)}")
    print(f"Failed batches: {len(failures)}")
    print(f"Status: {manifest['status']}")
    print(f"Manifest: {MANIFEST_FILE}")


if __name__ == "__main__":
    main()
