import os
import time
import requests
import pandas as pd
from io import StringIO

BASE_URL = "http://203.209.181.170:2018/API_TTB/XUAT/solieu.php"

OUTPUT_PATH = "data/processed/station_discovery_resume.csv"

# Continue only through ranges that previously produced network errors.
# These are deliberately split into small batches.
RANGES = [
    (555501, 555600),
    (555601, 555700),
    (555701, 555800),
    (555801, 555900),
    (555901, 556000),
    (556001, 556100),
    (556101, 556200),
    (556201, 556300),
    (556301, 556400),
    (556401, 556500),
    (556501, 556600),
    (556601, 556700),
    (556701, 556800),
    (556801, 556900),
    (556901, 557000),
    (557001, 557100),
    (557101, 557200),
    (557201, 557300),
    (557301, 557400),
    (557401, 557500),
    (557501, 557600),
]


def test_station(station_id):
    params = {
        "matram": str(station_id),
        "ten_table": "mucnuoc_oday",
        "sophut": 60,
        "tinhtong": 0,
        "thoigianbd": "'2026-07-13 00:00'",
        "thoigiankt": "'2026-07-13 23:59'",
    }

    try:
        response = requests.get(
            BASE_URL,
            params=params,
            timeout=15,
        )

        response.raise_for_status()

        tables = pd.read_html(
            StringIO(response.text)
        )

        if not tables:
            return {
                "station_id": str(station_id),
                "status": "NO_DATA",
                "rows": 0,
                "numeric_rows": 0,
                "first_value": None,
                "last_value": None,
                "error": "",
            }

        df = tables[0]

        if "so lieu" not in df.columns:
            return {
                "station_id": str(station_id),
                "status": "NO_DATA",
                "rows": len(df),
                "numeric_rows": 0,
                "first_value": None,
                "last_value": None,
                "error": "",
            }

        values = pd.to_numeric(
            df["so lieu"],
            errors="coerce",
        )

        numeric_values = values.dropna()

        if numeric_values.empty:
            status = "NO_DATA"
            first_value = None
            last_value = None
        else:
            status = "ACTIVE"
            first_value = float(numeric_values.iloc[0])
            last_value = float(numeric_values.iloc[-1])

        return {
            "station_id": str(station_id),
            "status": status,
            "rows": len(df),
            "numeric_rows": len(numeric_values),
            "first_value": first_value,
            "last_value": last_value,
            "error": "",
        }

    except requests.RequestException as exc:
        return {
            "station_id": str(station_id),
            "status": "ERROR",
            "rows": 0,
            "numeric_rows": 0,
            "first_value": None,
            "last_value": None,
            "error": str(exc),
        }

    except Exception as exc:
        return {
            "station_id": str(station_id),
            "status": "ERROR",
            "rows": 0,
            "numeric_rows": 0,
            "first_value": None,
            "last_value": None,
            "error": f"{type(exc).__name__}: {exc}",
        }


def load_existing_results():
    if not os.path.exists(OUTPUT_PATH):
        return pd.DataFrame()

    return pd.read_csv(
        OUTPUT_PATH,
        dtype={"station_id": str},
    )


def save_results(df):
    os.makedirs(
        os.path.dirname(OUTPUT_PATH),
        exist_ok=True,
    )

    df = df.drop_duplicates(
        subset=["station_id"],
        keep="last",
    )

    df = df.sort_values(
        "station_id"
    )

    df.to_csv(
        OUTPUT_PATH,
        index=False,
        encoding="utf-8-sig",
    )


def main():
    print("=" * 70)
    print("SAFE HYDROLOGY STATION DISCOVERY")
    print("=" * 70)

    existing = load_existing_results()

    tested_ids = set()

    if not existing.empty:
        tested_ids = set(
            existing["station_id"]
            .astype(str)
        )

        print(
            f"Existing discovery records: "
            f"{len(existing)}"
        )

    results = (
        existing.to_dict("records")
        if not existing.empty
        else []
    )

    total_to_test = sum(
        end - start + 1
        for start, end in RANGES
    )

    completed = 0

    print(
        f"IDs scheduled for this run: "
        f"{total_to_test}"
    )
    print()

    for range_index, (start, end) in enumerate(
        RANGES,
        start=1,
    ):
        print(
            f"RANGE {range_index}/{len(RANGES)}: "
            f"{start}-{end}"
        )

        for station_id in range(
            start,
            end + 1,
        ):
            station_id = str(station_id)

            if station_id in tested_ids:
                continue

            result = test_station(
                station_id
            )

            results.append(result)
            tested_ids.add(station_id)

            completed += 1

            if result["status"] == "ACTIVE":
                print(
                    f"  ACTIVE: {station_id} "
                    f"rows={result['rows']} "
                    f"first={result['first_value']} "
                    f"last={result['last_value']}"
                )

            elif result["status"] == "ERROR":
                print(
                    f"  ERROR: {station_id} "
                    f"{result['error']}"
                )

            # Save every 25 stations.
            if completed % 25 == 0:
                save_results(
                    pd.DataFrame(results)
                )
                print(
                    f"  Progress saved "
                    f"({completed} new IDs)"
                )

            # Small delay to avoid hammering the API.
            time.sleep(0.25)

        save_results(
            pd.DataFrame(results)
        )

        print(
            f"Range completed: "
            f"{start}-{end}"
        )
        print()

    final_df = pd.DataFrame(
        results
    )

    save_results(final_df)

    print()
    print("=" * 70)
    print("DISCOVERY SUMMARY")
    print("=" * 70)

    print(
        f"Total records: "
        f"{len(final_df)}"
    )

    print(
        f"ACTIVE: "
        f"{(final_df['status'] == 'ACTIVE').sum()}"
    )

    print(
        f"NO_DATA: "
        f"{(final_df['status'] == 'NO_DATA').sum()}"
    )

    print(
        f"ERROR: "
        f"{(final_df['status'] == 'ERROR').sum()}"
    )

    active = final_df[
        final_df["status"] == "ACTIVE"
    ]

    print()
    print("ACTIVE STATIONS:")
    print(
        active[
            [
                "station_id",
                "rows",
                "first_value",
                "last_value",
            ]
        ].to_string(index=False)
    )

    print()
    print(
        f"Saved inventory: "
        f"{OUTPUT_PATH}"
    )

    print("=" * 70)


if __name__ == "__main__":
    main()