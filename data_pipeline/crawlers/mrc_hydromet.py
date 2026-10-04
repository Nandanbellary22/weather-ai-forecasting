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
    """Create complete Vietnam station metadata dataframe."""

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

                # Current snapshot measurements
                "water_level": station.get("waterLevel"),
                "rainfall": station.get("rainFall"),
                "rainfall_1h": station.get("rainFall1H"),
                "rainfall_6h": station.get("rainFall6H"),
                "rainfall_12h": station.get("rainFall12H"),
                "rainfall_24h": station.get("rainFall24H"),
                "rainfall_7to7": station.get("rainFall7to7"),

                # Hydrological thresholds
                "flood_stage": station.get("floodStage"),
                "alarm_stage": station.get("alarmStage"),
                "mean_sea_level": station.get("meanSeaLevel"),

                # Sensor information
                "water_level_sensor": station.get("wlSensor"),
                "rainfall_sensor": station.get("rainfallSensor"),
                "temperature_sensor": station.get("tempSensor"),
                "battery_sensor": station.get("batterySensor"),
                "water_quality_sensors": station.get("wqSensors"),
                "water_level_sensor_type": station.get("wlSensorType"),

                # Station status
                "success_rate": station.get("successRate"),
                "last_status": station.get("lastStatus"),
                "last_measurement": station.get("lastMeasurement"),
                "telemetry_available": bool(
                    station.get("lastMeasurement")
                ),
            }
        )

    return pd.DataFrame(rows)


