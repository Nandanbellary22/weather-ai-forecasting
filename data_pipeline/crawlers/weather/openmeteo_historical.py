import time
from pathlib import Path

import pandas as pd
import requests


BASE_URL = "https://archive-api.open-meteo.com/v1/archive"

START_DATE = "2026-01-15"
END_DATE = "2026-07-13"

INPUT_FILE = Path("data/config/vietnam_locations.csv")
OUTPUT_DIR = Path("data/processed/weather")

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


def fetch_location(row):
    location_id = str(row["location_id"]).strip()
    location_name = str(row["location_name"]).strip()

    latitude = float(row["latitude"])
    longitude = float(row["longitude"])

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": START_DATE,
        "end_date": END_DATE,
        "hourly": ",".join(HOURLY_VARIABLES),
        "timezone": "Asia/Ho_Chi_Minh",
        "temperature_unit": "celsius",
        "wind_speed_unit": "kmh",
        "precipitation_unit": "mm",
    }

    print(
        f"Fetching {location_name}: "
        f"{START_DATE} -> {END_DATE}"
    )

    response = requests.get(
        BASE_URL,
        params=params,
        timeout=(15, 90),
    )

    response.raise_for_status()

    data = response.json()

    hourly = data.get("hourly")

    if not hourly:
        raise ValueError(
            f"No hourly data returned for {location_name}"
        )

    df = pd.DataFrame(hourly)

    df["location_id"] = location_id
    df["location_name"] = location_name
    df["latitude"] = latitude
    df["longitude"] = longitude

    df["timestamp"] = pd.to_datetime(
        df["time"],
        errors="coerce",
    )

    df = df.drop(columns=["time"])

    columns = [
        "location_id",
        "location_name",
        "latitude",
        "longitude",
        "timestamp",
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

    return df[columns]


def validate_data(df):
    print("\nFinal validation")
    print("----------------")
    print(f"Total rows: {len(df)}")
    print(f"Locations: {df['location_id'].nunique()}")
    print(f"Duplicate rows: {df.duplicated().sum()}")

    duplicate_times = df.duplicated(
        ["location_id", "timestamp"]
    ).sum()

    print(
        f"Duplicate location/timestamps: "
        f"{duplicate_times}"
    )

    print(
        f"Missing temperature: "
        f"{df['temperature_2m'].isna().sum()}"
    )

    print(
        f"Missing precipitation: "
        f"{df['precipitation'].isna().sum()}"
    )

    print("\nRows per location:")
    print(
        df.groupby(
            ["location_id", "location_name"]
        ).size()
    )


def main():
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    locations = pd.read_csv(INPUT_FILE)

    for _, row in locations.iterrows():

        location_id = str(
            row["location_id"]
        ).strip()

        location_name = str(
            row["location_name"]
        ).strip()

        output_file = (
            OUTPUT_DIR
            / f"weather_{location_id}.csv"
        )

        # Do not download locations that already exist.
        if output_file.exists():
            print(
                f"SKIP {location_name}: "
                f"{output_file} already exists"
            )
            continue

        try:
            df = fetch_location(row)

            df.to_csv(
                output_file,
                index=False,
            )

            print(
                f"Saved {len(df)} rows -> "
                f"{output_file}"
            )

        except Exception as exc:
            print(
                f"ERROR for {location_name}: "
                f"{type(exc).__name__}: {exc}"
            )

        time.sleep(1)

    # Combine every successfully downloaded location.
    all_files = sorted(
        OUTPUT_DIR.glob("weather_*.csv")
    )

    if not all_files:
        raise RuntimeError(
            "No weather files found."
        )

    print(
        f"\nCombining {len(all_files)} weather files..."
    )

    frames = []

    for file in all_files:
        frames.append(
            pd.read_csv(file)
        )

    combined = pd.concat(
        frames,
        ignore_index=True,
    )

    combined["timestamp"] = pd.to_datetime(
        combined["timestamp"]
    )

    combined = combined.sort_values(
        ["timestamp", "location_id"]
    )

    combined_file = (
        OUTPUT_DIR
        / "vietnam_weather_hourly.csv"
    )

    combined.to_csv(
        combined_file,
        index=False,
    )

    validate_data(combined)

    print(
        f"\nCombined dataset saved to:"
        f"\n{combined_file}"
    )


if __name__ == "__main__":
    main()
