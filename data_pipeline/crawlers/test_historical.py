import time
from io import StringIO

import pandas as pd
import requests


BASE_URL = "http://203.209.181.170:2018/API_TTB/XUAT/solieu.php"

OUTPUT_FILE = "data/processed/station_553100_7days.csv"


def fetch_station_day(station_id, date, max_retries=3):
    """
    Fetch one day of hourly data for a station.

    If the API request fails, retry up to max_retries times.
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
            print(f"  Attempt {attempt}/{max_retries}")

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
                    f"No table returned for station "
                    f"{station_id} on {date}"
                )

            df = tables[0]

            # Standardize column names
            df = df.rename(
                columns={
                    "Ma Tram": "station_id",
                    "thoi gian": "timestamp",
                    "so lieu": "value",
                }
            )

            # Standardize data types
            df["station_id"] = df["station_id"].astype(str)

            df["timestamp"] = pd.to_datetime(
                df["timestamp"]
            )

            df["value"] = pd.to_numeric(
                df["value"],
                errors="coerce"
            )

            # Sort chronologically
            df = df.sort_values(
                "timestamp"
            ).reset_index(drop=True)

            print(
                f"  Successfully collected "
                f"{len(df)} records"
            )

            return df

        except Exception as e:

            print(
                f"  Attempt {attempt} failed: {e}"
            )

            if attempt < max_retries:
                print(
                    "  Waiting 5 seconds before retry..."
                )
                time.sleep(5)

    raise RuntimeError(
        f"Failed to collect station {station_id} "
        f"for {date} after {max_retries} attempts."
    )


def main():

    station_id = "553100"

    # Test one week of historical data
    dates = pd.date_range(
        start="2026-07-07",
        end="2026-07-13",
        freq="D"
    )

    all_data = []

    failed_dates = []

    # --------------------------------------------------
    # Collect daily data
    # --------------------------------------------------

    for date in dates:

        date_string = date.strftime("%Y-%m-%d")

        print(
            f"\nCollecting {station_id} - {date_string}"
        )

        try:

            df = fetch_station_day(
                station_id,
                date_string
            )

            all_data.append(df)

        except Exception as e:

            print(
                f"  FINAL FAILURE: {e}"
            )

            failed_dates.append(date_string)

    # --------------------------------------------------
    # Check whether anything was collected
    # --------------------------------------------------

    if not all_data:

        print("\nNo data collected.")
        return

    # --------------------------------------------------
    # Combine all successful days
    # --------------------------------------------------

    combined = pd.concat(
        all_data,
        ignore_index=True
    )

    combined = combined.sort_values(
        ["station_id", "timestamp"]
    ).reset_index(drop=True)

    # --------------------------------------------------
    # Dataset overview
    # --------------------------------------------------

    print("\n--- Historical Dataset ---")

    print(f"Rows: {len(combined)}")

    print(
        f"Start: {combined['timestamp'].min()}"
    )

    print(
        f"End:   {combined['timestamp'].max()}"
    )

    # --------------------------------------------------
    # Records per date
    # --------------------------------------------------

    print("\n--- Records by Date ---")

    records_by_date = (
        combined
        .groupby(combined["timestamp"].dt.date)
        .size()
    )

    print(records_by_date)

    # --------------------------------------------------
    # Missing values
    # --------------------------------------------------

    print("\n--- Missing Values ---")

    print(
        combined[
            ["station_id", "timestamp", "value"]
        ].isna().sum()
    )

    # --------------------------------------------------
    # Duplicate timestamps
    # --------------------------------------------------

    print("\n--- Duplicate Timestamps ---")

    duplicate_count = combined.duplicated(
        subset=[
            "station_id",
            "timestamp"
        ]
    ).sum()

    print(duplicate_count)

    # --------------------------------------------------
    # Failed dates
    # --------------------------------------------------

    print("\n--- Failed Dates ---")

    if failed_dates:
        for date in failed_dates:
            print(date)
    else:
        print("None")

    # --------------------------------------------------
    # First rows
    # --------------------------------------------------

    print("\n--- First 10 Rows ---")

    print(
        combined.head(10).to_string(index=False)
    )

    # --------------------------------------------------
    # Last rows
    # --------------------------------------------------

    print("\n--- Last 10 Rows ---")

    print(
        combined.tail(10).to_string(index=False)
    )

    # --------------------------------------------------
    # Save dataset
    # --------------------------------------------------

    combined.to_csv(
        OUTPUT_FILE,
        index=False
    )

    print(
        f"\nSaved historical data to: {OUTPUT_FILE}"
    )


if __name__ == "__main__":
    main()