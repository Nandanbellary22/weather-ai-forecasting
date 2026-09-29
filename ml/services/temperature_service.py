from pathlib import Path

import joblib
import pandas as pd


MODEL_FILE = Path(
    "models/weather/temperature_random_forest.joblib"
)

FEATURE_FILE = Path(
    "data/processed/weather/temperature_forecast_features.csv"
)


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


_model = None
_features = None


def load_model():
    global _model

    if _model is None:
        _model = joblib.load(MODEL_FILE)

    return _model


def load_features():
    global _features

    if _features is None:
        _features = pd.read_csv(FEATURE_FILE)

        _features["timestamp"] = pd.to_datetime(
            _features["timestamp"]
        )

    return _features


def predict_next_hour_temperature(
    location_code: str,
):
    df = load_features()

    location_code = location_code.upper()

    location_data = (
        df[df["location_code"] == location_code]
        .sort_values("timestamp")
        .reset_index(drop=True)
    )

    if location_data.empty:
        raise ValueError(
            f"No weather data found for location: {location_code}"
        )

    latest = location_data.iloc[-1]

    X = latest[FEATURES].to_frame().T

    model = load_model()

    prediction = model.predict(X)[0]

    return {
        "location_code": location_code,
        "timestamp": latest["timestamp"],
        "current_temperature_c": round(
            float(latest["temperature_2m"]),
            2,
        ),
        "predicted_next_hour_temperature_c": round(
            float(prediction),
            2,
        ),
    }