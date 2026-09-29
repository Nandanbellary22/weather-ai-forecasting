from pathlib import Path

import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error


FEATURE_FILE = Path(
    "data/processed/weather/rainfall_forecast_features.csv"
)

RESULT_FILE = Path(
    "data/processed/weather/rainfall_model_results.csv"
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


def calculate_metrics(y_true, y_pred):
    mae = mean_absolute_error(
        y_true,
        y_pred,
    )

    rmse = mean_squared_error(
        y_true,
        y_pred,
    ) ** 0.5

    return mae, rmse


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
    test_parts = []

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

        test_parts.append(
            group.iloc[split_index:]
        )

    train = pd.concat(
        train_parts
    ).reset_index(drop=True)

    test = pd.concat(
        test_parts
    ).reset_index(drop=True)

    print()
    print(f"Training rows: {len(train)}")
    print(f"Testing rows: {len(test)}")

    X_train = train[FEATURES]
    y_train = train["target_next_hour"]

    X_test = test[FEATURES]
    y_test = test["target_next_hour"]

    results = []

    # --------------------------------------------
    # Persistence baseline
    # --------------------------------------------

    print()
    print("Running Persistence baseline...")

    persistence_predictions = (
        test["precipitation_mm"]
    )

    mae, rmse = calculate_metrics(
        y_test,
        persistence_predictions,
    )

    results.append(
        {
            "model": "Persistence",
            "mae": mae,
            "rmse": rmse,
        }
    )

    print(
        f"Persistence MAE:  {mae:.6f}"
    )

    print(
        f"Persistence RMSE: {rmse:.6f}"
    )

    # --------------------------------------------
    # Linear Regression
    # --------------------------------------------

    print()
    print("Running Linear Regression...")

    linear_model = LinearRegression()

    linear_model.fit(
        X_train,
        y_train,
    )

    linear_predictions = (
        linear_model.predict(X_test)
    )

    mae, rmse = calculate_metrics(
        y_test,
        linear_predictions,
    )

    results.append(
        {
            "model": "Linear Regression",
            "mae": mae,
            "rmse": rmse,
        }
    )

    print(
        f"Linear Regression MAE:  {mae:.6f}"
    )

    print(
        f"Linear Regression RMSE: {rmse:.6f}"
    )

    # --------------------------------------------
    # Random Forest
    # --------------------------------------------

    print()
    print("Running Random Forest...")

    rf_model = RandomForestRegressor(
        n_estimators=200,
        max_depth=20,
        min_samples_leaf=2,
        random_state=42,
        n_jobs=-1,
    )

    rf_model.fit(
        X_train,
        y_train,
    )

    rf_predictions = (
        rf_model.predict(X_test)
    )

    mae, rmse = calculate_metrics(
        y_test,
        rf_predictions,
    )

    results.append(
        {
            "model": "Random Forest",
            "mae": mae,
            "rmse": rmse,
        }
    )

    print(
        f"Random Forest MAE:  {mae:.6f}"
    )

    print(
        f"Random Forest RMSE: {rmse:.6f}"
    )

    # --------------------------------------------
    # Save results
    # --------------------------------------------

    results_df = pd.DataFrame(
        results
    )

    results_df.to_csv(
        RESULT_FILE,
        index=False,
    )

    print()
    print("========================================")
    print("Rainfall Model Comparison")
    print("========================================")

    print(
        results_df.to_string(
            index=False
        )
    )

    print()
    print(
        f"Saved results to: {RESULT_FILE}"
    )


if __name__ == "__main__":
    main()