def build_latest_snapshot_dataframe(stations):
    """
    Build a current MRC snapshot.

    This is intentionally separate from historical measurements.
    The rainfall accumulation fields are current snapshot values
    and must not be treated as historical time-series values.
    """

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

                # Current hydrometeorological values
                "water_level": station.get("waterLevel"),
                "rainfall": station.get("rainFall"),
                "rainfall_1h": station.get("rainFall1H"),
                "rainfall_6h": station.get("rainFall6H"),
                "rainfall_12h": station.get("rainFall12H"),
                "rainfall_24h": station.get("rainFall24H"),
                "rainfall_7to7": station.get("rainFall7to7"),

                # Flood / alarm thresholds
                "flood_stage": station.get("floodStage"),
                "alarm_stage": station.get("alarmStage"),
                "mean_sea_level": station.get("meanSeaLevel"),

                # Sensors
                "water_level_sensor": station.get("wlSensor"),
                "rainfall_sensor": station.get("rainfallSensor"),
                "temperature_sensor": station.get("tempSensor"),
                "battery_sensor": station.get("batterySensor"),
                "water_quality_sensors": station.get("wqSensors"),
                "water_level_sensor_type": station.get("wlSensorType"),

                # Status
                "success_rate": station.get("successRate"),
                "last_status": station.get("lastStatus"),
                "last_measurement": station.get("lastMeasurement"),
                "telemetry_available": bool(
                    station.get("lastMeasurement")
                ),
            }
        )

    df = pd.DataFrame(rows)

    if not df.empty:

        numeric_columns = [
            "latitude",
            "longitude",
            "water_level",
            "rainfall",
            "rainfall_1h",
            "rainfall_6h",
            "rainfall_12h",
            "rainfall_24h",
            "rainfall_7to7",
            "flood_stage",
            "alarm_stage",
            "mean_sea_level",
            "success_rate",
        ]

        for column in numeric_columns:
            df[column] = pd.to_numeric(
                df[column],
                errors="coerce",
            )

        df = df.sort_values(
            "station_id"
        ).reset_index(drop=True)

    return df


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
    """
    Collect historical measurements only from stations that
    currently expose telemetry.

    Stations without a lastMeasurement are retained in metadata
    but are not repeatedly queried for historical measurements.
    """

    all_rows = []

    telemetry_stations = [
        station
        for station in stations
        if station.get("lastMeasurement")
    ]

    print()
    print("=" * 70)
    print("MRC HISTORICAL MEASUREMENT COLLECTION")
    print("=" * 70)

    print(
        f"Stations with telemetry: "
        f"{len(telemetry_stations)}"
    )

    print(
        f"Stations without telemetry: "
        f"{len(stations) - len(telemetry_stations)}"
    )

    print()

    for index, station in enumerate(
        telemetry_stations,
        start=1,
    ):

        station_id = station.get("stationId")
        station_name = station.get("name")

        print(
            f"[{index}/{len(telemetry_stations)}] "
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

                if timestamps:

                    print(
                        f"  Oldest       : {min(timestamps)}"
                    )

                    print(
                        f"  Newest       : {max(timestamps)}"
                    )

            else:

                print(
                    "  Measurements : 0"
                )

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
    """Clean and normalize MRC historical measurements."""

    if df.empty:
        return df

    df["timestamp_utc"] = pd.to_datetime(
        df["timestamp_utc"],
        utc=True,
        errors="coerce",
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

    df = df.dropna(
        subset=[
            "station_id",
            "timestamp_utc",
        ]
    )

    df = df.drop_duplicates(
        subset=[
            "station_id",
            "timestamp_utc",
        ],
        keep="last",
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
    latest_df,
    measurements_df,
):
    """Save station metadata, current snapshot and historical data."""

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

    latest_df.to_csv(
        LATEST_OUTPUT,
        index=False,
        encoding="utf-8-sig",
    )

    print(
        f"Saved current snapshot: "
        f"{LATEST_OUTPUT}"
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


def print_summary(
    stations_df,
    latest_df,
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

    telemetry_count = int(
        stations_df["telemetry_available"].sum()
    )

    print(
        f"Stations with telemetry: "
        f"{telemetry_count}"
    )

    print(
        f"Stations without data  : "
        f"{len(stations_df) - telemetry_count}"
    )

    print(
        f"Historical measurements: "
        f"{len(measurements_df)}"
    )

    print(
        f"Current snapshots      : "
        f"{len(latest_df)}"
    )

    print()

    if not measurements_df.empty:

        print(
            f"Historical stations    : "
            f"{measurements_df['station_id'].nunique()}"
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

        print("Overall historical time range:")

        print(
            f"  Oldest: "
            f"{measurements_df['timestamp_utc'].min()}"
        )

        print(
            f"  Newest: "
            f"{measurements_df['timestamp_utc'].max()}"
        )

        print()

        print("Historical variables:")

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

    print()

    if not latest_df.empty:

        print("Current snapshot variables:")

        snapshot_columns = [
            "water_level",
            "rainfall",
            "rainfall_1h",
            "rainfall_6h",
            "rainfall_12h",
            "rainfall_24h",
            "rainfall_7to7",
        ]

        for column in snapshot_columns:

            if column in latest_df.columns:

                available = int(
                    latest_df[column].notna().sum()
                )

                print(
                    f"  {column:<14}: "
                    f"{available}/{len(latest_df)} stations"
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

        # --------------------------------------------------
        # 2. Build station metadata
        # --------------------------------------------------

        stations_df = build_station_dataframe(
            vietnam_stations
        )

        # --------------------------------------------------
        # 3. Build current snapshot
        # --------------------------------------------------

        latest_df = build_latest_snapshot_dataframe(
            vietnam_stations
        )

        # --------------------------------------------------
        # 4. Collect historical measurements
        # --------------------------------------------------

        measurements_df = (
            collect_historical_measurements(
                vietnam_stations
            )
        )

        # --------------------------------------------------
        # 5. Clean historical data
        # --------------------------------------------------

        measurements_df = clean_measurements(
            measurements_df
        )

        # --------------------------------------------------
        # 6. Save
        # --------------------------------------------------

        save_data(
            stations_df,
            latest_df,
            measurements_df,
        )

        # --------------------------------------------------
        # 7. Summary
        # --------------------------------------------------

        print_summary(
            stations_df,
            latest_df,
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