from pathlib import Path

import joblib
import pandas as pd


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parents[2]

MODEL_FILE = (
    BASE_DIR
    / "models"
    / "weather"
    / "temperature_500_model.joblib"
)

FEATURE_FILE = (
    BASE_DIR
    / "data"
    / "processed"
    / "weather_features"
    / "temperature_features_500.csv"
)


# ============================================================
# GLOBAL CACHE
# ============================================================

_model = None
_features = None


# ============================================================
# MODEL
# ============================================================

def load_model():

    global _model

    if _model is None:

        if not MODEL_FILE.exists():
            raise FileNotFoundError(
                f"Temperature model not found: "
                f"{MODEL_FILE}"
            )

        package = joblib.load(
            MODEL_FILE
        )

        # New 500-location training script
        # saves a dictionary containing the model.
        if isinstance(package, dict):

            _model = package["model"]

        else:

            # Backward compatibility
            _model = package

    return _model


# ============================================================
# FEATURES
# ============================================================

def load_features():

    global _features

    if _features is None:

        if not FEATURE_FILE.exists():
            raise FileNotFoundError(
                f"Temperature feature file not found: "
                f"{FEATURE_FILE}"
            )

        _features = pd.read_csv(
            FEATURE_FILE
        )

        _features["timestamp"] = pd.to_datetime(
            _features["timestamp"]
        )

    return _features


# ============================================================
# PREDICTION
# ============================================================

def predict_next_hour_temperature(
    location_code: str,
):

    location_code = (
        location_code
        .strip()
        .upper()
    )

    df = load_features()

    location_data = (
        df[
            df["location_code"]
            == location_code
        ]
        .sort_values("timestamp")
        .reset_index(drop=True)
    )

    if location_data.empty:

        raise ValueError(
            f"No weather data found for "
            f"location: {location_code}"
        )

    # --------------------------------------------------------
    # Latest feature row
    # --------------------------------------------------------

    latest = location_data.iloc[-1]

    # --------------------------------------------------------
    # Load model
    # --------------------------------------------------------

    model = load_model()

    # --------------------------------------------------------
    # Use the exact features used during training
    # --------------------------------------------------------

    if hasattr(
        model,
        "feature_names_in_",
    ):

        features = list(
            model.feature_names_in_
        )

    else:

        raise ValueError(
            "Temperature model does not contain "
            "feature metadata."
        )

    missing_features = [
        column
        for column in features
        if column not in latest.index
    ]

    if missing_features:

        raise ValueError(
            "Missing temperature model features: "
            + ", ".join(missing_features)
        )

    X = latest[
        features
    ].to_frame().T

    # --------------------------------------------------------
    # Prediction
    # --------------------------------------------------------

    prediction = model.predict(X)[0]

    # --------------------------------------------------------
    # Response
    # --------------------------------------------------------

    return {
        "location_code": location_code,
        "timestamp": latest["timestamp"],
        "current_temperature_c": round(
            float(
                latest["temperature_2m"]
            ),
            2,
        ),
        "predicted_next_hour_temperature_c": round(
            float(prediction),
            2,
        ),
        "model": "Random Forest",
    }