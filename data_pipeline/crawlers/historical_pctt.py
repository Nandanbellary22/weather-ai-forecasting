import os
import time
import requests
import pandas as pd


BASE_URL = (
    "https://pctt.danang.gov.vn/"
    "DesktopModules/PCTT/api/PCTTApi/"
    "baocaothuydiens_thongke"
)

# Match the 180-day hydrology dataset period.
START_DATE = "2026-01-15"
END_DATE = "2026-07-13"

OUTPUT_DIR = "data/processed"

RAW_OUTPUT = os.path.join(
    OUTPUT_DIR,
    "pctt_historical_180days_raw.csv"
)

REQUEST_TIMEOUT = 30

EXPECTED_FIELDS = [
    "thoigianxa",
    "ngay",
    "gio",
    "htl1",
    "qvao1",
    "luuluongnhamay1",
    "qxaquacua1",
    "htl2",
    "qvao2",
    "luuluongnhamay2",
    "qxaquacua2",
    "htl3",
    "qvao3",
    "luuluongnhamay3",
    "qxaquacua3",
    "htl4",
    "qvao4",
    "luuluongnhamay4",
    "qxaquacua4",
    "qvevugia",
    "qvethubon",
]


def fetch_day(date_str):
    """
    Fetch one calendar day of PCTT data.
    """

    params = {
        "ngaybatdau": f"{date_str}T00:00:00+07:00",
        "ngayketthuc": f"{date_str}T23:59:59+07:00",
        "lst_thuydien_id": "1,2,3,4",
    }

    response = requests.get(
        BASE_URL,
        params=params,
        timeout=REQUEST_TIMEOUT,
    )

    response.raise_for_status()

    data = response.json()

    if not isinstance(data, list):
        raise ValueError(
            "PCTT API response is not a JSON list."
        )

    return pd.DataFrame(data)


def standardize_dataframe(df):
    """
    Keep the known PCTT fields and add a parsed timestamp.
    """

    missing_fields = [
        field
        for field in EXPECTED_FIELDS
        if field not in df.columns
    ]

    if missing_fields:
        raise ValueError(
            f"Missing API fields: {missing_fields}"
        )

    df = df[EXPECTED_FIELDS].copy()

    df["timestamp"] = pd.to_datetime(
        df["thoigianxa"],
        errors="coerce",
    )

    numeric_fields = [
        field
        for field in EXPECTED_FIELDS
        if field not in [
            "thoigianxa",
            "ngay",
            "gio",
        ]
    ]

    for field in numeric_fields:
        df[field] = pd.to_numeric(
            df[field],
            errors="coerce",
        )

    return df


def main():

    print("=" * 80)
    print("PCTT HISTORICAL 180-DAY COLLECTOR")
    print("=" * 80)

    print(f"Start date : {START_DATE}")
    print(f"End date   : {END_DATE}")
    print()

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True,
    )

    dates = pd.date_range(
        START_DATE,
        END_DATE,
        freq="D",
    )

    all_frames = []

    successful_days = 0
    failed_days = 0

    total_rows = 0

    for index, date in enumerate(dates, start=1):

        date_str = date.strftime(
            "%Y-%m-%d"
        )

        print(
            f"[{index}/{len(dates)}] "
            f"Fetching {date_str}..."
        )

        try:

            df = fetch_day(
                date_str
            )

            df = standardize_dataframe(
                df
            )

            df["source_date"] = date_str

            all_frames.append(df)

            successful_days += 1
            total_rows += len(df)

            print(
                f"    Rows: {len(df)}"
            )

        except Exception as exc:

            failed_days += 1

            print(
                f"    ERROR: {type(exc).__name__}: {exc}"
            )

        # Small delay so we do not send requests
        # continuously to the public API.
        time.sleep(0.2)

    print()
    print("=" * 80)
    print("COLLECTION COMPLETE")
    print("=" * 80)

    print(
        f"Expected days    : {len(dates)}"
    )

    print(
        f"Successful days  : {successful_days}"
    )

    print(
        f"Failed days      : {failed_days}"
    )

    print(
        f"Total rows       : {total_rows}"
    )

    if not all_frames:

        print()
        print(
            "No data was collected."
        )

        return

    # Combine all successful days.
    historical_df = pd.concat(
        all_frames,
        ignore_index=True,
    )

    historical_df = historical_df.sort_values(
        "timestamp"
    ).reset_index(
        drop=True
    )

    # Save the raw historical dataset.
    historical_df.to_csv(
        RAW_OUTPUT,
        index=False,
    )

    print()
    print(
        f"Saved raw dataset:"
    )

    print(
        f"  {RAW_OUTPUT}"
    )

    print()
    print("Dataset summary")
    print("-" * 80)

    print(
        f"Rows       : {len(historical_df)}"
    )

    print(
        f"Columns    : {len(historical_df.columns)}"
    )

    if not historical_df.empty:

        print(
            f"Start time : "
            f"{historical_df['timestamp'].min()}"
        )

        print(
            f"End time   : "
            f"{historical_df['timestamp'].max()}"
        )

    print()
    print("Rows per source date")
    print("-" * 80)

    rows_per_day = (
        historical_df
        .groupby("source_date")
        .size()
    )

    print(
        rows_per_day.describe()
    )

    print()
    print("Missing values")
    print("-" * 80)

    missing_counts = (
        historical_df[
            EXPECTED_FIELDS
        ]
        .isna()
        .sum()
    )

    print(
        missing_counts[
            missing_counts > 0
        ].to_string()
    )

    print()
    print("Duplicate timestamps")
    print("-" * 80)

    duplicate_count = (
        historical_df["timestamp"]
        .duplicated(
            keep=False
        )
        .sum()
    )

    print(
        f"Duplicate timestamp rows: "
        f"{duplicate_count}"
    )

    print()
    print("=" * 80)
    print("PCTT COLLECTION FINISHED")
    print("=" * 80)


if __name__ == "__main__":
    main()