import requests
import pandas as pd
from io import StringIO

from data_pipeline.validation.validate_station_data import validate_station_data
URL = (
    "http://203.209.181.170:2018/API_TTB/XUAT/solieu.php"
    "?matram=553100"
    "&ten_table=mucnuoc_oday"
    "&sophut=60"
    "&tinhtong=0"
    "&thoigianbd=%272026-07-13%2000%3A00%27"
    "&thoigiankt=%272026-07-13%2023%3A59%27"
)


def fetch_station_data():
    # 1. Request data from the API
    response = requests.get(URL, timeout=30)

    print("HTTP status:", response.status_code)
    print("Content-Type:", response.headers.get("Content-Type"))

    # Stop if the request was not successful
    response.raise_for_status()

    # 2. Parse the HTML table
    tables = pd.read_html(StringIO(response.text))

    # Use the first table returned by the API
    df = tables[0]

    # 3. Rename source columns
    df = df.rename(
        columns={
            "Ma Tram": "station_id",
            "thoi gian": "timestamp",
            "so lieu": "value",
        }
    )

    # 4. Convert data types
    df["station_id"] = df["station_id"].astype(str)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")

    # 5. Sort chronologically
    df = df.sort_values("timestamp").reset_index(drop=True)

    return df


if __name__ == "__main__":
    df = fetch_station_data()

    print("\n--- Cleaned DataFrame ---")
    print(df)

    print("\n--- Data Types ---")
    print(df.dtypes)

    validation = validate_station_data(df)

    print("\n--- Validation Results ---")

    for key, value in validation.items():
        print(f"{key}: {value}")

    if validation["valid"]:
        output_path = "data/processed/station_553100.csv"
        df.to_csv(output_path, index=False)

        print(f"\nSaved validated data to: {output_path}")
    else:
        print("\nData validation failed. File was not saved.")