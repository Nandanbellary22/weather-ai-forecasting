from pathlib import Path
from datetime import date, timedelta

import pandas as pd

from data_pipeline.crawlers.hydrology_api import fetch_station_data


# All confirmed hydrology stations.
STATION_IDS = [
    "553000",
    "553100",
    "553200",
    "553300",
    "553400",
    "553800",
    "553900",
    "554000",
    "554100",
    "554200",
    "554300",
    "554400",
    "554500",
    "554600",
    "554700",
    "554800",
    "554900",
    "555000",
    "555100",
    "555200",
    "555300",
    "555400",
    "555500",
    "555800",
    "555900",
    "556100",
    "557600",
    "559200",
]

DAYS = 180

# Keep the same historical period used by the existing dataset
# so previous experiments remain comparable.
END_DATE = date(2026, 7, 13)

OUTPUT_DIR = Path("data/processed")
OUTPUT_FILE = OUTPUT_DIR / "historical_180days_all_stations.csv"


def collect_station(
    station_id: str,
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    """
    Collect the complete historical period for one station.

    The hydrology API supports requesting the full period in one call,
    so we avoid making one API request per day.
    """

    start_time = f"{start_date.isoformat()} 00:00"
    end_time = f"{end_date.isoformat()} 23:59"

    print(
        f"Collecting {station_id} | "
        f"{start_date} -> {end_date}"
    )

    try:
        df = fetch_station_data(
            station_id=station_id,
            start_time=start_time,
            end_time=end_time,
        )

    except Exception as exc:
        print(
            f"  ERROR: {station_id} -> {exc}"
        )
        return pd.DataFrame()

    if df is None or df.empty:
        print(
            f"  NO DATA: {station_id}"
        )
        return pd.DataFrame()

    df = df.copy()

    df["station_id"] = station_id

    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        errors="coerce",
    )

    df["value"] = pd.to_numeric(
        df["value"],
        errors="coerce",
    )

    df = df[
        [
            "station_id",
            "timestamp",
            "value",
        ]
    ]

    df = (
        df.dropna(subset=["timestamp"])
        .sort_values("timestamp")
        .drop_duplicates(
            subset=["station_id", "timestamp"]
        )
        .reset_index(drop=True)
    )

    print(
        f"  Rows: {len(df)}"
    )

    print(
        f"  Start: {df['timestamp'].min()}"
    )

    print(
        f"  End:   {df['timestamp'].max()}"
    )

    return df


def validate_station(
    df: pd.DataFrame,
    station_id: str,
    start_date: date,
    end_date: date,
) -> None:
    """
    Validate one station's historical coverage.
    """

    print()
    print(
        f"Validation: {station_id}"
    )
    print("-" * 60)

    expected_rows = DAYS * 24

    actual_rows = len(df)

    print(
        f"Expected rows: {expected_rows}"
    )

    print(
        f"Actual rows:   {actual_rows}"
    )

    print(
        f"Difference:    {actual_rows - expected_rows}"
    )

    if actual_rows == expected_rows:
        print("Coverage:       COMPLETE")
    else:
        print("Coverage:       INCOMPLETE")

    if df.empty:
        print("Status:         NO DATA")
        return

    duplicate_count = df.duplicated(
        subset=[
            "station_id",
            "timestamp",
        ]
    ).sum()

    print(
        f"Duplicates:     {duplicate_count}"
    )

    missing_timestamps = df["timestamp"].isna().sum()

    missing_values = df["value"].isna().sum()

    print(
        f"Missing time:   {missing_timestamps}"
    )

    print(
        f"Missing value:  {missing_values}"
    )

    unique_days = (
        df["timestamp"]
        .dt.date
        .nunique()
    )

    print(
        f"Available days: {unique_days}/{DAYS}"
    )

    expected_start = pd.Timestamp(
        start_date
    )

    expected_end = pd.Timestamp(
        end_date
    )

    actual_start = df["timestamp"].min()
    actual_end = df["timestamp"].max()

    print(
        f"Expected start: {expected_start}"
    )

    print(
        f"Actual start:   {actual_start}"
    )

    print(
        f"Expected end:   {expected_end}"
    )

    print(
        f"Actual end:     {actual_end}"
    )


