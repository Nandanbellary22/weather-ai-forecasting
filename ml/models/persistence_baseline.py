import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error

INPUT_FILE = "data/processed/forecast_features.csv"

TARGET_COLUMN = "target_next_hour"


def main():
    print("Loading feature dataset...")

    df = pd.read_csv(
        INPUT_FILE,
        parse_dates=["timestamp"]
    )

    df = df.sort_values(
        ["timestamp", "station_id"]
    ).reset_index(drop=True)

    print(f"Total rows: {len(df)}")

    # ---------------------------------------------------------
    # Time-series train/test split
    # ---------------------------------------------------------

    split_index = int(len(df) * 0.80)

    train = df.iloc[:split_index].copy()
    test = df.iloc[split_index:].copy()

    print()
    print("=" * 60)
    print("TIME-SERIES TEST SET")
    print("=" * 60)

    print(f"Training rows: {len(train)}")
    print(f"Testing rows:  {len(test)}")

    print()
    print(
        f"Training period: "
        f"{train['timestamp'].min()} -> {train['timestamp'].max()}"
    )

    print(
        f"Testing period:  "
        f"{test['timestamp'].min()} -> {test['timestamp'].max()}"
    )

    # ---------------------------------------------------------
    # Persistence prediction
    #
    # Forecast next hour = current observed value
    # ---------------------------------------------------------

    y_test = test[TARGET_COLUMN]

    predictions = test["value"]

    # ---------------------------------------------------------
    # Evaluation
    # ---------------------------------------------------------

    mae = mean_absolute_error(
        y_test,
        predictions
    )

    rmse = mean_squared_error(
        y_test,
        predictions
    ) ** 0.5

    print()
    print("=" * 60)
    print("PERSISTENCE BASELINE RESULTS")
    print("=" * 60)

    print(f"MAE:  {mae:.6f}")
    print(f"RMSE: {rmse:.6f}")

    # ---------------------------------------------------------
    # Sample predictions
    # ---------------------------------------------------------

    results = test[
        [
            "station_id",
            "timestamp",
            "value",
            TARGET_COLUMN
        ]
    ].copy()

    results["prediction"] = predictions

    print()
    print("--- Sample Predictions ---")

    print(
        results.head(20).to_string(index=False)
    )


if __name__ == "__main__":
    main()