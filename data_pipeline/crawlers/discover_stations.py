import concurrent.futures
from io import StringIO

import pandas as pd
import requests


BASE_URL = "http://203.209.181.170:2018/API_TTB/XUAT/solieu.php"

START_TIME = "2026-07-13 00:00"
END_TIME = "2026-07-13 01:00"

MAX_WORKERS = 10
TIMEOUT = 15


def test_station(station_id: str) -> dict:
    params = {
        "matram": station_id,
        "ten_table": "mucnuoc_oday",
        "sophut": 60,
        "tinhtong": 0,
        "thoigianbd": f"'{START_TIME}'",
        "thoigiankt": f"'{END_TIME}'",
    }

    result = {
        "station_id": station_id,
        "status": "ERROR",
        "rows": 0,
        "numeric_rows": 0,
        "first_value": None,
        "last_value": None,
        "error": "",
    }

    try:
        response = requests.get(
            BASE_URL,
            params=params,
            timeout=TIMEOUT,
        )

        response.raise_for_status()

        tables = pd.read_html(
            StringIO(response.text)
        )

        if not tables:
            result["error"] = "No table found"
            return result

        df = tables[0]

        result["rows"] = len(df)

        if "so lieu" not in df.columns:
            result["error"] = (
                f"Missing 'so lieu' column: {list(df.columns)}"
            )
            return result

        values = pd.to_numeric(
            df["so lieu"],
            errors="coerce",
        )

        numeric_values = values.dropna()

        result["numeric_rows"] = len(numeric_values)

        if len(numeric_values) > 0:
            result["status"] = "ACTIVE"
            result["first_value"] = numeric_values.iloc[0]
            result["last_value"] = numeric_values.iloc[-1]
        else:
            result["status"] = "NO_DATA"

        return result

    except Exception as e:
        result["error"] = str(e)
        return result


def discover_range(start_id: int, end_id: int) -> pd.DataFrame:
    station_ids = [
        str(i)
        for i in range(start_id, end_id + 1)
    ]

    results = []

    print()
    print("=" * 70)
    print("FAST FULL STATION DISCOVERY")
    print("=" * 70)
    print(f"Range: {start_id} -> {end_id}")
    print(f"IDs: {len(station_ids)}")
    print(f"Workers: {MAX_WORKERS}")
    print()

    completed = 0

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=MAX_WORKERS
    ) as executor:

        future_map = {
            executor.submit(
                test_station,
                station_id,
            ): station_id
            for station_id in station_ids
        }

        for future in concurrent.futures.as_completed(
            future_map
        ):

            result = future.result()
            results.append(result)

            completed += 1

            if result["status"] == "ACTIVE":

                print(
                    f"[ACTIVE] {result['station_id']} "
                    f"| first={result['first_value']} "
                    f"| last={result['last_value']}"
                )

            elif result["status"] == "ERROR":

                print(
                    f"[ERROR]  {result['station_id']} "
                    f"| {result['error']}"
                )

            if completed % 100 == 0:
                print(
                    f"Progress: "
                    f"{completed}/{len(station_ids)}"
                )

    return pd.DataFrame(results)


if __name__ == "__main__":

    # Full scans of the previously unexplored gaps.
    ranges = [
        (555501, 556099),
        (556101, 557599),
        (557601, 559199),
        (559201, 560000),
    ]

    all_results = []

    for start_id, end_id in ranges:

        df = discover_range(
            start_id,
            end_id,
        )

        all_results.append(df)

    combined = pd.concat(
        all_results,
        ignore_index=True,
    )

    combined["station_id"] = (
        combined["station_id"]
        .astype(str)
    )

    combined = combined.sort_values(
        "station_id"
    ).reset_index(drop=True)

    output_path = (
        "data/processed/"
        "station_discovery_full_gaps.csv"
    )

    combined.to_csv(
        output_path,
        index=False,
    )

    active = combined[
        combined["status"] == "ACTIVE"
    ]

    no_data = combined[
        combined["status"] == "NO_DATA"
    ]

    errors = combined[
        combined["status"] == "ERROR"
    ]

    print()
    print("=" * 70)
    print("FULL GAP DISCOVERY SUMMARY")
    print("=" * 70)

    print(f"Total IDs tested : {len(combined)}")
    print(f"Active stations  : {len(active)}")
    print(f"No-data IDs      : {len(no_data)}")
    print(f"Errors            : {len(errors)}")

    print()
    print("NEW ACTIVE STATIONS:")

    if active.empty:
        print("None found.")
    else:
        for station_id in active["station_id"]:
            print(f"  - {station_id}")

    print()
    print(
        f"Saved inventory to: {output_path}"
    )