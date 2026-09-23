import time
from datetime import datetime, timedelta

import pandas as pd
import requests
from io import StringIO


BASE_URL = "http://203.209.181.170:2018/API_TTB/XUAT/solieu.php"

STATIONS = ["553100", "553300"]

START_DATE = "2026-04-15"
END_DATE = "2026-07-13"

MAX_RETRIES = 3
TIMEOUT = 30
RETRY_DELAY = 5


def fetch_station_day(station_id, date):
    start_time = f"{date} 00:00"
    end_time = f"{date} 23:59"

    params = {
        "matram": station_id,
        "ten_table": "mucnuoc_oday",
        "sophut": "60",
        "tinhtong": "0",
        "thoigianbd": f"'{start_time}'",
        "thoigiankt": f"'{end_time}'",
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(
                f"{station_id} | {date} | "
                f"attempt {attempt}"
            )

            response = requests.get(
                BASE_URL,
                params=params,
                timeout=TIMEOUT
            )

            response.raise_for_status()

            tables = pd.read_html(
                StringIO(response.text)
            )

            if not tables:
                raise ValueError("No table found")

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
                df["timestamp"],
                errors="coerce"
            )

            df["value"] = pd.to_numeric(
                df["value"],
                errors="coerce"
            )

            df = df.sort_values(
                "timestamp"
            ).reset_index(drop=True)

            return df

        except Exception as e:
            print(
                f"  Failed: {e}"
            )

            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)

    return None


def generate_dates(start_date, end_date):
    start = datetime.strptime(
        start_date,
        "%Y-%m-%d"
    )

    end = datetime.strptime(
        end_date,
        "%Y-%m-%d"
    )

    current = start

    while current <= end:
        yield current.strftime("%Y-%m-%d")
        current += timedelta(days=1)


def collect_station(station_id):
    all_data = []
    failed_dates = []

    dates = list(
        generate_dates(
            START_DATE,
            END_DATE
        )
    )

    print("\n" + "=" * 60)
    print(f"COLLECTING STATION {station_id}")
    print(f"Dates: {START_DATE} → {END_DATE}")
    print(f"Total days: {len(dates)}")
    print("=" * 60)

    for date in dates:

        df = fetch_station_day(
            station_id,
            date
        )

        if df is not None and len(df) > 0:
            all_data.append(df)

            print(
                f"  SUCCESS: {len(df)} rows"
            )
        else:
            failed_dates.append(date)

            print(
                f"  FAILED: {date}"
            )

    if not all_data:
        print(
            f"\nNo data collected for {station_id}"
        )
        return

    result = pd.concat(
        all_data,
        ignore_index=True
    )

    result = result.sort_values(
        "timestamp"
    ).reset_index(drop=True)

    # Basic validation
    duplicate_count = result.duplicated(
        subset=["station_id", "timestamp"]
    ).sum()

    missing_values = result[
        ["station_id", "timestamp", "value"]
    ].isna().sum().sum()

    print("\n" + "-" * 60)
    print(f"SUMMARY — STATION {station_id}")
    print("-" * 60)

    print(f"Rows: {len(result)}")
    print(f"Expected maximum rows: {len(dates) * 24}")
    print(f"Start: {result['timestamp'].min()}")
    print(f"End: {result['timestamp'].max()}")
    print(f"Missing values: {missing_values}")
    print(
        f"Duplicate station/timestamps: "
        f"{duplicate_count}"
    )

    print(
        f"Failed dates: {len(failed_dates)}"
    )

    if failed_dates:
        print("Failed date list:")
        for date in failed_dates:
            print(f"  {date}")

    output_path = (
        f"data/processed/"
        f"station_{station_id}_90days.csv"
    )

    result.to_csv(
        output_path,
        index=False
    )

    print(
        f"\nSaved: {output_path}"
    )


def main():
    for station_id in STATIONS:
        collect_station(station_id)


if __name__ == "__main__":
    main()