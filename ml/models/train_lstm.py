import numpy as np
import pandas as pd

from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error

from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout
from tensorflow.keras.callbacks import EarlyStopping


# =========================================================
# Configuration
# =========================================================

INPUT_FILE = "data/processed/lstm_sequences_24h.npz"
OUTPUT_FILE = "data/processed/lstm_results.csv"

EPOCHS = 100
BATCH_SIZE = 32
RANDOM_SEED = 42


# =========================================================
# Main
# =========================================================

def main():

    print("=" * 75)
    print("LSTM NEXT-HOUR FORECASTING")
    print("=" * 75)

    np.random.seed(RANDOM_SEED)

    # -----------------------------------------------------
    # Load sequences
    # -----------------------------------------------------

    data = np.load(
        INPUT_FILE,
        allow_pickle=True
    )

    X_train = data["X_train"]
    y_train = data["y_train"]

    X_test = data["X_test"]
    y_test = data["y_test"]

    station_train = data["station_train"]
    station_test = data["station_test"]

    print("\nLoaded data:")
    print(f"X_train: {X_train.shape}")
    print(f"y_train: {y_train.shape}")
    print(f"X_test:  {X_test.shape}")
    print(f"y_test:  {y_test.shape}")

    # -----------------------------------------------------
    # Scale input features
    #
    # IMPORTANT:
    # Fit scaler ONLY on training data.
    # -----------------------------------------------------

    n_train_samples = X_train.shape[0]
    n_test_samples = X_test.shape[0]

    n_timesteps = X_train.shape[1]
    n_features = X_train.shape[2]

    scaler = StandardScaler()

    # Flatten time dimension temporarily
    X_train_flat = X_train.reshape(
        -1,
        n_features
    )

    X_test_flat = X_test.reshape(
        -1,
        n_features
    )

    # Fit ONLY on training data
    scaler.fit(
        X_train_flat
    )

    X_train_scaled = scaler.transform(
        X_train_flat
    )

    X_test_scaled = scaler.transform(
        X_test_flat
    )

    # Restore sequence shape
    X_train_scaled = X_train_scaled.reshape(
        n_train_samples,
        n_timesteps,
        n_features
    )

    X_test_scaled = X_test_scaled.reshape(
        n_test_samples,
        n_timesteps,
        n_features
    )

    # -----------------------------------------------------
    # Build LSTM model
    # -----------------------------------------------------

    model = Sequential([
        LSTM(
            64,
            input_shape=(
                n_timesteps,
                n_features
            )
        ),

        Dropout(0.2),

        Dense(32, activation="relu"),

        Dense(1)
    ])

    model.compile(
        optimizer="adam",
        loss="mse"
    )

    print("\nModel:")
    model.summary()

    # -----------------------------------------------------
    # Early stopping
    # -----------------------------------------------------

    early_stopping = EarlyStopping(
        monitor="val_loss",
        patience=10,
        restore_best_weights=True
    )

    # -----------------------------------------------------
    # Train
    # -----------------------------------------------------

    print("\n" + "=" * 75)
    print("TRAINING")
    print("=" * 75)

    history = model.fit(
        X_train_scaled,
        y_train,
        validation_split=0.2,
        epochs=EPOCHS,
        batch_size=BATCH_SIZE,
        callbacks=[early_stopping],
        shuffle=False,
        verbose=1
    )

    # -----------------------------------------------------
    # Predict
    # -----------------------------------------------------

    print("\n" + "=" * 75)
    print("EVALUATION")
    print("=" * 75)

    predictions = model.predict(
        X_test_scaled,
        verbose=0
    ).flatten()

    # -----------------------------------------------------
    # Overall metrics
    # -----------------------------------------------------

    mae = mean_absolute_error(
        y_test,
        predictions
    )

    rmse = mean_squared_error(
        y_test,
        predictions
    ) ** 0.5

    print("\nOverall LSTM performance:")
    print(
        f"MAE  = {mae:.6f}"
    )

    print(
        f"RMSE = {rmse:.6f}"
    )

    # -----------------------------------------------------
    # Station-level metrics
    # -----------------------------------------------------

    results = []

    for station_id in sorted(
        np.unique(station_test)
    ):

        mask = (
            station_test == station_id
        )

        station_y = y_test[mask]

        station_predictions = predictions[
            mask
        ]

        station_mae = mean_absolute_error(
            station_y,
            station_predictions
        )

        station_rmse = mean_squared_error(
            station_y,
            station_predictions
        ) ** 0.5

        results.append({
            "station_id": station_id,
            "model": "LSTM",
            "mae": station_mae,
            "rmse": station_rmse,
            "test_rows": len(station_y)
        })

        print(
            f"\nStation {station_id}"
        )

        print(
            f"MAE  = {station_mae:.6f}"
        )

        print(
            f"RMSE = {station_rmse:.6f}"
        )

    # -----------------------------------------------------
    # Save results
    # -----------------------------------------------------

    results_df = pd.DataFrame(
        results
    )

    results_df.to_csv(
        OUTPUT_FILE,
        index=False
    )

    print("\n" + "=" * 75)
    print("RESULTS SAVED")
    print("=" * 75)

    print(
        OUTPUT_FILE
    )


# =========================================================
# Run
# =========================================================

if __name__ == "__main__":
    main()