from pathlib import Path
from datetime import date, timedelta

import pandas as pd

from data_pipeline.crawlers.hydrology_api import fetch_station_data


STATION_IDS = [
    "553000",
    "553100",
    "553200",
    "553300",
    "553400",
]

DAYS = 180

OUTPUT_DIR = Path("data/processed")
OUTPUT_FILE = OUTPUT_DIR / "historical_180days_all_stations.csv"


def collect_station(
    station_id: str,
    start_date: date,
    end_date: date,
) -> pd.DataFrame:

    records = []
    failed_dates = []

    current_date = start_date

    while current_date <= end_date:

        date_str = current_date.isoformat()

        start_time = f"{date_str} 00:00"
        end_time = f"{date_str} 23:59"

        print(f"{station_id} | {date_str}")

        try:
            df = fetch_station_data(
                station_id=station_id,
                start_time=start_time,
                end_time=end_time,
            )

            if df is not None and not df.empty:

                df["station_id"] = station_id

                records.append(df)

            else:

                print(f"  NO DATA: {station_id} {date_str}")
                failed_dates.append(date_str)

        except Exception as exc:

            print(
                f"  ERROR: {station_id} {date_str} -> {exc}"
            )

            failed_dates.append(date_str)

        current_date += timedelta(days=1)

    if records:

        result = pd.concat(
            records,
            ignore_index=True,
        )

    else:

        result = pd.DataFrame()

    print()
    print(f"Station {station_id} summary")
    print(f"Rows collected: {len(result)}")
    print(f"Failed dates: {len(failed_dates)}")

    if failed_dates:

        print("Failed dates:")

        for failed_date in failed_dates:
            print(f"  {failed_date}")

    return result


def validate_dataset(df: pd.DataFrame) -> None:

    print()
    print("=" * 60)
    print("FINAL DATASET VALIDATION")
    print("=" * 60)

    if df.empty:

        print("Dataset is empty.")
        return

    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        errors="coerce",
    )

    df["value"] = pd.to_numeric(
        df["value"],
        errors="coerce",
    )

    print(f"Rows: {len(df)}")
    print(f"Stations: {df['station_id'].nunique()}")
    print(f"Start: {df['timestamp'].min()}")
    print(f"End: {df['timestamp'].max()}")

    print()
    print("Rows by station:")

    print(
        df.groupby("station_id").size()
    )

    print()
    print("Missing values:")

    print(
        df.isna().sum()
    )

    print()
    print("Duplicate station/timestamp rows:")

    duplicate_count = df.duplicated(
        subset=[
            "station_id",
            "timestamp",
        ]
    ).sum()

    print(duplicate_count)

    print()
    print("Days available per station:")

    days_per_station = (
        df.assign(
            date=df["timestamp"].dt.date
        )
        .groupby("station_id")["date"]
        .nunique()
    )

    print(days_per_station)

    print()
    print("Rows per station per day:")

    daily_counts = (
        df.assign(
            date=df["timestamp"].dt.date
        )
        .groupby(
            ["station_id", "date"]
        )
        .size()
    )

    print(daily_counts.describe())

    print()
    print("Rows per station:")

    print(
        df.groupby("station_id")
        .size()
        .sort_index()
    )


def main() -> None:

    # Keep the same end date used by our previous
    # 90-day dataset so the experiments remain comparable.
    end_date = date(2026, 7, 13)

    start_date = (
        end_date
        - timedelta(days=DAYS - 1)
    )

    print("=" * 60)
    print("180-DAY HISTORICAL HYDROLOGY COLLECTION")
    print("=" * 60)

    print(f"Start date: {start_date}")
    print(f"End date:   {end_date}")

    print(
        f"Stations:   {', '.join(STATION_IDS)}"
    )

    print(
        f"Expected days/station: {DAYS}"
    )

    print(
        f"Expected rows/station: {DAYS * 24}"
    )

    print(
        f"Expected total rows: "
        f"{DAYS * 24 * len(STATION_IDS)}"
    )

    print()

    all_data = []

    for station_id in STATION_IDS:

        station_df = collect_station(
            station_id=station_id,
            start_date=start_date,
            end_date=end_date,
        )

        if not station_df.empty:

            all_data.append(
                station_df
            )

    if not all_data:

        print("No data collected.")
        return

    combined = pd.concat(
        all_data,
        ignore_index=True,
    )

    combined["timestamp"] = pd.to_datetime(
        combined["timestamp"],
        errors="coerce",
    )

    combined["value"] = pd.to_numeric(
        combined["value"],
        errors="coerce",
    )

    combined = combined[
        [
            "station_id",
            "timestamp",
            "value",
        ]
    ]

    combined = (
        combined
        .sort_values(
            [
                "station_id",
                "timestamp",
            ]
        )
        .reset_index(drop=True)
    )

    validate_dataset(combined)

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    combined.to_csv(
        OUTPUT_FILE,
        index=False,
    )

    print()
    print("=" * 60)
    print("SAVED")
    print("=" * 60)

    print(OUTPUT_FILE)
    print(
        f"Final rows: {len(combined)}"
    )


if __name__ == "__main__":
    main()