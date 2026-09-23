import numpy as np
import pandas as pd

from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error

from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Input, LSTM, Dense, Dropout
from tensorflow.keras.callbacks import EarlyStopping


# =========================================================
# Configuration
# =========================================================

INPUT_FILE = "data/processed/lstm_sequences_24h.npz"
OUTPUT_FILE = "data/processed/lstm_v2_results.csv"

EPOCHS = 100
BATCH_SIZE = 32
VALIDATION_RATIO = 0.20
RANDOM_SEED = 42


# =========================================================
# Metrics
# =========================================================

def calculate_metrics(y_true, y_pred):

    mae = mean_absolute_error(
        y_true,
        y_pred
    )

    rmse = mean_squared_error(
        y_true,
        y_pred
    ) ** 0.5

    return mae, rmse


# =========================================================
# Build model
# =========================================================

def build_model(
    timesteps,
    n_features
):

    model = Sequential([
        Input(
            shape=(
                timesteps,
                n_features
            )
        ),

        LSTM(
            64
        ),

        Dropout(
            0.2
        ),

        Dense(
            32,
            activation="relu"
        ),

        Dense(
            1
        )
    ])

    model.compile(
        optimizer="adam",
        loss="mse"
    )

    return model


# =========================================================
# Main
# =========================================================

def main():

    print("=" * 75)
    print("LSTM V2 - TIME-BASED VALIDATION + TARGET SCALING")
    print("=" * 75)

    np.random.seed(
        RANDOM_SEED
    )

    # -----------------------------------------------------
    # Load data
    # -----------------------------------------------------

    data = np.load(
        INPUT_FILE,
        allow_pickle=True
    )

    X_train_full = data["X_train"]
    y_train_full = data["y_train"]

    X_test = data["X_test"]
    y_test = data["y_test"]

    station_test = data["station_test"]

    print("\nLoaded data:")

    print(
        f"X_train: {X_train_full.shape}"
    )

    print(
        f"y_train: {y_train_full.shape}"
    )

    print(
        f"X_test:  {X_test.shape}"
    )

    print(
        f"y_test:  {y_test.shape}"
    )

    # -----------------------------------------------------
    # Time-based validation split
    # -----------------------------------------------------

    validation_start = int(
        len(X_train_full)
        * (1 - VALIDATION_RATIO)
    )

    X_train = X_train_full[
        :validation_start
    ]

    y_train = y_train_full[
        :validation_start
    ]

    X_val = X_train_full[
        validation_start:
    ]

    y_val = y_train_full[
        validation_start:
    ]

    print("\nTime-based split:")

    print(
        f"Training samples:   {len(X_train)}"
    )

    print(
        f"Validation samples: {len(X_val)}"
    )

    # -----------------------------------------------------
    # Dimensions
    # -----------------------------------------------------

    n_train = X_train.shape[0]
    n_val = X_val.shape[0]
    n_test = X_test.shape[0]

    timesteps = X_train.shape[1]
    n_features = X_train.shape[2]

    # -----------------------------------------------------
    # Scale X
    #
    # Fit ONLY on training data.
    # -----------------------------------------------------

    x_scaler = StandardScaler()

    X_train_flat = X_train.reshape(
        -1,
        n_features
    )

    X_val_flat = X_val.reshape(
        -1,
        n_features
    )

    X_test_flat = X_test.reshape(
        -1,
        n_features
    )

    x_scaler.fit(
        X_train_flat
    )

    X_train_scaled = x_scaler.transform(
        X_train_flat
    )

    X_val_scaled = x_scaler.transform(
        X_val_flat
    )

    X_test_scaled = x_scaler.transform(
        X_test_flat
    )

    X_train_scaled = X_train_scaled.reshape(
        n_train,
        timesteps,
        n_features
    )

    X_val_scaled = X_val_scaled.reshape(
        n_val,
        timesteps,
        n_features
    )

    X_test_scaled = X_test_scaled.reshape(
        n_test,
        timesteps,
        n_features
    )

    # -----------------------------------------------------
    # Scale target
    #
    # Fit ONLY on training targets.
    # -----------------------------------------------------

    y_scaler = StandardScaler()

    y_train_scaled = y_scaler.fit_transform(
        y_train.reshape(-1, 1)
    ).flatten()

    y_val_scaled = y_scaler.transform(
        y_val.reshape(-1, 1)
    ).flatten()

    # -----------------------------------------------------
    # Build model
    # -----------------------------------------------------

    model = build_model(
        timesteps,
        n_features
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

    model.fit(
        X_train_scaled,
        y_train_scaled,

        validation_data=(
            X_val_scaled,
            y_val_scaled
        ),

        epochs=EPOCHS,
        batch_size=BATCH_SIZE,

        callbacks=[
            early_stopping
        ],

        shuffle=False,
        verbose=1
    )

    # -----------------------------------------------------
    # Predict
    # -----------------------------------------------------

    predictions_scaled = model.predict(
        X_test_scaled,
        verbose=0
    ).flatten()

    # Convert predictions back
    # to original units.
    predictions = y_scaler.inverse_transform(
        predictions_scaled.reshape(-1, 1)
    ).flatten()

    # -----------------------------------------------------
    # Overall evaluation
    # -----------------------------------------------------

    overall_mae, overall_rmse = calculate_metrics(
        y_test,
        predictions
    )

    print("\n" + "=" * 75)
    print("OVERALL TEST PERFORMANCE")
    print("=" * 75)

    print(
        f"MAE  = {overall_mae:.6f}"
    )

    print(
        f"RMSE = {overall_rmse:.6f}"
    )

    # -----------------------------------------------------
    # Station-level evaluation
    # -----------------------------------------------------

    results = []

    for station_id in sorted(
        np.unique(station_test)
    ):

        mask = (
            station_test == station_id
        )

        station_y = y_test[
            mask
        ]

        station_predictions = predictions[
            mask
        ]

        mae, rmse = calculate_metrics(
            station_y,
            station_predictions
        )

        print(
            f"\nStation {station_id}"
        )

        print(
            f"MAE  = {mae:.6f}"
        )

        print(
            f"RMSE = {rmse:.6f}"
        )

        results.append({
            "station_id": station_id,
            "model": "LSTM_V2",
            "mae": mae,
            "rmse": rmse,
            "test_rows": len(station_y)
        })

    # -----------------------------------------------------
    # Save
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
    