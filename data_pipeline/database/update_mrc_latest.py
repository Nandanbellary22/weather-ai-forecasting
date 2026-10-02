import os
import requests
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values


MRC_STATIONS_URL = (
    "https://api.mrcmekong.org/api/v1/time-series/telemetry/recent/stations"
)

MRC_MEASUREMENT_URL = (
    "https://api.mrcmekong.org/api/v1/time-series/telemetry/"
    "recent/measurement/{station_id}"
)


def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("PGHOST", "localhost"),
        port=os.getenv("PGPORT", "5432"),
        database=os.getenv("PGDATABASE", "weather_forecasting"),
        user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD"),
    )


def fetch_vietnam_stations():
    response = requests.get(
        MRC_STATIONS_URL,
        timeout=30,
    )
    response.raise_for_status()

    data = response.json()

    if not isinstance(data, list):
        raise ValueError(
            "Unexpected MRC station response."
        )

    stations = [
        station
        for station in data
        if station.get("country") == "Viet Nam"
    ]

    return stations


def fetch_station_measurements(station_id):
    url = MRC_MEASUREMENT_URL.format(
        station_id=station_id
    )

    response = requests.get(
        url,
        timeout=30,
    )
    response.raise_for_status()

    data = response.json()

    measurements = data.get(
        "measurements",
        []
    )

    rows = []

    for measurement in measurements:
        rows.append(
            {
                "station_id": str(station_id),
                "timestamp_utc": measurement.get("d"),
                "water_level": measurement.get("w"),
                "rainfall": measurement.get("r"),
                "temperature": measurement.get("t"),
                "battery": measurement.get("b"),
            }
        )

    return rows


def collect_latest_measurements(stations):
    all_rows = []

    print()
    print("=" * 70)
    print("MRC LATEST DATA COLLECTION")
    print("=" * 70)

    for index, station in enumerate(
        stations,
        start=1,
    ):
        station_id = str(
            station.get("stationId")
        )

        station_name = station.get(
            "name"
        )

        print(
            f"[{index}/{len(stations)}] "
            f"{station_id} - {station_name}"
        )

        try:
            rows = fetch_station_measurements(
                station_id
            )

            all_rows.extend(rows)

            print(
                f"  Records fetched: {len(rows)}"
            )

            if rows:
                timestamps = [
                    row["timestamp_utc"]
                    for row in rows
                    if row["timestamp_utc"]
                ]

                print(
                    f"  Oldest: {min(timestamps)}"
                )

                print(
                    f"  Newest: {max(timestamps)}"
                )

        except requests.RequestException as exc:
            print(
                f"  ERROR: {exc}"
            )

        except Exception as exc:
            print(
                f"  ERROR: "
                f"{type(exc).__name__}: {exc}"
            )

    return pd.DataFrame(
        all_rows
    )


def clean_measurements(df):
    if df.empty:
        return df

    df["station_id"] = (
        df["station_id"]
        .astype(str)
    )

    df["timestamp_utc"] = pd.to_datetime(
        df["timestamp_utc"],
        utc=True,
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
        ]
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


def get_existing_keys(conn):
    query = """
        SELECT
            station_id,
            timestamp_utc
        FROM mrc_hydromet_observations
    """

    with conn.cursor() as cursor:
        cursor.execute(query)

        rows = cursor.fetchall()

    return {
        (
            str(station_id),
            pd.Timestamp(timestamp_utc),
        )
        for station_id, timestamp_utc in rows
    }


def insert_new_records(conn, df):
    if df.empty:
        return 0

    existing_keys = get_existing_keys(
        conn
    )

    print()
    print(
        f"Existing database records: "
        f"{len(existing_keys)}"
    )

    new_rows = []

    for row in df.itertuples(
        index=False
    ):
        key = (
            str(row.station_id),
            pd.Timestamp(
                row.timestamp_utc
            ),
        )

        if key in existing_keys:
            continue

        timestamp_utc = pd.Timestamp(
            row.timestamp_utc
        )

        # Convert UTC to Vietnam local time.
        timestamp_local = (
            timestamp_utc.tz_convert(
                "Asia/Ho_Chi_Minh"
            )
        )

        new_rows.append(
            (
                str(row.station_id),

                # Required local timestamp
                timestamp_local.to_pydatetime(),

                # Original UTC timestamp
                timestamp_utc.to_pydatetime(),

                (
                    float(row.water_level)
                    if pd.notna(
                        row.water_level
                    )
                    else None
                ),

                (
                    float(row.rainfall)
                    if pd.notna(
                        row.rainfall
                    )
                    else None
                ),

                (
                    float(row.temperature)
                    if pd.notna(
                        row.temperature
                    )
                    else None
                ),

                (
                    float(row.battery)
                    if pd.notna(
                        row.battery
                    )
                    else None
                ),
            )
        )

    if not new_rows:
        return 0

    insert_query = """
        INSERT INTO mrc_hydromet_observations (
            station_id,
            timestamp,
            timestamp_utc,
            water_level,
            rainfall,
            temperature,
            battery
        )
        VALUES %s
        ON CONFLICT (
            station_id,
            timestamp_utc
        )
        DO NOTHING
    """

    with conn.cursor() as cursor:
        execute_values(
            cursor,
            insert_query,
            new_rows,
        )

    conn.commit()

    return len(new_rows)


def print_latest_database_state(conn):
    query = """
        SELECT
            COUNT(*) AS total_records,
            COUNT(DISTINCT station_id) AS stations,
            MIN(timestamp_utc) AS oldest,
            MAX(timestamp_utc) AS newest
        FROM mrc_hydromet_observations
    """

    with conn.cursor() as cursor:
        cursor.execute(query)

        result = cursor.fetchone()

    print()
    print("=" * 70)
    print("MRC DATABASE STATUS")
    print("=" * 70)

    print(
        f"Total records : {result[0]}"
    )

    print(
        f"Stations      : {result[1]}"
    )

    print(
        f"Oldest        : {result[2]}"
    )

    print(
        f"Newest        : {result[3]}"
    )

    print("=" * 70)


def main():
    print("=" * 70)
    print("MRC INCREMENTAL DATABASE UPDATE")
    print("=" * 70)

    try:
        stations = fetch_vietnam_stations()

        print(
            f"Vietnam MRC stations found: "
            f"{len(stations)}"
        )

        df = collect_latest_measurements(
            stations
        )

        df = clean_measurements(
            df
        )

        print()
        print(
            f"Clean records fetched: "
            f"{len(df)}"
        )

        conn = get_db_connection()

        try:
            new_records = insert_new_records(
                conn,
                df,
            )

            print()
            print("=" * 70)
            print("UPDATE RESULT")
            print("=" * 70)

            print(
                f"New records inserted: "
                f"{new_records}"
            )

            print(
                f"Existing/duplicate records skipped: "
                f"{len(df) - new_records}"
            )

            print_latest_database_state(
                conn
            )

        finally:
            conn.close()

        print()
        print(
            "MRC incremental update "
            "completed successfully."
        )

    except Exception as exc:
        print()
        print(
            "MRC incremental update failed:"
        )

        print(
            type(exc).__name__
        )

        print(exc)


if __name__ == "__main__":
    main()