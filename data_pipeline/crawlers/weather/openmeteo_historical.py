import time
from pathlib import Path

import pandas as pd
import requests


BASE_URL = "https://archive-api.open-meteo.com/v1/archive"

START_DATE = "2026-01-15"
END_DATE = "2026-07-13"

INPUT_FILE = Path(
    "data/config/vietnam_weather_grid_500.csv"
)

OUTPUT_DIR = Path(
    "data/processed/weather"
)

# Number of locations per API request.
BATCH_SIZE = 20

# Delay between API requests.
REQUEST_DELAY = 1.0

# None = full 500-location dataset.
# Use an integer such as 20 only for testing.
TEST_LOCATION_LIMIT = None


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


def fetch_batch(batch):
    """Fetch multiple locations in one Open-Meteo request."""

    latitudes = ",".join(
        str(float(row["latitude"]))
        for _, row in batch.iterrows()
    )

    longitudes = ",".join(
        str(float(row["longitude"]))
        for _, row in batch.iterrows()
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

    response = requests.get(
        BASE_URL,
        params=params,
        timeout=(30, 180),
    )

    response.raise_for_status()

    data = response.json()

    if not isinstance(data, list):
        data = [data]

    if len(data) != len(batch):
        raise ValueError(
            "Number of API responses does not match "
            f"number of requested locations: "
            f"{len(data)} != {len(batch)}"
        )

    frames = []

    for (_, row), location_data in zip(
        batch.iterrows(),
        data,
    ):
        hourly = location_data.get("hourly")

        if not hourly:
            raise ValueError(
                f"No hourly data returned for "
                f"{row['location_id']}"
            )

        df = pd.DataFrame(hourly)

        df["location_id"] = str(
            row["location_id"]
        ).strip()

        df["location_name"] = str(
            row["location_name"]
        ).strip()

        df["latitude"] = float(
            row["latitude"]
        )

        df["longitude"] = float(
            row["longitude"]
        )

        df["timestamp"] = pd.to_datetime(
            df["time"],
            errors="coerce",
        )

        df = df.drop(
            columns=["time"]
        )

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

        frames.append(
            df[columns]
        )

    return frames


def load_existing_location_ids():
    """Find locations that already have downloaded CSV files."""

    existing_ids = set()

    if not OUTPUT_DIR.exists():
        return existing_ids

    for file in OUTPUT_DIR.glob("weather_*.csv"):
        location_id = file.stem.replace(
            "weather_",
            "",
            1,
        )

        existing_ids.add(location_id)

    return existing_ids


def validate_data(df):
    print()
    print("Final validation")
    print("----------------")

    print(
        f"Total rows: {len(df):,}"
    )

    print(
        f"Locations: "
        f"{df['location_id'].nunique()}"
    )

    print(
        f"Duplicate rows: "
        f"{df.duplicated().sum()}"
    )

    duplicate_times = df.duplicated(
        ["location_id", "timestamp"]
    ).sum()

    print(
        "Duplicate location/timestamps: "
        f"{duplicate_times}"
    )

    print(
        "Missing temperature: "
        f"{df['temperature_2m'].isna().sum():,}"
    )

    print(
        "Missing precipitation: "
        f"{df['precipitation'].isna().sum():,}"
    )

    print()
    print("Rows per location:")

    rows_per_location = (
        df.groupby(
            ["location_id", "location_name"]
        )
        .size()
    )

    print(rows_per_location.describe())

    print()
    print(
        f"Minimum rows/location: "
        f"{rows_per_location.min()}"
    )

    print(
        f"Maximum rows/location: "
        f"{rows_per_location.max()}"
    )


def main():

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    locations = pd.read_csv(
        INPUT_FILE
    )

    required_columns = {
        "location_id",
        "location_name",
        "latitude",
        "longitude",
    }

    missing = (
        required_columns
        - set(locations.columns)
    )

    if missing:
        raise ValueError(
            f"Missing columns: {missing}"
        )

    print(
        f"Loaded {len(locations)} locations."
    )

    # -----------------------------------------------------
    # Optional test limit
    # -----------------------------------------------------

    if TEST_LOCATION_LIMIT is not None:

        locations = locations.head(
            TEST_LOCATION_LIMIT
        ).copy()

        print(
            f"TEST MODE: using only "
            f"{len(locations)} locations."
        )

    else:

        print(
            "FULL MODE: target dataset has "
            f"{len(locations)} locations."
        )

    # -----------------------------------------------------
    # Detect already downloaded locations
    # -----------------------------------------------------

    existing_ids = (
        load_existing_location_ids()
    )

    print(
        f"Existing location files found: "
        f"{len(existing_ids)}"
    )

    locations_to_download = locations[
        ~locations["location_id"].astype(str).isin(
            existing_ids
        )
    ].copy()

    print(
        f"Locations remaining to download: "
        f"{len(locations_to_download)}"
    )

    if len(locations_to_download) == 0:
        print()
        print(
            "All requested locations are already "
            "downloaded."
        )

    # -----------------------------------------------------
    # Download missing locations in batches
    # -----------------------------------------------------

    total_batches = (
        len(locations_to_download)
        + BATCH_SIZE
        - 1
    ) // BATCH_SIZE

    for batch_number, start in enumerate(
        range(
            0,
            len(locations_to_download),
            BATCH_SIZE,
        ),
        start=1,
    ):

        batch = locations_to_download.iloc[
            start:start + BATCH_SIZE
        ]

        first_id = batch.iloc[0]["location_id"]
        last_id = batch.iloc[-1]["location_id"]

        print()
        print(
            f"Batch {batch_number}/"
            f"{total_batches}: "
            f"{first_id} -> {last_id}"
        )

        try:

            frames = fetch_batch(
                batch
            )

            for frame in frames:

                location_id = (
                    frame["location_id"]
                    .iloc[0]
                )

                output_file = (
                    OUTPUT_DIR
                    / f"weather_{location_id}.csv"
                )

                frame.to_csv(
                    output_file,
                    index=False,
                )

                print(
                    f"  Saved {location_id}: "
                    f"{len(frame):,} rows"
                )

            print(
                f"Batch {batch_number} completed."
            )

        except Exception as exc:

            print(
                f"ERROR in batch "
                f"{batch_number}: "
                f"{type(exc).__name__}: "
                f"{exc}"
            )

        time.sleep(
            REQUEST_DELAY
        )

    # -----------------------------------------------------
    # Rebuild combined dataset from ALL location files
    # -----------------------------------------------------

    print()
    print(
        "Reading all downloaded location datasets..."
    )

    all_frames = []

    for file in sorted(
        OUTPUT_DIR.glob("weather_*.csv")
    ):

        try:

            frame = pd.read_csv(
                file,
                parse_dates=["timestamp"],
            )

            all_frames.append(frame)

        except Exception as exc:

            print(
                f"ERROR reading {file}: "
                f"{type(exc).__name__}: {exc}"
            )

    if not all_frames:
        raise RuntimeError(
            "No weather data files found."
        )

    print(
        f"Combining "
        f"{len(all_frames)} "
        f"location datasets..."
    )

    combined = pd.concat(
        all_frames,
        ignore_index=True,
    )

    combined["timestamp"] = pd.to_datetime(
        combined["timestamp"],
        errors="coerce",
    )

    combined = combined.sort_values(
        [
            "timestamp",
            "location_id",
        ]
    )

    combined_file = (
        OUTPUT_DIR
        / "vietnam_weather_grid_500_hourly.csv"
    )

    combined.to_csv(
        combined_file,
        index=False,
    )

    # -----------------------------------------------------
    # Validate
    # -----------------------------------------------------

    validate_data(
        combined
    )

    print()
    print(
        "Combined dataset saved to:"
    )

    print(
        combined_file
    )


if __name__ == "__main__":
    main()