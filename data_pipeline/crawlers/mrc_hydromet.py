import os
import time

import pandas as pd
import requests


BASE_URL = "https://api.mrcmekong.org/api/v1/time-series/telemetry"
STATIONS_URL = f"{BASE_URL}/recent/stations"
MEASUREMENT_URL = f"{BASE_URL}/recent/measurement/{{station_id}}"

OUTPUT_DIR = "data/processed"

STATIONS_OUTPUT = os.path.join(
    OUTPUT_DIR,
    "mrc_vietnam_stations.csv",
)

LATEST_OUTPUT = os.path.join(
    OUTPUT_DIR,
    "mrc_vietnam_latest.csv",
)

HISTORY_OUTPUT = os.path.join(
    OUTPUT_DIR,
    "mrc_vietnam_measurements.csv",
)


def fetch_mrc_stations():
    """Fetch all stations currently available from MRC."""

    response = requests.get(
        STATIONS_URL,
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()

    if not isinstance(data, list):
        raise ValueError(
            f"Unexpected MRC station response: {type(data).__name__}"
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
    """Create station metadata dataframe."""

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


def fetch_station_measurements(station_id):
    """Fetch recent historical measurements for one station."""

    url = MEASUREMENT_URL.format(
        station_id=station_id
    )

    response = requests.get(
        url,
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()

    if not isinstance(data, dict):
        raise ValueError(
            f"Unexpected response for station {station_id}"
        )

    measurements = data.get("measurements", [])

    rows = []

    for measurement in measurements:

        rows.append(
            {
                "station_id": station_id,
                "timestamp_utc": measurement.get("d"),
                "water_level": measurement.get("w"),
                "rainfall": measurement.get("r"),
                "temperature": measurement.get("t"),
                "battery": measurement.get("b"),
            }
        )

    return rows


def collect_historical_measurements(stations):
    """Collect recent measurements from every Vietnam station."""

    all_rows = []

    print()
    print("=" * 70)
    print("MRC HISTORICAL MEASUREMENT COLLECTION")
    print("=" * 70)

    for index, station in enumerate(stations, start=1):

        station_id = station.get("stationId")
        station_name = station.get("name")

        print(
            f"[{index}/{len(stations)}] "
            f"{station_id} - {station_name}"
        )

        try:

            rows = fetch_station_measurements(
                station_id
            )

            all_rows.extend(rows)

            if rows:

                timestamps = [
                    row["timestamp_utc"]
                    for row in rows
                    if row["timestamp_utc"]
                ]

                print(
                    f"  Measurements : {len(rows)}"
                )

                print(
                    f"  Oldest       : {min(timestamps)}"
                )

                print(
                    f"  Newest       : {max(timestamps)}"
                )

            else:

                print("  Measurements : 0")

        except requests.RequestException as exc:

            print(
                f"  ERROR: request failed - {exc}"
            )

        except Exception as exc:

            print(
                f"  ERROR: {type(exc).__name__}: {exc}"
            )

        # Small delay so we do not hit the API too aggressively.
        time.sleep(0.5)

    return pd.DataFrame(all_rows)


def clean_measurements(df):
    """Clean and normalize MRC measurements."""

    if df.empty:
        return df

    df["timestamp_utc"] = pd.to_datetime(
        df["timestamp_utc"],
        utc=True,
    )

    # Convert UTC to Vietnam local time.
    df["timestamp"] = (
        df["timestamp_utc"]
        .dt.tz_convert("Asia/Ho_Chi_Minh")
    )

    numeric_columns = [
        "water_level",
        "rainfall",
        "temperature",
        "battery",
    ]

    for column in numeric_columns:

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    df = df[
        [
            "station_id",
            "timestamp",
            "timestamp_utc",
            "water_level",
            "rainfall",
            "temperature",
            "battery",
        ]
    ]

    df = df.drop_duplicates(
        subset=[
            "station_id",
            "timestamp_utc",
        ]
    )

    df = df.sort_values(
        [
            "station_id",
            "timestamp_utc",
        ]
    )

    df = df.reset_index(drop=True)

    return df


def save_data(
    stations_df,
    measurements_df,
):
    """Save MRC station metadata and historical measurements."""

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True,
    )

    stations_df.to_csv(
        STATIONS_OUTPUT,
        index=False,
        encoding="utf-8-sig",
    )

    print()
    print(
        f"Saved station metadata: "
        f"{STATIONS_OUTPUT}"
    )

    measurements_df.to_csv(
        HISTORY_OUTPUT,
        index=False,
        encoding="utf-8-sig",
    )

    print(
        f"Saved historical measurements: "
        f"{HISTORY_OUTPUT}"
    )

    # Save latest observation for each station.
    if not measurements_df.empty:

        latest = (
            measurements_df
            .sort_values("timestamp_utc")
            .groupby("station_id", as_index=False)
            .tail(1)
            .sort_values("station_id")
        )

        latest.to_csv(
            LATEST_OUTPUT,
            index=False,
            encoding="utf-8-sig",
        )

        print(
            f"Saved latest measurements: "
            f"{LATEST_OUTPUT}"
        )


def print_summary(
    stations_df,
    measurements_df,
):
    """Print collection summary."""

    print()
    print("=" * 70)
    print("MRC VIETNAM COLLECTION SUMMARY")
    print("=" * 70)

    print(
        f"Vietnam stations       : "
        f"{len(stations_df)}"
    )

    print(
        f"Historical measurements: "
        f"{len(measurements_df)}"
    )

    if not measurements_df.empty:

        print()

        print(
            f"Stations with data     : "
            f"{measurements_df['station_id'].nunique()}"
        )

        print(
            f"Stations without data  : "
            f"{len(stations_df) - measurements_df['station_id'].nunique()}"
        )

        print()

        print("Measurements per station:")
        print("-" * 70)

        counts = (
            measurements_df
            .groupby("station_id")
            .size()
            .reset_index(name="measurements")
            .sort_values("station_id")
        )

        print(
            counts.to_string(index=False)
        )

        print()

        print(
            "Overall time range:"
        )

        print(
            f"  Oldest: "
            f"{measurements_df['timestamp_utc'].min()}"
        )

        print(
            f"  Newest: "
            f"{measurements_df['timestamp_utc'].max()}"
        )

        print()

        print("Available variables:")

        print(
            f"  Water level : "
            f"{measurements_df['water_level'].notna().sum()} records"
        )

        print(
            f"  Rainfall    : "
            f"{measurements_df['rainfall'].notna().sum()} records"
        )

        print(
            f"  Temperature : "
            f"{measurements_df['temperature'].notna().sum()} records"
        )

        print(
            f"  Battery     : "
            f"{measurements_df['battery'].notna().sum()} records"
        )

    print("=" * 70)


def main():

    print("=" * 70)
    print("MRC MEKONG HYDROMET COLLECTOR")
    print("=" * 70)

    try:

        # --------------------------------------------------
        # 1. Get station list
        # --------------------------------------------------

        data = fetch_mrc_stations()

        vietnam_stations = filter_vietnam_stations(
            data
        )

        if not vietnam_stations:

            raise ValueError(
                "No Vietnam stations found."
            )

        stations_df = build_station_dataframe(
            vietnam_stations
        )

        # --------------------------------------------------
        # 2. Collect recent historical measurements
        # --------------------------------------------------

        measurements_df = (
            collect_historical_measurements(
                vietnam_stations
            )
        )

        # --------------------------------------------------
        # 3. Clean data
        # --------------------------------------------------

        measurements_df = clean_measurements(
            measurements_df
        )

        # --------------------------------------------------
        # 4. Save
        # --------------------------------------------------

        save_data(
            stations_df,
            measurements_df,
        )

        # --------------------------------------------------
        # 5. Summary
        # --------------------------------------------------

        print_summary(
            stations_df,
            measurements_df,
        )

        print()
        print(
            "MRC collection completed successfully."
        )

    except requests.RequestException as exc:

        print()
        print(
            "MRC API request failed:"
        )

        print(exc)

    except Exception as exc:

        print()
        print(
            "MRC collection failed:"
        )

        print(type(exc).__name__)

        print(exc)


if __name__ == "__main__":
    main()