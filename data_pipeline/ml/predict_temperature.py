from pathlib import Path

import joblib
import pandas as pd
import psycopg2


MODEL_FILE = Path(
    "models/weather/temperature_random_forest.joblib"
)

FEATURE_FILE = Path(
    "data/processed/weather/temperature_forecast_features.csv"
)

LOCATION = "DN"


FEATURES = [
    "temperature_2m",
    "precipitation_mm",
    "relative_humidity_2m",
    "surface_pressure_hpa",
    "wind_speed_10m",
    "cloud_cover",
    "latitude",
    "longitude",
    "hour",
    "day_of_week",
    "day_of_month",
    "month",
    "day_of_year",
    "temperature_lag_1h",
    "temperature_lag_3h",
    "temperature_lag_6h",
    "temperature_lag_12h",
    "temperature_lag_24h",
    "precipitation_mm_lag_1h",
    "relative_humidity_2m_lag_1h",
    "surface_pressure_hpa_lag_1h",
    "wind_speed_10m_lag_1h",
    "cloud_cover_lag_1h",
    "temperature_rolling_mean_3h",
    "temperature_rolling_mean_6h",
    "temperature_rolling_mean_24h",
]


def main():
    print("Loading Random Forest model...")

    model = joblib.load(MODEL_FILE)

    print("Model loaded successfully.")
    print()

    print(f"Loading latest feature row for location: {LOCATION}")

    df = pd.read_csv(FEATURE_FILE)

    df["timestamp"] = pd.to_datetime(
        df["timestamp"]
    )

    location_data = (
        df[df["location_code"] == LOCATION]
        .sort_values("timestamp")
        .reset_index(drop=True)
    )

    if location_data.empty:
        raise ValueError(
            f"No data found for location: {LOCATION}"
        )

    latest = location_data.iloc[-1]

    X = latest[FEATURES].to_frame().T

    prediction = model.predict(X)[0]

    print()
    print("========================================")
    print("Temperature Forecast")
    print("========================================")
    print(f"Location:          {latest['location_code']}")
    print(f"Latest timestamp:  {latest['timestamp']}")
    print(f"Current temperature: {latest['temperature_2m']:.2f} °C")
    print(f"Predicted next hour: {prediction:.2f} °C")
    print("========================================")


if __name__ == "__main__":
    main()