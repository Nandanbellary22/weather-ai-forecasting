from pathlib import Path

import joblib
import pandas as pd
from sklearn.linear_model import LinearRegression


FEATURE_FILE = Path(
    "data/processed/weather/rainfall_forecast_features.csv"
)

MODEL_DIR = Path("models/weather")
MODEL_FILE = MODEL_DIR / "rainfall_linear_regression.joblib"


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
    "precipitation_lag_1h",
    "precipitation_lag_3h",
    "precipitation_lag_6h",
    "precipitation_lag_12h",
    "precipitation_lag_24h",
    "temperature_2m_lag_1h",
    "relative_humidity_2m_lag_1h",
    "surface_pressure_hpa_lag_1h",
    "wind_speed_10m_lag_1h",
    "cloud_cover_lag_1h",
    "precipitation_rolling_sum_3h",
    "precipitation_rolling_mean_3h",
    "precipitation_rolling_sum_6h",
    "precipitation_rolling_mean_6h",
    "precipitation_rolling_sum_12h",
    "precipitation_rolling_mean_12h",
    "precipitation_rolling_sum_24h",
    "precipitation_rolling_mean_24h",
]


def main():
    print("Loading rainfall forecasting dataset...")

    df = pd.read_csv(FEATURE_FILE)

    df["timestamp"] = pd.to_datetime(
        df["timestamp"]
    )

    print(f"Rows: {len(df)}")
    print(
        f"Locations: {df['location_code'].nunique()}"
    )

    # --------------------------------------------
    # Chronological 80/20 split per location
    # --------------------------------------------

    train_parts = []

    for location, group in df.groupby(
        "location_code"
    ):
        group = (
            group
            .sort_values("timestamp")
            .reset_index(drop=True)
        )

        split_index = int(len(group) * 0.8)

        train_parts.append(
            group.iloc[:split_index]
        )

    train = pd.concat(
        train_parts
    ).reset_index(drop=True)

    X_train = train[FEATURES]
    y_train = train["target_next_hour"]

    print(
        f"Training rows: {len(train)}"
    )

    # --------------------------------------------
    # Train Linear Regression
    # --------------------------------------------

    print()
    print("Training Linear Regression...")

    model = LinearRegression()

    model.fit(
        X_train,
        y_train,
    )

    # --------------------------------------------
    # Save model
    # --------------------------------------------

    MODEL_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    joblib.dump(
        model,
        MODEL_FILE,
    )

    print()
    print("Rainfall model saved successfully.")
    print(
        f"Model file: {MODEL_FILE}"
    )


if __name__ == "__main__":
    main()