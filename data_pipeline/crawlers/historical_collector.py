import time
from io import StringIO

import pandas as pd
import requests


BASE_URL = "http://203.209.181.170:2018/API_TTB/XUAT/solieu.php"

OUTPUT_DIR = "data/processed"

STATIONS = ["553100", "553300"]

START_DATE = "2026-06-14"
END_DATE = "2026-07-13"


def fetch_station_day(station_id, date, max_retries=3):
    """
    Fetch one day of hourly data for one station.
    """

    start_time = f"{date} 00:00"
    end_time = f"{date} 23:59"

    params = {
        "matram": station_id,
        "ten_table": "mucnuoc_oday",
        "sophut": 60,
        "tinhtong": 0,
        "thoigianbd": f"'{start_time}'",
        "thoigiankt": f"'{end_time}'",
    }

    for attempt in range(1, max_retries + 1):

        try:
            print(f"    Attempt {attempt}/{max_retries}")

            response = requests.get(
                BASE_URL,
                params=params,
                timeout=30
            )

            response.raise_for_status()

            tables = pd.read_html(
                StringIO(response.text)
            )

            if not tables:
                raise ValueError(
                    f"No table returned for station {station_id} on {date}"
                )

            df = tables[0]

            df = df.rename(
                columns={
                    "Ma Tram": "station_id",
                    "thoi gian": "timestamp",
                    "so lieu": "value",
                }
            )

            df["station_id"] = df["station_id"].astype(str)

            df["timestamp"] = pd.to_datetime(
                df["timestamp"]
            )

            df["value"] = pd.to_numeric(
                df["value"],
                errors="coerce"
            )

            df = (
                df
                .sort_values("timestamp")
                .reset_index(drop=True)
            )

            print(
                f"    Successfully collected {len(df)} records"
            )

            return df

        except Exception as e:

            print(
                f"    Attempt {attempt} failed: {e}"
            )

            if attempt < max_retries:
                print(
                    "    Waiting 5 seconds before retry..."
                )
                time.sleep(5)

    raise RuntimeError(
        f"Failed to collect station {station_id} "
        f"for {date} after {max_retries} attempts."
    )


def collect_station(station_id, start_date, end_date):

    dates = pd.date_range(
        start=start_date,
        end=end_date,
        freq="D"
    )

    all_data = []
    failed_dates = []

    print()
    print("=" * 60)
    print(f"COLLECTING STATION {station_id}")
    print(f"Period: {start_date} -> {end_date}")
    print("=" * 60)

    for date in dates:

        date_string = date.strftime("%Y-%m-%d")

        print(
            f"\n  Collecting {station_id} - {date_string}"
        )

        try:

            df = fetch_station_day(
                station_id,
                date_string
            )

            all_data.append(df)

        except Exception as e:

            print(
                f"    FINAL FAILURE: {e}"
            )

            failed_dates.append(date_string)

    if not all_data:
        print(
            f"\nNo data collected for station {station_id}."
        )
        return None

    combined = pd.concat(
        all_data,
        ignore_index=True
    )

    combined = (
        combined
        .sort_values(
            ["station_id", "timestamp"]
        )
        .reset_index(drop=True)
    )

    print()
    print("--- Station Summary ---")
    print(f"Station: {station_id}")
    print(f"Rows: {len(combined)}")
    print(
        f"Start: {combined['timestamp'].min()}"
    )
    print(
        f"End:   {combined['timestamp'].max()}"
    )

    print()
    print("--- Records by Date ---")

    records_by_date = (
        combined
        .groupby(combined["timestamp"].dt.date)
        .size()
    )

    print(records_by_date)

    print()
    print("--- Missing Values ---")

    print(
        combined[
            ["station_id", "timestamp", "value"]
        ].isna().sum()
    )

    print()
    print("--- Duplicate Station/Timestamps ---")

    duplicate_count = combined.duplicated(
        subset=["station_id", "timestamp"]
    ).sum()

    print(duplicate_count)

    print()
    print("--- Failed Dates ---")

    if failed_dates:

        for date in failed_dates:
            print(date)

    else:

        print("None")

    output_file = (
        f"{OUTPUT_DIR}/station_{station_id}_30days.csv"
    )

    combined.to_csv(
        output_file,
        index=False
    )

    print()
    print(
        f"Saved: {output_file}"
    )

    return combined


def main():

    for station_id in STATIONS:

        collect_station(
            station_id,
            START_DATE,
            END_DATE
        )

        print()


if __name__ == "__main__":
    main()