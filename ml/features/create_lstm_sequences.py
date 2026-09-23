import numpy as np
import pandas as pd


# =========================================================
# Configuration
# =========================================================

INPUT_FILE = "data/processed/historical_90days_all_stations.csv"
OUTPUT_FILE = "data/processed/lstm_sequences_24h.npz"

SEQUENCE_LENGTH = 24
TEST_START = pd.Timestamp("2026-07-08 04:00:00")
TEST_END = pd.Timestamp("2026-07-13 22:00:00")


# =========================================================
# Main
# =========================================================

def main():

    print("=" * 75)
    print("CREATING LSTM 24-HOUR SEQUENCES")
    print("=" * 75)

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

    # -----------------------------------------------------
    # Features
    #
    # For the first LSTM experiment we use:
    #
    # value
    # hour
    # day_of_week
    # -----------------------------------------------------

    feature_columns = [
        "value",
        "hour",
        "day_of_week",
    ]

    # Create time features
    df["hour"] = df["timestamp"].dt.hour
    df["day_of_week"] = df["timestamp"].dt.dayofweek

    # -----------------------------------------------------
    # Storage
    # -----------------------------------------------------

    X_train_all = []
    y_train_all = []

    X_test_all = []
    y_test_all = []

    station_train_all = []
    station_test_all = []

    timestamp_train_all = []
    timestamp_test_all = []

    # -----------------------------------------------------
    # Process each station separately
    # -----------------------------------------------------

    for station_id in sorted(
        df["station_id"].unique()
    ):

        print("\n" + "-" * 75)
        print(f"STATION {station_id}")
        print("-" * 75)

        station_df = df[
            df["station_id"] == station_id
        ].copy()

        station_df = station_df.sort_values(
            "timestamp"
        ).reset_index(drop=True)

        values = station_df[
            feature_columns
        ].values.astype(np.float32)

        targets = station_df[
            "value"
        ].values.astype(np.float32)

        timestamps = station_df[
            "timestamp"
        ].values

        # -------------------------------------------------
        # Create sequences
        # -------------------------------------------------

        for i in range(
            SEQUENCE_LENGTH,
            len(station_df)
        ):

            sequence_start = i - SEQUENCE_LENGTH
            sequence_end = i

            X = values[
                sequence_start:sequence_end
            ]

            y = targets[i]

            target_timestamp = pd.Timestamp(
                timestamps[i]
            )

            # -------------------------------------------------
            # Training samples
            # -------------------------------------------------

            if target_timestamp < TEST_START:

                X_train_all.append(X)
                y_train_all.append(y)

                station_train_all.append(
                    station_id
                )

                timestamp_train_all.append(
                    target_timestamp
                )

            # -------------------------------------------------
            # Test samples
            # -------------------------------------------------

            elif (
                target_timestamp >= TEST_START
                and target_timestamp <= TEST_END
            ):

                X_test_all.append(X)
                y_test_all.append(y)

                station_test_all.append(
                    station_id
                )

                timestamp_test_all.append(
                    target_timestamp
                )

    # -----------------------------------------------------
    # Convert to NumPy arrays
    # -----------------------------------------------------

    X_train = np.array(
        X_train_all,
        dtype=np.float32
    )

    y_train = np.array(
        y_train_all,
        dtype=np.float32
    )

    X_test = np.array(
        X_test_all,
        dtype=np.float32
    )

    y_test = np.array(
        y_test_all,
        dtype=np.float32
    )

    station_train = np.array(
        station_train_all
    )

    station_test = np.array(
        station_test_all
    )

    timestamp_train = np.array(
        timestamp_train_all,
        dtype="datetime64[ns]"
    )

    timestamp_test = np.array(
        timestamp_test_all,
        dtype="datetime64[ns]"
    )

    # -----------------------------------------------------
    # Print shapes
    # -----------------------------------------------------

    print("\n" + "=" * 75)
    print("SEQUENCE DATASET")
    print("=" * 75)

    print(
        f"X_train shape: {X_train.shape}"
    )

    print(
        f"y_train shape: {y_train.shape}"
    )

    print(
        f"X_test shape: {X_test.shape}"
    )

    print(
        f"y_test shape: {y_test.shape}"
    )

    print(
        f"Training samples: {len(X_train)}"
    )

    print(
        f"Test samples: {len(X_test)}"
    )

    # -----------------------------------------------------
    # Save
    # -----------------------------------------------------

    np.savez_compressed(
        OUTPUT_FILE,
        X_train=X_train,
        y_train=y_train,
        X_test=X_test,
        y_test=y_test,
        station_train=station_train,
        station_test=station_test,
        timestamp_train=timestamp_train,
        timestamp_test=timestamp_test,
    )

    print("\nSaved:")
    print(OUTPUT_FILE)

    print("\nFeature order:")
    print(feature_columns)

    print("\nSequence length:")
    print(f"{SEQUENCE_LENGTH} hours")


# =========================================================
# Run
# =========================================================

if __name__ == "__main__":
    main()