from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error


DATA_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "processed"
    / "historical_180days_all_stations.csv"
)


def load_data() -> pd.DataFrame:
    """Load and standardize the historical hydrology dataset."""

    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Dataset not found: {DATA_PATH}")

    df = pd.read_csv(DATA_PATH)

    required_columns = {"station_id", "timestamp", "value"}

    missing = required_columns - set(df.columns)

    if missing:
        raise ValueError(
            f"Dataset is missing required columns: {sorted(missing)}"
        )

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df["station_id"] = pd.to_numeric(
        df["station_id"], errors="coerce"
    ).astype("Int64")

    df = df.dropna(subset=["station_id", "timestamp"])
    df = df.sort_values(["station_id", "timestamp"])

    return df.reset_index(drop=True)


def create_features(
    station_df: pd.DataFrame,
    lags: tuple[int, ...] = (1, 3, 6, 12, 24),
) -> pd.DataFrame:
    """Create time-series features for one station."""

    df = station_df.copy()

    df = df.sort_values("timestamp").reset_index(drop=True)

    df["hour"] = df["timestamp"].dt.hour
    df["day_of_week"] = df["timestamp"].dt.dayofweek
    df["day_of_month"] = df["timestamp"].dt.day

    for lag in lags:
        df[f"lag_{lag}"] = df["value"].shift(lag)

    df["rolling_mean_6"] = df["value"].shift(1).rolling(6).mean()
    df["rolling_mean_12"] = df["value"].shift(1).rolling(12).mean()
    df["rolling_mean_24"] = df["value"].shift(1).rolling(24).mean()

    return df


def train_model(
    station_id: int,
    model_type: str = "random_forest",
) -> tuple[Any, list[str], dict[str, float]]:
    """
    Train a forecasting model for one station.

    The final 20% of observations are reserved as a time-ordered
    test set. No random shuffling is used.
    """

    df = load_data()

    station_df = df[df["station_id"] == station_id].copy()

    if station_df.empty:
        raise ValueError(f"No data found for station {station_id}")

    station_df = create_features(station_df)

    feature_columns = [
        "hour",
        "day_of_week",
        "day_of_month",
        "lag_1",
        "lag_3",
        "lag_6",
        "lag_12",
        "lag_24",
        "rolling_mean_6",
        "rolling_mean_12",
        "rolling_mean_24",
    ]

    model_df = station_df.dropna(
        subset=feature_columns + ["value"]
    ).copy()

    if len(model_df) < 100:
        raise ValueError(
            f"Insufficient training data for station {station_id}: "
            f"{len(model_df)} rows"
        )

    split_index = int(len(model_df) * 0.8)

    train_df = model_df.iloc[:split_index]
    test_df = model_df.iloc[split_index:]

    X_train = train_df[feature_columns]
    y_train = train_df["value"]

    X_test = test_df[feature_columns]
    y_test = test_df["value"]

    if model_type == "linear_regression":
        model = LinearRegression()

    elif model_type == "random_forest":
        model = RandomForestRegressor(
            n_estimators=200,
            random_state=42,
            n_jobs=-1,
            max_depth=None,
        )

    else:
        raise ValueError(
            "Unsupported model_type. "
            "Use 'random_forest' or 'linear_regression'."
        )

    model.fit(X_train, y_train)

    predictions = model.predict(X_test)

    mae = mean_absolute_error(y_test, predictions)

    rmse = mean_squared_error(
        y_test,
        predictions,
    ) ** 0.5

    metrics = {
        "mae": float(mae),
        "rmse": float(rmse),
        "train_rows": int(len(train_df)),
        "test_rows": int(len(test_df)),
    }

    return model, feature_columns, metrics


def forecast_next_24_hours(
    station_id: int,
    model_type: str = "random_forest",
) -> dict[str, Any]:
    """
    Train a model using historical observations and recursively
    forecast the next 24 hourly values.
    """

    df = load_data()

    station_df = df[df["station_id"] == station_id].copy()

    if station_df.empty:
        raise ValueError(f"No data found for station {station_id}")

    station_df = station_df.sort_values("timestamp").reset_index(drop=True)

    model, feature_columns, metrics = train_model(
        station_id=station_id,
        model_type=model_type,
    )

    history = station_df[
        ["timestamp", "value"]
    ].dropna(subset=["value"]).copy()

    if len(history) < 25:
        raise ValueError(
            f"Not enough observations for forecasting station {station_id}"
        )

    values = history["value"].tolist()

    last_timestamp = history["timestamp"].iloc[-1]

    forecasts = []

    for step in range(1, 25):
        forecast_timestamp = (
            last_timestamp + pd.Timedelta(hours=step)
        )

        recent_values = values

        row = {
            "hour": forecast_timestamp.hour,
            "day_of_week": forecast_timestamp.dayofweek,
            "day_of_month": forecast_timestamp.day,
            "lag_1": recent_values[-1],
            "lag_3": recent_values[-3],
            "lag_6": recent_values[-6],
            "lag_12": recent_values[-12],
            "lag_24": recent_values[-24],
            "rolling_mean_6": sum(recent_values[-6:]) / 6,
            "rolling_mean_12": sum(recent_values[-12:]) / 12,
            "rolling_mean_24": sum(recent_values[-24:]) / 24,
        }

        feature_df = pd.DataFrame(
            [row],
            columns=feature_columns,
        )

        prediction = float(model.predict(feature_df)[0])

        forecasts.append(
            {
                "station_id": station_id,
                "timestamp": forecast_timestamp.isoformat(),
                "predicted_value": prediction,
            }
        )

        values.append(prediction)

    return {
        "station_id": station_id,
        "model": model_type,
        "forecast_horizon_hours": 24,
        "last_observation": {
            "timestamp": history["timestamp"].iloc[-1].isoformat(),
            "value": float(history["value"].iloc[-1]),
        },
        "metrics": metrics,
        "forecasts": forecasts,
    }


def get_station_summary() -> list[dict[str, Any]]:
    """Return basic metadata for all available stations."""

    df = load_data()

    summaries = []

    for station_id, station_df in df.groupby("station_id"):
        numeric_values = station_df["value"].dropna()

        summaries.append(
            {
                "station_id": int(station_id),
                "observation_count": int(len(station_df)),
                "valid_observation_count": int(len(numeric_values)),
                "missing_value_count": int(
                    station_df["value"].isna().sum()
                ),
                "start_time": station_df["timestamp"]
                .min()
                .isoformat(),
                "end_time": station_df["timestamp"]
                .max()
                .isoformat(),
                "latest_value": (
                    float(numeric_values.iloc[-1])
                    if not numeric_values.empty
                    else None
                ),
            }
        )

    return summaries