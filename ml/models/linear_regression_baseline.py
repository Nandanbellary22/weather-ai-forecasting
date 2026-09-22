import pandas as pd

from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error


INPUT_FILE = "data/processed/forecast_features.csv"


FEATURE_COLUMNS = [
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

TARGET_COLUMN = "target_next_hour"


def main():

    print("Loading feature dataset...")

    df = pd.read_csv(
        INPUT_FILE,
        parse_dates=["timestamp"]
    )

    # Make sure the data is in chronological order
    df = (
        df
        .sort_values(["timestamp", "station_id"])
        .reset_index(drop=True)
    )

    print(f"Total rows: {len(df)}")

    # ---------------------------------------------------------
    # Chronological train/test split
    # ---------------------------------------------------------

    split_index = int(len(df) * 0.80)

    train = df.iloc[:split_index].copy()
    test = df.iloc[split_index:].copy()

    print()
    print("=" * 60)
    print("TIME-SERIES TRAIN / TEST SPLIT")
    print("=" * 60)

    print(f"Training rows: {len(train)}")
    print(f"Testing rows:  {len(test)}")

    print()
    print(
        f"Training period: "
        f"{train['timestamp'].min()} -> "
        f"{train['timestamp'].max()}"
    )

    print(
        f"Testing period:  "
        f"{test['timestamp'].min()} -> "
        f"{test['timestamp'].max()}"
    )

    # ---------------------------------------------------------
    # Prepare X and y
    # ---------------------------------------------------------

    X_train = train[FEATURE_COLUMNS]
    y_train = train[TARGET_COLUMN]

    X_test = test[FEATURE_COLUMNS]
    y_test = test[TARGET_COLUMN]

    print()
    print("--- Features ---")
    print(FEATURE_COLUMNS)

    # ---------------------------------------------------------
    # Train Linear Regression
    # ---------------------------------------------------------

    print()
    print("=" * 60)
    print("TRAINING LINEAR REGRESSION")
    print("=" * 60)

    model = LinearRegression()

    model.fit(
        X_train,
        y_train
    )

    # ---------------------------------------------------------
    # Predictions
    # ---------------------------------------------------------

    predictions = model.predict(X_test)

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
    print("MODEL RESULTS")
    print("=" * 60)

    print(f"MAE:  {mae:.6f}")
    print(f"RMSE: {rmse:.6f}")

    # ---------------------------------------------------------
    # Show sample predictions
    # ---------------------------------------------------------

    results = test[
        [
            "station_id",
            "timestamp",
            "value",
            TARGET_COLUMN,
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