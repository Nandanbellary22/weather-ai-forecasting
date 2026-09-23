import pandas as pd

from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error


# =========================================================
# Configuration
# =========================================================

ORIGINAL_FILE = "data/processed/forecast_features_90days.csv"
ENHANCED_FILE = "data/processed/enhanced_forecast_features.csv"

OUTPUT_FILE = "data/processed/original_vs_enhanced_results.csv"

TEST_START = pd.Timestamp("2026-07-08 04:00:00")
TEST_END = pd.Timestamp("2026-07-13 22:00:00")


# Original feature set
ORIGINAL_FEATURES = [
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


# Enhanced feature set
ENHANCED_FEATURES = [
    "hour",
    "day_of_week",
    "day_of_month",

    "lag_1",
    "lag_2",
    "lag_3",
    "lag_4",
    "lag_6",
    "lag_8",
    "lag_12",
    "lag_18",
    "lag_24",
    "lag_36",
    "lag_48",
    "lag_72",

    "rolling_mean_3",
    "rolling_mean_6",
    "rolling_mean_12",
    "rolling_mean_24",
    "rolling_mean_48",
    "rolling_mean_72",
]


TARGET = "target_next_hour"


# =========================================================
# Metrics
# =========================================================

def calculate_metrics(y_true, y_pred):

    mae = mean_absolute_error(
        y_true,
        y_pred
    )

    mse = mean_squared_error(
        y_true,
        y_pred
    )

    rmse = mse ** 0.5

    return mae, rmse


# =========================================================
# Load dataset
# =========================================================

def load_dataset(file_path):

    df = pd.read_csv(file_path)

    df["timestamp"] = pd.to_datetime(
        df["timestamp"]
    )

    df = df.sort_values(
        ["station_id", "timestamp"]
    ).reset_index(drop=True)

    return df


# =========================================================
# Evaluate model
# =========================================================

def evaluate_model(
    train,
    test,
    features,
    model_name,
    station_id,
    feature_set
):

    X_train = train[features]
    y_train = train[TARGET]

    X_test = test[features]
    y_test = test[TARGET]

    # -----------------------------------------------------
    # Linear Regression
    # -----------------------------------------------------

    if model_name == "Linear Regression":

        model = LinearRegression()

        model.fit(
            X_train,
            y_train
        )

        predictions = model.predict(
            X_test
        )

    # -----------------------------------------------------
    # Random Forest
    # -----------------------------------------------------

    elif model_name == "Random Forest":

        model = RandomForestRegressor(
            n_estimators=200,
            max_depth=10,
            random_state=42,
            n_jobs=-1
        )

        model.fit(
            X_train,
            y_train
        )

        predictions = model.predict(
            X_test
        )

    else:
        raise ValueError(
            f"Unknown model: {model_name}"
        )

    mae, rmse = calculate_metrics(
        y_test,
        predictions
    )

    return {
        "feature_set": feature_set,
        "station_id": station_id,
        "model": model_name,
        "train_rows": len(train),
        "test_rows": len(test),
        "mae": mae,
        "rmse": rmse,
    }


# =========================================================
# Main
# =========================================================

def main():

    print("=" * 75)
    print("ORIGINAL VS ENHANCED FEATURE COMPARISON")
    print("=" * 75)

    print("\nCommon test period:")
    print(
        f"{TEST_START} -> {TEST_END}"
    )

    # -----------------------------------------------------
    # Load both datasets
    # -----------------------------------------------------

    original = load_dataset(
        ORIGINAL_FILE
    )

    enhanced = load_dataset(
        ENHANCED_FILE
    )

    print("\nOriginal dataset rows:")
    print(len(original))

    print("\nEnhanced dataset rows:")
    print(len(enhanced))

    results = []

    # -----------------------------------------------------
    # Evaluate each station
    # -----------------------------------------------------

    for station_id in sorted(
        original["station_id"].unique()
    ):

        print("\n" + "-" * 75)
        print(f"STATION {station_id}")
        print("-" * 75)

        # =================================================
        # ORIGINAL FEATURES
        # =================================================

        original_station = original[
            original["station_id"] == station_id
        ].copy()

        original_station = original_station.sort_values(
            "timestamp"
        )

        # Common test period
        original_test = original_station[
            (original_station["timestamp"] >= TEST_START)
            & (original_station["timestamp"] <= TEST_END)
        ].copy()

        # Training data before test period
        original_train = original_station[
            original_station["timestamp"] < TEST_START
        ].copy()

        print("\nOriginal feature set")

        print(
            f"Training rows: "
            f"{len(original_train)}"
        )

        print(
            f"Test rows: "
            f"{len(original_test)}"
        )

        # -------------------------------------------------
        # Original Linear Regression
        # -------------------------------------------------

        result = evaluate_model(
            original_train,
            original_test,
            ORIGINAL_FEATURES,
            "Linear Regression",
            station_id,
            "Original"
        )

        results.append(result)

        print(
            f"Linear Regression | "
            f"MAE={result['mae']:.6f} | "
            f"RMSE={result['rmse']:.6f}"
        )

        # -------------------------------------------------
        # Original Random Forest
        # -------------------------------------------------

        result = evaluate_model(
            original_train,
            original_test,
            ORIGINAL_FEATURES,
            "Random Forest",
            station_id,
            "Original"
        )

        results.append(result)

        print(
            f"Random Forest     | "
            f"MAE={result['mae']:.6f} | "
            f"RMSE={result['rmse']:.6f}"
        )

        # =================================================
        # ENHANCED FEATURES
        # =================================================

        enhanced_station = enhanced[
            enhanced["station_id"] == station_id
        ].copy()

        enhanced_station = enhanced_station.sort_values(
            "timestamp"
        )

        # Common test period
        enhanced_test = enhanced_station[
            (enhanced_station["timestamp"] >= TEST_START)
            & (enhanced_station["timestamp"] <= TEST_END)
        ].copy()

        # Training data before test period
        enhanced_train = enhanced_station[
            enhanced_station["timestamp"] < TEST_START
        ].copy()

        print("\nEnhanced feature set")

        print(
            f"Training rows: "
            f"{len(enhanced_train)}"
        )

        print(
            f"Test rows: "
            f"{len(enhanced_test)}"
        )

        # -------------------------------------------------
        # Enhanced Linear Regression
        # -------------------------------------------------

        result = evaluate_model(
            enhanced_train,
            enhanced_test,
            ENHANCED_FEATURES,
            "Linear Regression",
            station_id,
            "Enhanced"
        )

        results.append(result)

        print(
            f"Linear Regression | "
            f"MAE={result['mae']:.6f} | "
            f"RMSE={result['rmse']:.6f}"
        )

        # -------------------------------------------------
        # Enhanced Random Forest
        # -------------------------------------------------

        result = evaluate_model(
            enhanced_train,
            enhanced_test,
            ENHANCED_FEATURES,
            "Random Forest",
            station_id,
            "Enhanced"
        )

        results.append(result)

        print(
            f"Random Forest     | "
            f"MAE={result['mae']:.6f} | "
            f"RMSE={result['rmse']:.6f}"
        )

    # =====================================================
    # Results
    # =====================================================

    results_df = pd.DataFrame(
        results
    )

    print("\n" + "=" * 75)
    print("FINAL RESULTS")
    print("=" * 75)

    print(
        results_df.to_string(
            index=False
        )
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