import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error


# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

INPUT_FILE = "data/processed/forecast_features_90days.csv"
OUTPUT_FILE = "data/processed/station_model_results_90days.csv"

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


# ---------------------------------------------------------
# Evaluation helper
# ---------------------------------------------------------

def calculate_metrics(y_true, y_pred):
    mae = mean_absolute_error(y_true, y_pred)

    mse = mean_squared_error(y_true, y_pred)
    rmse = mse ** 0.5

    return mae, rmse


# ---------------------------------------------------------
# Main evaluation
# ---------------------------------------------------------

def main():

    print("=" * 60)
    print("90-DAY STATION-LEVEL MODEL EVALUATION")
    print("=" * 60)

    # Load 90-day feature dataset
    df = pd.read_csv(INPUT_FILE)

    df["timestamp"] = pd.to_datetime(df["timestamp"])

    # Sort chronologically
    df = df.sort_values(
        ["station_id", "timestamp"]
    ).reset_index(drop=True)

    print(f"\nInput rows: {len(df)}")
    print(f"Stations: {df['station_id'].unique().tolist()}")

    results = []

    # -----------------------------------------------------
    # Evaluate each station separately
    # -----------------------------------------------------

    for station_id in sorted(df["station_id"].unique()):

        print("\n" + "-" * 60)
        print(f"Station: {station_id}")
        print("-" * 60)

        station_df = df[
            df["station_id"] == station_id
        ].copy()

        station_df = station_df.sort_values(
            "timestamp"
        ).reset_index(drop=True)

        total_rows = len(station_df)

        # Chronological 80/20 split
        train_size = int(total_rows * 0.80)

        train = station_df.iloc[:train_size].copy()
        test = station_df.iloc[train_size:].copy()

        print(f"Total rows: {total_rows}")
        print(f"Training rows: {len(train)}")
        print(f"Testing rows: {len(test)}")

        print(
            f"Training period: "
            f"{train['timestamp'].min()} -> "
            f"{train['timestamp'].max()}"
        )

        print(
            f"Testing period: "
            f"{test['timestamp'].min()} -> "
            f"{test['timestamp'].max()}"
        )

        # -------------------------------------------------
        # Prepare ML data
        # -------------------------------------------------

        X_train = train[FEATURES]
        y_train = train[TARGET]

        X_test = test[FEATURES]
        y_test = test[TARGET]

        # -------------------------------------------------
        # 1. Persistence baseline
        # -------------------------------------------------
        #
        # next-hour prediction = current value
        # -------------------------------------------------

        persistence_predictions = test["value"].values

        persistence_mae, persistence_rmse = calculate_metrics(
            y_test,
            persistence_predictions
        )

        print("\nPersistence")
        print(f"MAE : {persistence_mae:.6f}")
        print(f"RMSE: {persistence_rmse:.6f}")

        results.append({
            "station_id": station_id,
            "model": "Persistence",
            "train_rows": len(train),
            "test_rows": len(test),
            "mae": persistence_mae,
            "rmse": persistence_rmse
        })

        # -------------------------------------------------
        # 2. Linear Regression
        # -------------------------------------------------

        linear_model = LinearRegression()

        linear_model.fit(
            X_train,
            y_train
        )

        linear_predictions = linear_model.predict(
            X_test
        )

        linear_mae, linear_rmse = calculate_metrics(
            y_test,
            linear_predictions
        )

        print("\nLinear Regression")
        print(f"MAE : {linear_mae:.6f}")
        print(f"RMSE: {linear_rmse:.6f}")

        results.append({
            "station_id": station_id,
            "model": "Linear Regression",
            "train_rows": len(train),
            "test_rows": len(test),
            "mae": linear_mae,
            "rmse": linear_rmse
        })

        # -------------------------------------------------
        # 3. Random Forest
        # -------------------------------------------------

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

        rf_mae, rf_rmse = calculate_metrics(
            y_test,
            rf_predictions
        )

        print("\nRandom Forest")
        print(f"MAE : {rf_mae:.6f}")
        print(f"RMSE: {rf_rmse:.6f}")

        results.append({
            "station_id": station_id,
            "model": "Random Forest",
            "train_rows": len(train),
            "test_rows": len(test),
            "mae": rf_mae,
            "rmse": rf_rmse
        })

    # -----------------------------------------------------
    # Save results
    # -----------------------------------------------------

    results_df = pd.DataFrame(results)

    print("\n" + "=" * 60)
    print("90-DAY FINAL RESULTS")
    print("=" * 60)

    print(results_df.to_string(index=False))

    results_df.to_csv(
        OUTPUT_FILE,
        index=False
    )

    print("\nResults saved to:")
    print(OUTPUT_FILE)


# ---------------------------------------------------------
# Run
# ---------------------------------------------------------

if __name__ == "__main__":
    main()