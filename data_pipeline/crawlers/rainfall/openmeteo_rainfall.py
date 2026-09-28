from pathlib import Path
from datetime import date
import requests
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[3]
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "rainfall"

BASE_URL = "https://archive-api.open-meteo.com/v1/archive"

# Da Nang reference point
LATITUDE = 16.0544
LONGITUDE = 108.2022

TIMEZONE = "Asia/Ho_Chi_Minh"


def fetch_rainfall(start_date: str, end_date: str) -> pd.DataFrame:
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "start_date": start_date,
        "end_date": end_date,
        "hourly": "precipitation,rain",
        "timezone": TIMEZONE,
    }

    response = requests.get(BASE_URL, params=params, timeout=60)
    response.raise_for_status()

    data = response.json()

    hourly = data["hourly"]

    df = pd.DataFrame({
        "timestamp": hourly["time"],
        "precipitation_mm": hourly["precipitation"],
        "rain_mm": hourly["rain"],
    })

    df["timestamp"] = pd.to_datetime(df["timestamp"])

    df["latitude"] = data["latitude"]
    df["longitude"] = data["longitude"]

    return df


def save_rainfall(df: pd.DataFrame, start_date: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    output_file = OUTPUT_DIR / f"rainfall_{start_date}.csv"

    df.to_csv(output_file, index=False)

    return output_file


def main():
    start_date = "2026-07-13"
    end_date = "2026-07-13"

    print(f"Fetching rainfall data: {start_date} → {end_date}")

    df = fetch_rainfall(start_date, end_date)

    print(f"Rows received: {len(df)}")
    print(f"Missing precipitation values: {df['precipitation_mm'].isna().sum()}")

    output_file = save_rainfall(df, start_date)

    print(f"Saved: {output_file}")
    print()
    print(df.head(10))


if __name__ == "__main__":
    main()