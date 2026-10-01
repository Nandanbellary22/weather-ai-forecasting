import os
import time

import pandas as pd
import requests


API_URL = (
    "https://api.mrcmekong.org/"
    "api/v1/time-series/telemetry/recent/stations"
)

OUTPUT_DIR = "data/processed"

STATIONS_OUTPUT = os.path.join(
    OUTPUT_DIR,
    "mrc_vietnam_stations.csv",
)

LATEST_OUTPUT = os.path.join(
    OUTPUT_DIR,
    "mrc_vietnam_latest.csv",
)


def fetch_mrc_stations():
    """Fetch latest station telemetry from the MRC API."""

    response = requests.get(
        API_URL,
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()

    if not isinstance(data, list):
        raise ValueError(
            f"Unexpected MRC response type: {type(data).__name__}"
        )

    print(f"MRC stations received: {len(data)}")

    return data


def filter_vietnam_stations(data):
    """Keep only stations located in Viet Nam."""

    vietnam = [
        station
        for station in data
        if station.get("country") == "Viet Nam"
    ]

    print(f"Vietnam stations found: {len(vietnam)}")

    return vietnam


def build_station_dataframe(stations):
    """Create normalized station metadata table."""

    rows = []

    for station in stations:
        rows.append(
            {
                "station_id": station.get("stationId"),
                "station_name": station.get("name"),
                "latitude": station.get("latitude"),
                "longitude": station.get("longitude"),
                "river": station.get("river"),
                "country": station.get("country"),
                "station_type": station.get("stationType"),
                "water_level": station.get("waterLevel"),
                "rainfall": station.get("rainFall"),
                "rainfall_1h": station.get("rainFall1H"),
                "rainfall_6h": station.get("rainFall6H"),
                "rainfall_12h": station.get("rainFall12H"),
                "rainfall_24h": station.get("rainFall24H"),
                "rainfall_7to7": station.get("rainFall7to7"),
                "water_level_sensor": station.get("wlSensor"),
                "rainfall_sensor": station.get("rainfallSensor"),
                "temperature_sensor": station.get("tempSensor"),
                "battery_sensor": station.get("batterySensor"),
                "water_quality_sensors": station.get("wqSensors"),
                "success_rate": station.get("successRate"),
                "last_status": station.get("lastStatus"),
                "last_measurement": station.get("lastMeasurement"),
            }
        )

    return pd.DataFrame(rows)


def save_data(df):
    """Save normalized MRC data."""

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    df.to_csv(
        LATEST_OUTPUT,
        index=False,
        encoding="utf-8-sig",
    )

    print(f"Saved latest data: {LATEST_OUTPUT}")

    metadata_columns = [
        "station_id",
        "station_name",
        "latitude",
        "longitude",
        "river",
        "country",
        "station_type",
        "water_level_sensor",
        "rainfall_sensor",
        "temperature_sensor",
        "battery_sensor",
        "water_quality_sensors",
    ]

    metadata = df[metadata_columns].copy()

    metadata.to_csv(
        STATIONS_OUTPUT,
        index=False,
        encoding="utf-8-sig",
    )

    print(f"Saved station metadata: {STATIONS_OUTPUT}")


def print_summary(df):
    """Print collection summary."""

    print()
    print("=" * 70)
    print("MRC VIETNAM HYDROMET SUMMARY")
    print("=" * 70)

    print(f"Vietnam stations : {len(df)}")

    water_level_count = df["water_level"].notna().sum()
    rainfall_count = df["rainfall"].notna().sum()

    print(f"Water level data : {water_level_count}")
    print(f"Rainfall data    : {rainfall_count}")

    print()
    print("Stations:")
    print("-" * 70)

    display_columns = [
        "station_id",
        "station_name",
        "river",
        "water_level",
        "rainfall",
        "last_status",
        "last_measurement",
    ]

    print(
        df[display_columns].to_string(
            index=False
        )
    )

    print("=" * 70)


def main():
    print("=" * 70)
    print("MRC MEKONG HYDROMET COLLECTOR")
    print("=" * 70)

    try:
        data = fetch_mrc_stations()

        vietnam_stations = filter_vietnam_stations(
            data
        )

        if not vietnam_stations:
            raise ValueError(
                "No Vietnam stations found."
            )

        df = build_station_dataframe(
            vietnam_stations
        )

        save_data(df)

        print_summary(df)

        print()
        print("MRC collection completed successfully.")

    except requests.RequestException as exc:
        print()
        print("MRC API request failed:")
        print(exc)

    except Exception as exc:
        print()
        print("MRC collection failed:")
        print(type(exc).__name__)
        print(exc)


if __name__ == "__main__":
    main()