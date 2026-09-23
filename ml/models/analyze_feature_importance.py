import pandas as pd

from sklearn.ensemble import RandomForestRegressor


# =========================================================
# Configuration
# =========================================================

INPUT_FILE = "data/processed/forecast_features.csv"

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
# Main
# =========================================================

def main():

    print("=" * 65)
    print("RANDOM FOREST FEATURE IMPORTANCE ANALYSIS")
    print("=" * 65)

    # -----------------------------------------------------
    # Load data
    # -----------------------------------------------------

    df = pd.read_csv(INPUT_FILE)

    df["timestamp"] = pd.to_datetime(
        df["timestamp"]
    )

    df = df.sort_values(
        ["station_id", "timestamp"]
    ).reset_index(drop=True)

    print(f"\nTotal rows: {len(df)}")
    print(
        f"Stations: "
        f"{df['station_id'].unique().tolist()}"
    )

    # -----------------------------------------------------
    # Analyze each station separately
    # -----------------------------------------------------

    for station_id in sorted(df["station_id"].unique()):

        print("\n" + "-" * 65)
        print(f"STATION {station_id}")
        print("-" * 65)

        station_df = df[
            df["station_id"] == station_id
        ].copy()

        station_df = station_df.sort_values(
            "timestamp"
        ).reset_index(drop=True)

        # -------------------------------------------------
        # Chronological 80/20 split
        # -------------------------------------------------

        train_size = int(
            len(station_df) * 0.80
        )

        train = station_df.iloc[:train_size]
        test = station_df.iloc[train_size:]

        X_train = train[FEATURES]
        y_train = train[TARGET]

        # -------------------------------------------------
        # Random Forest
        # -------------------------------------------------

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

        # -------------------------------------------------
        # Feature importance
        # -------------------------------------------------

        importance_df = pd.DataFrame({
            "feature": FEATURES,
            "importance": model.feature_importances_
        })

        importance_df = importance_df.sort_values(
            "importance",
            ascending=False
        ).reset_index(drop=True)

        print("\nFeature importance:")

        for _, row in importance_df.iterrows():

            print(
                f"{row['feature']:20s} "
                f"{row['importance']:.6f} "
                f"({row['importance'] * 100:.2f}%)"
            )

        # -------------------------------------------------
        # Top 5
        # -------------------------------------------------

        print("\nTop 5 features:")

        for i, row in importance_df.head(5).iterrows():

            print(
                f"{i + 1}. "
                f"{row['feature']} "
                f"-> "
                f"{row['importance'] * 100:.2f}%"
            )


# =========================================================
# Run
# =========================================================

if __name__ == "__main__":
    main()