import requests
import pandas as pd
from io import StringIO

from data_pipeline.validation.validate_station_data import validate_station_data


BASE_URL = "http://203.209.181.170:2018/API_TTB/XUAT/solieu.php"


def fetch_station_data(
    station_id: str,
    start_time: str,
    end_time: str,
) -> pd.DataFrame:
    """
    Fetch hydrological station data from the professor-provided API.

    Parameters
    ----------
    station_id : str
        Station ID, for example "553100" or "553300".

    start_time : str
        Start time in format YYYY-MM-DD HH:MM.

    end_time : str
        End time in format YYYY-MM-DD HH:MM.

    Returns
    -------
    pd.DataFrame
        Cleaned station data with columns:
        station_id, timestamp, value.
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

    print(f"HTTP status: {response.status_code}")
    print(f"Content-Type: {response.headers.get('Content-Type')}")
    print(f"Station: {station_id}")

    tables = pd.read_html(StringIO(response.text))

    if not tables:
        raise ValueError("No table found in API response.")

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
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")

    # Sort chronologically
    df = df.sort_values("timestamp").reset_index(drop=True)

    return df


def collect_and_validate(
    station_id: str,
    start_time: str,
    end_time: str,
) -> pd.DataFrame:

    df = fetch_station_data(
        station_id=station_id,
        start_time=start_time,
        end_time=end_time,
    )

    validation = validate_station_data(df)

    print("\n--- Validation Results ---")

    for key, value in validation.items():
        print(f"{key}: {value}")

    if not validation["valid"]:
        raise ValueError("Data validation failed.")

    return df


if __name__ == "__main__":

    station_id = "553300"

    start_time = "2026-07-13 00:00"
    end_time = "2026-07-13 23:59"

    df = collect_and_validate(
        station_id=station_id,
        start_time=start_time,
        end_time=end_time,
    )

    print("\n--- Cleaned DataFrame ---")
    print(df)

    output_path = f"data/processed/station_{station_id}.csv"

    df.to_csv(
        output_path,
        index=False,
    )

    print(f"\nSaved data to: {output_path}")