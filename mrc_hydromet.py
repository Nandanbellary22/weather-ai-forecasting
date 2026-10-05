import os
import time

import pandas as pd
import requests


BASE_URL = "https://api.mrcmekong.org/api/v1/time-series/telemetry"

STATIONS_URL = (
    f"{BASE_URL}/recent/stations"
)

MEASUREMENT_URL = (
    f"{BASE_URL}/recent/measurement/{{station_id}}"
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

HISTORY_OUTPUT = os.path.join(
    OUTPUT_DIR,
    "mrc_vietnam_measurements.csv",
)

REQUEST_TIMEOUT = 30
REQUEST_DELAY_SECONDS = 0.5


def fetch_mrc_stations():
    """Fetch the current MRC telemetry station inventory."""

    response = requests.get(
        STATIONS_URL,
        timeout=REQUEST_TIMEOUT,
    )

    response.raise_for_status()

    data = response.json()

    if not isinstance(data, list):
        raise ValueError(
            "Unexpected MRC station response: "
            f"{type(data).__name__}"
        )

    print(
        f"MRC stations received: {len(data)}"
    )

    return data


def filter_vietnam_stations(data):
    """Keep all stations currently listed by MRC for Viet Nam."""

    vietnam = [
        station
        for station in data
        if station.get("country") == "Viet Nam"
    ]

    print(
        f"Vietnam stations found: {len(vietnam)}"
    )

    return vietnam


def station_has_recent_measurement(station):
    """
    Determine whether the MRC station currently exposes
    a recent measurement.

    The station inventory provides lastMeasurement for
    stations with active/recent telemetry.
    """

    last_measurement = station.get(
        "lastMeasurement"
    )

    return bool(last_measurement)


def build_station_dataframe(stations):
    """
    Build the complete Vietnam station metadata table.

    This contains all discovered Vietnam stations,
    including stations without currently available
    telemetry.
    """

    rows = []

    for station in stations:

        last_measurement = station.get(
            "lastMeasurement"
        )

        rows.append(
            {
                "station_id": station.get(
                    "stationId"
                ),
                "station_name": station.get(
                    "name"
                ),
                "latitude": station.get(
                    "latitude"
                ),
                "longitude": station.get(
                    "longitude"
                ),
                "river": station.get(
                    "river"
                ),
                "country": station.get(
                    "country"
                ),
                "station_type": station.get(
                    "stationType"
                ),

                # Current snapshot values
                "water_level": station.get(
                    "waterLevel"
                ),
                "rainfall": station.get(
                    "rainFall"
                ),
                "rainfall_1h": station.get(
                    "rainFall1H"
                ),
                "rainfall_6h": station.get(
                    "rainFall6H"
                ),
                "rainfall_12h": station.get(
                    "rainFall12H"
                ),
                "rainfall_24h": station.get(
                    "rainFall24H"
                ),
                "rainfall_7to7": station.get(
                    "rainFall7to7"
                ),

                # Flood/reference levels
                "flood_stage": station.get(
                    "floodStage"
                ),
                "alarm_stage": station.get(
                    "alarmStage"
                ),
                "mean_sea_level": station.get(
                    "meanSeaLevel"
                ),

                # Sensor availability
                "water_level_sensor": station.get(
                    "wlSensor"
                ),
                "rainfall_sensor": station.get(
                    "rainfallSensor"
                ),
                "temperature_sensor": station.get(
                    "tempSensor"
                ),
                "battery_sensor": station.get(
                    "batterySensor"
                ),
                "water_quality_sensors": station.get(
                    "wqSensors"
                ),
                "water_level_sensor_type": station.get(
                    "wlSensorType"
                ),

                # Operational status
                "success_rate": station.get(
                    "successRate"
                ),
                "last_status": station.get(
                    "lastStatus"
                ),
                "last_measurement": last_measurement,

                # Derived availability flag
                "telemetry_available": bool(
                    last_measurement
                ),
            }
        )

    return pd.DataFrame(rows)


def fetch_station_measurements(station_id):
    """
    Fetch the historical telemetry returned by MRC
    for one station.
    """

    url = MEASUREMENT_URL.format(
        station_id=station_id
    )

    response = requests.get(
        url,
        timeout=REQUEST_TIMEOUT,
    )

    response.raise_for_status()

    data = response.json()

    if not isinstance(data, dict):
        raise ValueError(
            "Unexpected response for station "
            f"{station_id}: "
            f"{type(data).__name__}"
        )

    measurements = data.get(
        "measurements",
        [],
    )

    if measurements is None:
        measurements = []

    if not isinstance(
        measurements,
        list,
    ):
        raise ValueError(
            "Unexpected measurements response "
            f"for station {station_id}"
        )

    rows = []

    for measurement in measurements:

        if not isinstance(
            measurement,
            dict,
        ):
            continue

        rows.append(
            {
                "station_id": str(
                    station_id
                ),
                "timestamp_utc": measurement.get(
                    "d"
                ),
                "water_level": measurement.get(
                    "w"
                ),
                "rainfall": measurement.get(
                    "r"
                ),
                "temperature": measurement.get(
                    "t"
                ),
                "battery": measurement.get(
                    "b"
                ),
            }
        )

    return rows


def collect_historical_measurements(stations):
    """
    Collect historical telemetry only from stations
    that currently report a lastMeasurement.

    All Vietnam stations remain in metadata, but
    inactive stations are not queried unnecessarily.
    """

    active_stations = [
        station
        for station in stations
        if station_has_recent_measurement(
            station
        )
    ]

    inactive_stations = [
        station
        for station in stations
        if not station_has_recent_measurement(
            station
        )
    ]

    print()
    print("=" * 70)
    print("MRC TELEMETRY COVERAGE")
    print("=" * 70)

    print(
        f"Vietnam stations          : {len(stations)}"
    )

    print(
        f"Stations with telemetry   : "
        f"{len(active_stations)}"
    )

    print(
        f"Stations without telemetry: "
        f"{len(inactive_stations)}"
    )

    if inactive_stations:

        print()
        print(
            "Stations without current telemetry:"
        )

        for station in inactive_stations:

            print(
                f"  {station.get('stationId')} - "
                f"{station.get('name')}"
            )

    all_rows = []

    print()
    print("=" * 70)
    print("MRC HISTORICAL MEASUREMENT COLLECTION")
    print("=" * 70)

    for index, station in enumerate(
        active_stations,
        start=1,
    ):

        station_id = station.get(
            "stationId"
        )

        station_name = station.get(
            "name"
        )

        print(
            f"[{index}/{len(active_stations)}] "
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
                    if row.get(
                        "timestamp_utc"
                    )
                ]

                print(
                    f"  Measurements : {len(rows)}"
                )

                if timestamps:

                    print(
                        f"  Oldest       : "
                        f"{min(timestamps)}"
                    )

                    print(
                        f"  Newest       : "
                        f"{max(timestamps)}"
                    )

            else:

                print(
                    "  Measurements : 0"
                )

        except requests.RequestException as exc:

            print(
                "  ERROR: request failed - "
                f"{exc}"
            )

        except Exception as exc:

            print(
                "  ERROR: "
                f"{type(exc).__name__}: {exc}"
            )

        time.sleep(
            REQUEST_DELAY_SECONDS
        )

    return pd.DataFrame(all_rows)


def clean_measurements(df):
    """Clean and normalize MRC telemetry observations."""

    if df.empty:

        return pd.DataFrame(
            columns=[
                "station_id",
                "timestamp",
                "timestamp_utc",
                "water_level",
                "rainfall",
                "temperature",
                "battery",
            ]
        )

    df = df.copy()

    # Preserve station IDs such as 019803.
    df["station_id"] = (
        df["station_id"]
        .astype(str)
        .str.strip()
        .str.zfill(6)
    )

    df["timestamp_utc"] = pd.to_datetime(
        df["timestamp_utc"],
        utc=True,
        errors="coerce",
    )

    # Remove observations without a usable timestamp.
    df = df.dropna(
        subset=[
            "station_id",
            "timestamp_utc",
        ]
    )

    # Convert UTC to Vietnam local time.
    df["timestamp"] = (
        df["timestamp_utc"]
        .dt.tz_convert(
            "Asia/Ho_Chi_Minh"
        )
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

    # One observation per station/timestamp.
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

    df = df.reset_index(
        drop=True
    )

    return df


def save_data(
    stations_df,
    measurements_df,
):
    """Save station metadata, history, and latest observations."""

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

    # Always create/update the latest file.
    if measurements_df.empty:

        latest = pd.DataFrame(
            columns=measurements_df.columns
        )

    else:

        latest = (
            measurements_df
            .sort_values(
                "timestamp_utc"
            )
            .groupby(
                "station_id",
                as_index=False,
            )
            .tail(1)
            .sort_values(
                "station_id"
            )
            .reset_index(
                drop=True
            )
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
    """Print a concise collection and data-quality summary."""

    print()
    print("=" * 70)
    print("MRC VIETNAM COLLECTION SUMMARY")
    print("=" * 70)

    total_stations = len(
        stations_df
    )

    active_stations = int(
        stations_df[
            "telemetry_available"
        ].fillna(False).sum()
    )

    stations_with_data = (
        measurements_df[
            "station_id"
        ].nunique()
        if not measurements_df.empty
        else 0
    )

    print(
        f"Vietnam stations       : "
        f"{total_stations}"
    )

    print(
        f"Telemetry stations     : "
        f"{active_stations}"
    )

    print(
        f"Stations with history  : "
        f"{stations_with_data}"
    )

    print(
        f"Historical measurements: "
        f"{len(measurements_df)}"
    )

    print(
        f"Stations without history: "
        f"{total_stations - stations_with_data}"
    )

    if measurements_df.empty:

        print()
        print(
            "No historical measurements collected."
        )

        print("=" * 70)

        return

    print()
    print("Measurements per station:")
    print("-" * 70)

    counts = (
        measurements_df
        .groupby("station_id")
        .size()
        .reset_index(
            name="measurements"
        )
        .sort_values(
            "station_id"
        )
    )

    print(
        counts.to_string(
            index=False
        )
    )

    print()
    print("Overall time range:")

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
        f"{measurements_df['water_level'].notna().sum()}"
        f" records"
    )

    print(
        f"  Rainfall    : "
        f"{measurements_df['rainfall'].notna().sum()}"
        f" records"
    )

    print(
        f"  Temperature : "
        f"{measurements_df['temperature'].notna().sum()}"
        f" records"
    )

    print(
        f"  Battery     : "
        f"{measurements_df['battery'].notna().sum()}"
        f" records"
    )

    print()
    print("Data quality:")

    duplicate_count = int(
        measurements_df.duplicated(
            subset=[
                "station_id",
                "timestamp_utc",
            ]
        ).sum()
    )

    print(
        f"  Duplicate station/timestamp rows: "
        f"{duplicate_count}"
    )

    print(
        f"  Missing water level: "
        f"{measurements_df['water_level'].isna().sum()}"
    )

    print(
        f"  Missing rainfall: "
        f"{measurements_df['rainfall'].isna().sum()}"
    )

    print(
        f"  Missing temperature: "
        f"{measurements_df['temperature'].isna().sum()}"
    )

    print(
        f"  Missing battery: "
        f"{measurements_df['battery'].isna().sum()}"
    )

    print("=" * 70)


def main():

    print("=" * 70)
    print("MRC MEKONG HYDROMET COLLECTOR")
    print("=" * 70)

    try:

        # --------------------------------------------------
        # 1. Get complete MRC station inventory
        # --------------------------------------------------

        data = fetch_mrc_stations()

        vietnam_stations = (
            filter_vietnam_stations(
                data
            )
        )

        if not vietnam_stations:

            raise ValueError(
                "No Vietnam stations found."
            )

        # --------------------------------------------------
        # 2. Build complete station metadata
        # --------------------------------------------------

        stations_df = (
            build_station_dataframe(
                vietnam_stations
            )
        )

        # --------------------------------------------------
        # 3. Collect history only from stations
        #    currently exposing telemetry
        # --------------------------------------------------

        measurements_df = (
            collect_historical_measurements(
                vietnam_stations
            )
        )

        # --------------------------------------------------
        # 4. Clean and normalize observations
        # --------------------------------------------------

        measurements_df = (
            clean_measurements(
                measurements_df
            )
        )

        # --------------------------------------------------
        # 5. Save outputs
        # --------------------------------------------------

        save_data(
            stations_df,
            measurements_df,
        )

        # --------------------------------------------------
        # 6. Print summary
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

        print(
            f"{type(exc).__name__}: {exc}"
        )


if __name__ == "__main__":
    main()