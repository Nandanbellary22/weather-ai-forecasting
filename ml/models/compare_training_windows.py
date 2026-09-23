import pandas as pd

from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error


# =========================================================
# Configuration
# =========================================================

FILE_30_DAYS = "data/processed/forecast_features.csv"
FILE_90_DAYS = "data/processed/forecast_features_90days.csv"

OUTPUT_FILE = "data/processed/training_window_comparison.csv"

# Common test period
TEST_START = pd.Timestamp("2026-07-08 04:00:00")
TEST_END = pd.Timestamp("2026-07-13 22:00:00")

FEATURES = [
    "hour",
    "day_of_week",
    "day_of_month",
    "lag_1",
    "lag_3",
    "lag_6",
    "lag_12",
    "lag_24",
    "rolling_mean_3",
    "rolling_mean_6",
    "rolling_mean_24",
]

TARGET = "target_next_hour"


# =========================================================
# Metrics
# =========================================================

def calculate_metrics(y_true, y_pred):

    mae = mean_absolute_error(y_true, y_pred)

    mse = mean_squared_error(y_true, y_pred)
    rmse = mse ** 0.5

    return mae, rmse


# =========================================================
# Prepare dataset
# =========================================================

def prepare_data(file_path):

    df = pd.read_csv(file_path)

    df["timestamp"] = pd.to_datetime(df["timestamp"])

    df = df.sort_values(
        ["station_id", "timestamp"]
    ).reset_index(drop=True)

    return df


# =========================================================
# Evaluate one model
# =========================================================

def evaluate_models(
    train,
    test,
    station_id,
    training_window
):

    X_train = train[FEATURES]
    y_train = train[TARGET]

    X_test = test[FEATURES]
    y_test = test[TARGET]

    results = []

    # -----------------------------------------------------
    # Persistence
    # -----------------------------------------------------
    #
    # Prediction for next hour = current value
    # -----------------------------------------------------

    persistence_predictions = test["value"].values

    mae, rmse = calculate_metrics(
        y_test,
        persistence_predictions
    )

    results.append({
        "training_window": training_window,
        "station_id": station_id,
        "model": "Persistence",
        "train_rows": len(train),
        "test_rows": len(test),
        "mae": mae,
        "rmse": rmse
    })

    # -----------------------------------------------------
    # Linear Regression
    # -----------------------------------------------------

    linear_model = LinearRegression()

    linear_model.fit(
        X_train,
        y_train
    )

    linear_predictions = linear_model.predict(
        X_test
    )

    mae, rmse = calculate_metrics(
        y_test,
        linear_predictions
    )

    results.append({
        "training_window": training_window,
        "station_id": station_id,
        "model": "Linear Regression",
        "train_rows": len(train),
        "test_rows": len(test),
        "mae": mae,
        "rmse": rmse
    })

    # -----------------------------------------------------
    # Random Forest
    # -----------------------------------------------------

    rf_model = RandomForestRegressor(
        n_estimators=200,
        max_depth=10,
        random_state=42,
        n_jobs=-1
    )

    rf_model.fit(
        X_train,
        y_train
    )

    rf_predictions = rf_model.predict(
        X_test
    )

    mae, rmse = calculate_metrics(
        y_test,
        rf_predictions
    )

    results.append({
        "training_window": training_window,
        "station_id": station_id,
        "model": "Random Forest",
        "train_rows": len(train),
        "test_rows": len(test),
        "mae": mae,
        "rmse": rmse
    })

    return results


# =========================================================
# Main
# =========================================================

def main():

    print("=" * 70)
    print("30-DAY VS 90-DAY TRAINING WINDOW COMPARISON")
    print("=" * 70)

    print("\nCommon test period:")
    print(f"{TEST_START} -> {TEST_END}")

    # -----------------------------------------------------
    # Load datasets
    # -----------------------------------------------------

    df_30 = prepare_data(FILE_30_DAYS)
    df_90 = prepare_data(FILE_90_DAYS)

    print("\n30-day dataset:")
    print(f"Rows: {len(df_30)}")

    print("\n90-day dataset:")
    print(f"Rows: {len(df_90)}")

    results = []

    # -----------------------------------------------------
    # Evaluate each station
    # -----------------------------------------------------

    for station_id in sorted(df_30["station_id"].unique()):

        print("\n" + "-" * 70)
        print(f"STATION {station_id}")
        print("-" * 70)

        # =================================================
        # 30-DAY TRAINING WINDOW
        # =================================================

        station_30 = df_30[
            df_30["station_id"] == station_id
        ].copy()

        station_30 = station_30.sort_values(
            "timestamp"
        )

        # Test period
        test_30 = station_30[
            (station_30["timestamp"] >= TEST_START)
            & (station_30["timestamp"] <= TEST_END)
        ].copy()

        # Everything before test period is training
        train_30 = station_30[
            station_30["timestamp"] < TEST_START
        ].copy()

        print("\n30-day training window")
        print(f"Training rows: {len(train_30)}")
        print(f"Test rows: {len(test_30)}")

        print(
            f"Training period: "
            f"{train_30['timestamp'].min()} -> "
            f"{train_30['timestamp'].max()}"
        )

        print(
            f"Test period: "
            f"{test_30['timestamp'].min()} -> "
            f"{test_30['timestamp'].max()}"
        )

        results.extend(
            evaluate_models(
                train_30,
                test_30,
                station_id,
                "30-day"
            )
        )

        # =================================================
        # 90-DAY TRAINING WINDOW
        # =================================================

        station_90 = df_90[
            df_90["station_id"] == station_id
        ].copy()

        station_90 = station_90.sort_values(
            "timestamp"
        )

        # Test period
        test_90 = station_90[
            (station_90["timestamp"] >= TEST_START)
            & (station_90["timestamp"] <= TEST_END)
        ].copy()

        # Everything before test period is training
        train_90 = station_90[
            station_90["timestamp"] < TEST_START
        ].copy()

        print("\n90-day training window")
        print(f"Training rows: {len(train_90)}")
        print(f"Test rows: {len(test_90)}")

        print(
            f"Training period: "
            f"{train_90['timestamp'].min()} -> "
            f"{train_90['timestamp'].max()}"
        )

        print(
            f"Test period: "
            f"{test_90['timestamp'].min()} -> "
            f"{test_90['timestamp'].max()}"
        )

        results.extend(
            evaluate_models(
                train_90,
                test_90,
                station_id,
                "90-day"
            )
        )

    # -----------------------------------------------------
    # Results
    # -----------------------------------------------------

    results_df = pd.DataFrame(results)

    print("\n" + "=" * 70)
    print("FINAL COMPARISON")
    print("=" * 70)

    print(
        results_df.to_string(index=False)
    )

    # -----------------------------------------------------
    # Save
    # -----------------------------------------------------

    results_df.to_csv(
        OUTPUT_FILE,
        index=False
    )

    print("\nResults saved to:")
    print(OUTPUT_FILE)


# =========================================================
# Run
# =========================================================

if __name__ == "__main__":
    main()