def validate_dataset(
    df: pd.DataFrame,
    start_date: date,
    end_date: date,
) -> None:
    """
    Perform final validation across all stations.
    """

    print()
    print("=" * 70)
    print("FINAL 180-DAY HYDROLOGY DATASET VALIDATION")
    print("=" * 70)

    if df.empty:
        print("Dataset is empty.")
        return

    expected_rows_per_station = DAYS * 24

    expected_total_rows = (
        expected_rows_per_station
        * len(STATION_IDS)
    )

    print(
        f"Rows:              {len(df)}"
    )

    print(
        f"Expected rows:     {expected_total_rows}"
    )

    print(
        f"Difference:        "
        f"{len(df) - expected_total_rows}"
    )

    print(
        f"Stations:           "
        f"{df['station_id'].nunique()}"
    )

    print(
        f"Expected stations:  "
        f"{len(STATION_IDS)}"
    )

    print(
        f"Start:              "
        f"{df['timestamp'].min()}"
    )

    print(
        f"End:                "
        f"{df['timestamp'].max()}"
    )

    print()
    print("Rows by station:")
    print(
        df.groupby("station_id")
        .size()
        .sort_index()
        .to_string()
    )

    print()
    print("Missing values:")
    print(
        df[
            [
                "station_id",
                "timestamp",
                "value",
            ]
        ]
        .isna()
        .sum()
        .to_string()
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
        .sort_index()
    )

    print(
        days_per_station.to_string()
    )

    print()
    print("Rows per station per day:")

    daily_counts = (
        df.assign(
            date=df["timestamp"].dt.date
        )
        .groupby(
            [
                "station_id",
                "date",
            ]
        )
        .size()
    )

    print(
        daily_counts.describe()
    )

    print()
    print("Stations with incomplete coverage:")

    station_counts = (
        df.groupby("station_id")
        .size()
    )

    incomplete = station_counts[
        station_counts != expected_rows_per_station
    ]

    if incomplete.empty:
        print("None")
    else:
        print(
            incomplete.sort_index().to_string()
        )

    print()
    print("Expected date range:")
    print(
        f"{start_date} -> {end_date}"
    )


def main() -> None:

    start_date = (
        END_DATE
        - timedelta(days=DAYS - 1)
    )

    print("=" * 70)
    print("180-DAY HISTORICAL HYDROLOGY COLLECTION")
    print("=" * 70)

    print(
        f"Start date:          {start_date}"
    )

    print(
        f"End date:            {END_DATE}"
    )

    print(
        f"Stations:             {len(STATION_IDS)}"
    )

    print(
        f"Expected days:        {DAYS}"
    )

    print(
        f"Expected rows/station:"
        f" {DAYS * 24}"
    )

    print(
        f"Expected total rows:  "
        f"{DAYS * 24 * len(STATION_IDS)}"
    )

    print()

    all_data = []

    for station_id in STATION_IDS:

        station_df = collect_station(
            station_id=station_id,
            start_date=start_date,
            end_date=END_DATE,
        )

        if station_df.empty:
            continue

        validate_station(
            df=station_df,
            station_id=station_id,
            start_date=start_date,
            end_date=END_DATE,
        )

        all_data.append(
            station_df
        )

    if not all_data:
        print()
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
        .dropna(
            subset=[
                "station_id",
                "timestamp",
            ]
        )
        .drop_duplicates(
            subset=[
                "station_id",
                "timestamp",
            ]
        )
        .sort_values(
            [
                "station_id",
                "timestamp",
            ]
        )
        .reset_index(drop=True)
    )

    validate_dataset(
        df=combined,
        start_date=start_date,
        end_date=END_DATE,
    )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    combined.to_csv(
        OUTPUT_FILE,
        index=False,
    )

    print()
    print("=" * 70)
    print("SAVED")
    print("=" * 70)

    print(
        f"File: {OUTPUT_FILE}"
    )

    print(
        f"Final rows: {len(combined)}"
    )

    print(
        f"Final stations: "
        f"{combined['station_id'].nunique()}"
    )


if __name__ == "__main__":
    main()