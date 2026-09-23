import requests
import pandas as pd
from io import StringIO


BASE_URL = "http://203.209.181.170:2018/API_TTB/XUAT/solieu.php"

STATION_IDS = [
    "553000",
    "553001",
    "553002",
    "553100",
    "553200",
    "553208",
    "553210",
    "553300",
    "553400",
]


def inspect_station(station_id: str):

    params = {
        "matram": station_id,
        "ten_table": "mucnuoc_oday",
        "sophut": 60,
        "tinhtong": 0,
        "thoigianbd": "'2026-07-13 00:00'",
        "thoigiankt": "'2026-07-13 01:00'",
    }

    print("\n" + "=" * 70)
    print(f"REQUESTED STATION: {station_id}")
    print("=" * 70)

    try:
        response = requests.get(
            BASE_URL,
            params=params,
            timeout=30,
        )

        print(f"HTTP status: {response.status_code}")
        print(f"Content-Type: {response.headers.get('Content-Type')}")

        tables = pd.read_html(
            StringIO(response.text)
        )

        if not tables:
            print("NO TABLE FOUND")
            return

        df = tables[0]

        print(f"Rows returned: {len(df)}")
        print(f"Columns: {list(df.columns)}")

        print("\nRaw returned data:")
        print(df.to_string(index=False))

        if "Ma Tram" in df.columns:
            print("\nReturned station IDs:")

            print(
                df["Ma Tram"]
                .astype(str)
                .unique()
            )

        if "so lieu" in df.columns:

            print("\nValue statistics:")

            values = pd.to_numeric(
                df["so lieu"],
                errors="coerce",
            )

            print(
                values.describe()
            )

    except Exception as e:

        print(f"ERROR: {e}")


if __name__ == "__main__":

    for station_id in STATION_IDS:

        inspect_station(station_id)