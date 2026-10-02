import os
import time
import requests
import pandas as pd
from io import StringIO


BASE_URL = (
    "http://203.209.181.170:2018/API_TTB/XUAT/solieu.php"
)

OUTPUT_DIR = "data/processed"

OUTPUT_FILE = os.path.join(
    OUTPUT_DIR,
    "hydrology_confirmed_30_stations.csv",
)


# ============================================================
# 30 CONFIRMED ACTIVE HYDROLOGY STATIONS
# ============================================================

STATIONS = [
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
    "556100",
    "557600",
]


# Remove accidental duplicates while preserving order.
STATIONS = list(dict.fromkeys(STATIONS))


def fetch_station(
    station_id,
    start_time,
    end_time,
):
    """
    Fetch hydrology observations for one station.
    """

    params = {
        "matram": station_id,
        "ten_table": "mucnuoc_oday",
        "sophut": 60,
        "tinhtong": 0,
        "thoigianbd": f"'{start_time}'",
        "thoigiankt": f"'{end_time}'",
    }

    response = requests.get(
        BASE_URL,
        params=params,
        timeout=30,
    )

    response.raise_for_status()

    tables = pd.read_html(
        StringIO(response.text)
    )

    if not tables:
        return pd.DataFrame()

    df = tables[0]

    required_columns = {
        "Ma Tram",
        "thoi gian",
        "so lieu",
    }

    if not required_columns.issubset(
        df.columns
    ):
        return pd.DataFrame()

    df = df.rename(
        columns={
            "Ma Tram": "station_id",
            "thoi gian": "timestamp",
            "so lieu": "value",
        }
    )

    df["station_id"] = (
        df["station_id"]
        .astype(str)
    )

    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        errors="coerce",
    )

    df["value"] = pd.to_numeric(
        df["value"],
        errors="coerce",
    )

    # Remove rows without valid timestamps.
    df = df.dropna(
        subset=["timestamp"]
    )

    # Sort chronologically.
    df = df.sort_values(
        "timestamp"
    )

    # Remove duplicate observations.
    df = df.drop_duplicates(
        subset=[
            "station_id",
            "timestamp",
        ]
    )

    return df[
        [
            "station_id",
            "timestamp",
            "value",
        ]
    ]


def load_existing():
    """
    Load previously collected data if the file exists.
    """

    if not os.path.exists(
        OUTPUT_FILE
    ):
        return pd.DataFrame(
            columns=[
                "station_id",
                "timestamp",
                "value",
            ]
        )

    df = pd.read_csv(
        OUTPUT_FILE,
        dtype={
            "station_id": str,
        },
    )

    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        errors="coerce",
    )

    return df


def save_data(df):
    """
    Save collection progress safely.
    """

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True,
    )

    if df.empty:
        df.to_csv(
            OUTPUT_FILE,
            index=False,
            encoding="utf-8-sig",
        )
        return

    df = df.drop_duplicates(
        subset=[
            "station_id",
            "timestamp",
        ]
    )

    df = df.sort_values(
        [
            "station_id",
            "timestamp",
        ]
    )

    df.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig",
    )


def main():

    print("=" * 70)
    print("CONFIRMED HYDROLOGY STATION COLLECTION")
    print("=" * 70)

    # --------------------------------------------------------
    # Historical collection period
    # --------------------------------------------------------

    start_time = "2026-01-15 00:00"
    end_time = "2026-07-13 23:59"

    print(
        f"Historical period : "
        f"{start_time} -> {end_time}"
    )

    print(
        f"Stations to collect: "
        f"{len(STATIONS)}"
    )

    print()

    # --------------------------------------------------------
    # Load previously collected records
    # --------------------------------------------------------

    existing = load_existing()

    print(
        f"Existing saved records: "
        f"{len(existing)}"
    )

    all_data = existing.copy()

    successful_stations = []
    failed_stations = []
    empty_stations = []

    # --------------------------------------------------------
    # Collect each confirmed station
    # --------------------------------------------------------

    for index, station_id in enumerate(
        STATIONS,
        start=1,
    ):

        print()
        print("-" * 70)

        print(
            f"[{index}/{len(STATIONS)}] "
            f"Station {station_id}"
        )

        try:

            df = fetch_station(
                station_id,
                start_time,
                end_time,
            )

            if df.empty:

                print(
                    "  No data returned."
                )

                empty_stations.append(
                    station_id
                )

            else:

                print(
                    f"  Records fetched : "
                    f"{len(df)}"
                )

                print(
                    f"  First timestamp : "
                    f"{df['timestamp'].min()}"
                )

                print(
                    f"  Last timestamp  : "
                    f"{df['timestamp'].max()}"
                )

                # Add to combined dataset.
                all_data = pd.concat(
                    [
                        all_data,
                        df,
                    ],
                    ignore_index=True,
                )

                # Remove duplicates.
                all_data = (
                    all_data
                    .drop_duplicates(
                        subset=[
                            "station_id",
                            "timestamp",
                        ]
                    )
                )

                # Save immediately.
                save_data(
                    all_data
                )

                successful_stations.append(
                    station_id
                )

                print(
                    f"  Total saved records: "
                    f"{len(all_data)}"
                )

        except requests.RequestException as exc:

            print(
                f"  REQUEST ERROR: {exc}"
            )

            failed_stations.append(
                station_id
            )

        except Exception as exc:

            print(
                f"  ERROR: "
                f"{type(exc).__name__}: {exc}"
            )

            failed_stations.append(
                station_id
            )

        # Small delay to avoid hammering API.
        time.sleep(0.75)

    # --------------------------------------------------------
    # Final cleanup
    # --------------------------------------------------------

    if not all_data.empty:

        all_data = (
            all_data
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

    save_data(
        all_data
    )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    print()
    print()
    print("=" * 70)
    print("HYDROLOGY COLLECTION SUMMARY")
    print("=" * 70)

    print(
        f"Stations attempted : "
        f"{len(STATIONS)}"
    )

    print(
        f"Stations successful : "
        f"{len(successful_stations)}"
    )

    print(
        f"Stations empty      : "
        f"{len(empty_stations)}"
    )

    print(
        f"Stations failed     : "
        f"{len(failed_stations)}"
    )

    print(
        f"Total records       : "
        f"{len(all_data)}"
    )

    if not all_data.empty:

        print(
            f"Stations with data  : "
            f"{all_data['station_id'].nunique()}"
        )

        print(
            f"Oldest timestamp    : "
            f"{all_data['timestamp'].min()}"
        )

        print(
            f"Newest timestamp    : "
            f"{all_data['timestamp'].max()}"
        )

        print()

        print(
            "Records per station:"
        )

        counts = (
            all_data
            .groupby("station_id")
            .size()
            .sort_index()
        )

        print(
            counts.to_string()
        )

        print()

        print(
            "Missing values:"
        )

        print(
            f"  Value missing: "
            f"{all_data['value'].isna().sum()}"
        )

        print(
            f"  Timestamp missing: "
            f"{all_data['timestamp'].isna().sum()}"
        )

    if empty_stations:

        print()
        print(
            "EMPTY STATIONS:"
        )

        print(
            ", ".join(
                empty_stations
            )
        )

    if failed_stations:

        print()
        print(
            "FAILED STATIONS:"
        )

        print(
            ", ".join(
                failed_stations
            )
        )

    print()
    print(
        f"Saved file:"
    )

    print(
        OUTPUT_FILE
    )

    print("=" * 70)

    print()
    print(
        "Hydrology historical collection completed."
    )


if __name__ == "__main__":
    main()