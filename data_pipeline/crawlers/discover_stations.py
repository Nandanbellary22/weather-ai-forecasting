import requests
import pandas as pd
from io import StringIO


BASE_URL = "http://203.209.181.170:2018/API_TTB/XUAT/solieu.php"

START_TIME = "2026-07-13 00:00"
END_TIME = "2026-07-13 01:00"


def test_station(station_id: str) -> dict:
    """
    Test a station ID and classify it as:
    ACTIVE, NO_DATA, or ERROR.
    """

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
            timeout=10,
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

        # Check expected column.
        if "so lieu" not in df.columns:
            result["error"] = (
                f"Missing 'so lieu' column: {list(df.columns)}"
            )
            return result

        # Convert observations to numeric.
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


def discover_station_range(
    start_id: int,
    end_id: int,
) -> pd.DataFrame:

    results = []

    total = end_id - start_id + 1

    print("=" * 70)
    print("STATION DISCOVERY")
    print("=" * 70)

    print(f"Testing IDs: {start_id} to {end_id}")
    print(f"Total IDs: {total}")
    print()

    for number in range(start_id, end_id + 1):

        station_id = str(number)

        result = test_station(station_id)

        results.append(result)

        if result["status"] == "ACTIVE":

            print(
                f"[ACTIVE]  {station_id} "
                f"| rows={result['rows']} "
                f"| numeric={result['numeric_rows']} "
                f"| first={result['first_value']} "
                f"| last={result['last_value']}"
            )

        elif result["status"] == "NO_DATA":

            print(
                f"[NO DATA] {station_id}"
            )

        else:

            print(
                f"[ERROR]   {station_id} "
                f"| {result['error']}"
            )

    return pd.DataFrame(results)


if __name__ == "__main__":

    START_ID = 553000
    END_ID = 553400

    df = discover_station_range(
        start_id=START_ID,
        end_id=END_ID,
    )

    print("\n" + "=" * 70)
    print("DISCOVERY SUMMARY")
    print("=" * 70)

    active = df[
        df["status"] == "ACTIVE"
    ]

    no_data = df[
        df["status"] == "NO_DATA"
    ]

    errors = df[
        df["status"] == "ERROR"
    ]

    print(f"Total IDs tested : {len(df)}")
    print(f"Active stations  : {len(active)}")
    print(f"No-data IDs      : {len(no_data)}")
    print(f"Errors            : {len(errors)}")

    print("\nACTIVE STATIONS:")

    for station_id in active["station_id"]:
        print(f"  - {station_id}")

    output_path = (
        "data/processed/station_discovery.csv"
    )

    df.to_csv(
        output_path,
        index=False,
    )

    print(
        f"\nSaved inventory to: {output_path}"
    )