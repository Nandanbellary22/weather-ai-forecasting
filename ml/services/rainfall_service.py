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
    / "rainfall_500_model.joblib"
)

FEATURE_FILE = (
    BASE_DIR
    / "data"
    / "processed"
    / "weather_features"
    / "rainfall_features_500.csv"
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
                f"Rainfall model not found: "
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
                f"Rainfall feature file not found: "
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

def predict_next_hour_rainfall(
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
            f"No rainfall data found for "
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
    # Use exact features used during training
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
            "Rainfall model does not contain "
            "feature metadata."
        )

    missing_features = [
        column
        for column in features
        if column not in latest.index
    ]

    if missing_features:

        raise ValueError(
            "Missing rainfall model features: "
            + ", ".join(missing_features)
        )

    X = latest[
        features
    ].to_frame().T

    # --------------------------------------------------------
    # Prediction
    # --------------------------------------------------------

    prediction = model.predict(X)[0]

    # Rainfall cannot be negative.
    prediction = max(
        0.0,
        float(prediction),
    )

    # --------------------------------------------------------
    # Response
    # --------------------------------------------------------

    return {
        "location_code": location_code,
        "timestamp": latest["timestamp"],
        "current_rainfall_mm": round(
            float(
                latest["precipitation_mm"]
            ),
            3,
        ),
        "predicted_next_hour_rainfall_mm": round(
            prediction,
            3,
        ),
        "model": "Random Forest",
    }