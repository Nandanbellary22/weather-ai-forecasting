import os
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2
from dotenv import load_dotenv
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env", override=False)

SOURCE_TIMEZONE = "Asia/Ho_Chi_Minh"

DB_CONFIG = {
    "host": os.getenv("PGHOST", "localhost"),
    "port": int(os.getenv("PGPORT", "5432")),
    "database": os.getenv("PGDATABASE", "weather_forecasting"),
    "user": os.getenv("PGUSER", "postgres"),
}


def get_connection():
    """Create a PostgreSQL connection using shared project settings."""

    password = os.getenv("PGPASSWORD")

    if not password:
        raise RuntimeError(
            "PGPASSWORD is not set. Configure it in the project-root .env "
            "or in the process environment before starting the API."
        )

    return psycopg2.connect(
        host=DB_CONFIG["host"],
        port=DB_CONFIG["port"],
        database=DB_CONFIG["database"],
        user=DB_CONFIG["user"],
        password=password,
    )


def load_data() -> pd.DataFrame:
    """
    Load hydrology observations directly from PostgreSQL.

    PostgreSQL stores timestamps as timestamptz.
    The source observations originate from Vietnam, so timestamps
    are explicitly converted to Asia/Ho_Chi_Minh before any
    temporal features are created.
    """

    query = """
        SELECT
            station_id,
            timestamp,
            value
        FROM hydrology_observations
        ORDER BY station_id, timestamp
    """

    connection = get_connection()

    try:
        df = pd.read_sql_query(query, connection)
    finally:
        connection.close()

    if df.empty:
        raise ValueError(
            "No hydrology observations found in PostgreSQL."
        )

    required_columns = {
        "station_id",
        "timestamp",
        "value",
    }

    missing = required_columns - set(df.columns)

    if missing:
        raise ValueError(
            f"Missing database columns: {sorted(missing)}"
        )

    df["station_id"] = df["station_id"].astype(str)

    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        errors="coerce",
        utc=True,
    )

    if df["timestamp"].isna().any():
        raise ValueError(
            "Database contains invalid timestamps."
        )

    # Convert database instants explicitly to Vietnam local time.
    df["timestamp"] = df["timestamp"].dt.tz_convert(
        SOURCE_TIMEZONE
    )

    df["value"] = pd.to_numeric(
        df["value"],
        errors="coerce",
    )

    df = df.sort_values(
        ["station_id", "timestamp"]
    ).reset_index(drop=True)

    return df


def create_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Create temporal and lag features.

    Timestamp features are based on Vietnam local time. Calendar values are
    known at prediction time; lag and rolling values use observations strictly
    before the row timestamp, which remains the target time.
    """

    if df.empty:
        return df.copy()

    # Keep target gaps explicit; dependent feature rows are dropped before fit.
    try:
        data = _validate_hourly_history(df, allow_missing_values=True)
    except ValueError as exc:
        station_ids = df["station_id"].astype(str).unique() if "station_id" in df else []
        context = f" for station {station_ids[0]}" if len(station_ids) == 1 else ""
        raise ValueError(f"Invalid hourly history{context}: {exc}") from exc

    data["hour"] = data["timestamp"].dt.hour
    data["day_of_week"] = data["timestamp"].dt.dayofweek
    data["day_of_month"] = data["timestamp"].dt.day

    data["lag_1"] = data["value"].shift(1)
    data["lag_3"] = data["value"].shift(3)
    data["lag_6"] = data["value"].shift(6)
    data["lag_12"] = data["value"].shift(12)
    data["lag_24"] = data["value"].shift(24)

    data["rolling_mean_6"] = (
        data["value"]
        .shift(1)
        .rolling(6)
        .mean()
    )

    data["rolling_mean_12"] = (
        data["value"]
        .shift(1)
        .rolling(12)
        .mean()
    )

    data["rolling_mean_24"] = (
        data["value"]
        .shift(1)
        .rolling(24)
        .mean()
    )

    return data


def _validate_hourly_history(
    df: pd.DataFrame,
    *,
    minimum_rows: int = 1,
    allow_missing_values: bool = False,
) -> pd.DataFrame:
    """Validate hourly timestamps and target values without filling gaps."""

    required = {"timestamp", "value"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"History is missing required columns:{sorted(missing)}")
    if len(df) < minimum_rows:
        raise ValueError(
            f"Insufficient hourly history: need at least {minimum_rows} rows."
        )

    data = df.copy()
    timestamps = pd.to_datetime(data["timestamp"], errors="coerce")
    if timestamps.isna().any():
        raise ValueError("Hourly history contains invalid timestamps.")
    if timestamps.dt.tz is None:
        timestamps = timestamps.dt.tz_localize(SOURCE_TIMEZONE)
    else:
        timestamps = timestamps.dt.tz_convert(SOURCE_TIMEZONE)
    if timestamps.duplicated().any():
        raise ValueError("Hourly history contains duplicate timestamps.")
    if not timestamps.is_monotonic_increasing:
        raise ValueError("Hourly history timestamps must be strictly ordered.")
    if len(timestamps) > 1 and not (timestamps.diff().iloc[1:] == pd.Timedelta(hours=1)).all():
        raise ValueError("Hourly history is irregular or has missing hours.")

    values = pd.to_numeric(data["value"], errors="coerce")
    numeric_values = values.to_numpy(dtype=float)
    if np.isinf(numeric_values).any():
        raise ValueError("Hourly history contains non-finite target values.")
    if not allow_missing_values and np.isnan(numeric_values).any():
        raise ValueError("Hourly history contains missing target values.")

    data["timestamp"] = timestamps
    data["value"] = values.astype(float)
    return data.reset_index(drop=True)


def _next_step_features(values, timestamp: pd.Timestamp) -> pd.DataFrame:
    """Build one recursive feature row from observations available before it."""

    return pd.DataFrame([{
        "hour": timestamp.hour,
        "day_of_week": timestamp.dayofweek,
        "day_of_month": timestamp.day,
        "lag_1": values[-1],
        "lag_3": values[-3],
        "lag_6": values[-6],
        "lag_12": values[-12],
        "lag_24": values[-24],
        "rolling_mean_6": float(np.mean(values[-6:])),
        "rolling_mean_12": float(np.mean(values[-12:])),
        "rolling_mean_24": float(np.mean(values[-24:])),
    }], columns=FEATURE_COLUMNS)


def _recursive_predictions(model, history: pd.DataFrame, horizon: int = 24):
    """Predict a horizon recursively and validate timestamps and values."""

    history = _validate_hourly_history(
        history,
        minimum_rows=24,
        allow_missing_values=True,
    )
    if not np.isfinite(history["value"].tail(24).to_numpy(dtype=float)).all():
        raise ValueError("The latest 24 hourly observations must have finite values.")
    origin = history["timestamp"].iloc[-1]
    values = history["value"].astype(float).tolist()
    points = []
    for step in range(1, horizon + 1):
        timestamp = origin + pd.Timedelta(hours=step)
        feature_row = _next_step_features(values, timestamp)
        prediction = float(model.predict(feature_row[FEATURE_COLUMNS])[0])
        values.append(prediction)
        points.append({"timestamp": timestamp, "value": prediction})

    _validate_forecast_points(points, origin=origin, horizon=horizon)
    return points


def _validate_forecast_points(points, *, origin, horizon=24):
    if len(points) != horizon:
        raise ValueError(f"Forecast must contain exactly {horizon} points.")
    timestamps = pd.DatetimeIndex([point["timestamp"] for point in points])
    expected = pd.date_range(
        start=origin + pd.Timedelta(hours=1),
        periods=horizon,
        freq="h",
    )
    if timestamps.has_duplicates or not timestamps.is_monotonic_increasing:
        raise ValueError("Forecast timestamps must be unique and ordered.")
    if not timestamps.equals(expected):
        raise ValueError("Forecast timestamps must be hourly, starting after the origin.")
    values = np.asarray([point["value"] for point in points], dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("Forecast contains missing or non-finite predictions.")
    if len(values) > 1 and np.all(values == values[0]):
        warnings.warn("Forecast predictions are constant acrossthe horizon.", RuntimeWarning)


def evaluate_recursive_forecasts(
    df: pd.DataFrame,
    station_id: str,
    *,
    horizon: int = 24,
    max_windows: int = 5,
    minimum_train_rows: int = 100,
) -> dict:
    """Evaluate recursive Random Forest forecasts against persistence offline.

    Returns ``status='insufficient'`` with no metric values unless at least two
    complete chronological windows have enough pre-origin training rows.
    This function does not load data, save results, or connect to the database.
    """

    if horizon != 24:
        raise ValueError("Recursive evaluation currently supports a 24-hour horizon.")
    if max_windows < 2:
        raise ValueError("At least two evaluation windows are required.")
    if "station_id" not in df.columns:
        raise ValueError("Evaluation data must include station_id.")
    station = df[df["station_id"].astype(str) == str(station_id)].copy()
    try:
        station = _validate_hourly_history(
            station,
            allow_missing_values=True,
        )
    except ValueError as exc:
        return {"status": "insufficient", "reason": str(exc), "windows": 0}

    candidate_origins = list(
        range(len(station) - horizon, 0, -horizon)
    )[:max_windows]
    eligible_origins = []
    for origin in candidate_origins:
        if origin < 24:
            continue
        if not np.isfinite(
            station["value"].iloc[origin - 24:origin].to_numpy(dtype=float)
        ).all():
            continue
        training = create_features(station.iloc[:origin]).dropna(
            subset=FEATURE_COLUMNS + ["value"]
        )
        if len(training) >= minimum_train_rows:
            eligible_origins.append(origin)
    origins = sorted(eligible_origins)
    if len(origins) < 2:
        return {
            "status": "insufficient",
            "reason": "Not enough history for at least two complete 24-hour test windows and training sets.",
            "windows": len(origins),
        }

    actual, forest_predictions, persistence_predictions = [], [], []
    evaluated_timestamps = []
    excluded_comparisons = 0
    window_results = []
    for origin_index in origins:
        history = station.iloc[:origin_index].copy()
        truth = station.iloc[origin_index:origin_index + horizon]["value"].to_numpy(dtype=float)
        training = create_features(history).dropna(
            subset=FEATURE_COLUMNS + ["value"]
        )
        model = RandomForestRegressor(
            n_estimators=200,
            random_state=42,
            n_jobs=-1,
        )
        model.fit(training[FEATURE_COLUMNS], training["value"])
        predicted_points = _recursive_predictions(model, history, horizon)
        forest_window = np.asarray(
            [point["value"] for point in predicted_points], dtype=float
        )
        persistence_window = np.full(
            horizon, float(history["value"].iloc[-1]), dtype=float
        )
        valid = np.isfinite(truth)
        excluded = int((~valid).sum())
        excluded_comparisons += excluded
        actual_timestamps = station["timestamp"].iloc[
            origin_index:origin_index + horizon
        ]
        window_results.append({
            "forecast_origin": history["timestamp"].iloc[-1],
            "evaluation_start": actual_timestamps.iloc[0],
            "evaluation_end": actual_timestamps.iloc[-1],
            "evaluated_observations": int(valid.sum()),
            "excluded_comparisons": excluded,
            "evaluated_start": actual_timestamps[valid].iloc[0]if valid.any() else None,
            "evaluated_end": actual_timestamps[valid].iloc[-1] if valid.any() else None,
        })
        if valid.any():
            actual.extend(truth[valid].tolist())
            forest_predictions.extend(forest_window[valid].tolist())
            persistence_predictions.extend(persistence_window[valid].tolist())
            evaluated_timestamps.extend(actual_timestamps[valid].tolist())

    evaluated_windows = sum(
        item["evaluated_observations"] > 0 for item in window_results
    )
    if evaluated_windows < 2:
        return {
            "status": "insufficient",
            "reason": "Fewer than two forecast windows have valid observations for comparison.",
            "windows": len(origins),
            "evaluated_windows": evaluated_windows,
            "evaluated_observations": len(actual),
            "excluded_comparisons": excluded_comparisons,
        }

    def metric_pair(predictions):
        return {
            "rmse": float(np.sqrt(mean_squared_error(actual, predictions))),
            "mae": float(mean_absolute_error(actual, predictions)),
        }

    random_forest_metrics = metric_pair(forest_predictions)
    persistence_metrics = metric_pair(persistence_predictions)
    return {
        "status": "success",
        "windows": len(origins),
        "horizon": horizon,
        "points": len(actual),
        "evaluated_observations": len(actual),
        "evaluated_windows": evaluated_windows,
        "excluded_comparisons": excluded_comparisons,
        "evaluation_start": min(evaluated_timestamps),
        "evaluation_end": max(evaluated_timestamps),
        "window_results": window_results,
        "random_forest": random_forest_metrics,
        "persistence": persistence_metrics,
        "random_forest_better_on_both_metrics": (
            random_forest_metrics["rmse"] < persistence_metrics["rmse"]
            and random_forest_metrics["mae"] < persistence_metrics["mae"]
        ),
    }


FEATURE_COLUMNS = [
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


def train_model(
    station_id: str,
    model_type: str = "random_forest",
):
    """Train on the longest continuous segment and return the latest segment.

    The historical segment is used for model fitting and holdout metrics.
    The latest continuous segment is returned as the recursive forecast history.
    Gaps are never filled or bridged.
    """

    df = load_data()
    station_id = str(station_id)

    station_df = df[df["station_id"] == station_id].copy()
    if station_df.empty:
        raise ValueError(f"No data found for station {station_id}.")

    station_df = station_df.sort_values("timestamp").reset_index(drop=True)
    timestamp_gap = station_df["timestamp"].diff()
    segment_break = timestamp_gap.isna() | (
        timestamp_gap != pd.Timedelta(hours=1)
    )
    station_df["_segment_id"] = segment_break.cumsum()

    segments = [
        group.drop(columns="_segment_id").reset_index(drop=True)
        for _, group in station_df.groupby("_segment_id")
    ]

    training_history = max(segments, key=len)
    latest_history = max(
        segments,
        key=lambda segment: segment["timestamp"].iloc[-1],
    )

    # Feature engineering requires at least 24 hours for lag/rolling features;
    # retain a larger minimum to avoid training on an extremelyshort segment.
    if len(training_history) < 125:
        raise ValueError(
            f"Not enough continuous hourly history for station {station_id}."
        )

    training_features = create_features(training_history)
    model_data = training_features.dropna(
        subset=FEATURE_COLUMNS + ["value"]
    ).copy()

    if len(model_data) < 100:
        raise ValueError(
            f"Not enough valid observations for station {station_id}."
        )

    split_index = int(len(model_data) * 0.80)
    train_df = model_data.iloc[:split_index]
    test_df = model_data.iloc[split_index:]

    if train_df.empty or test_df.empty:
        raise ValueError(
            f"Insufficient training or test data for station {station_id}."
        )

    X_train = train_df[FEATURE_COLUMNS]
    y_train = train_df["value"]
    X_test = test_df[FEATURE_COLUMNS]
    y_test = test_df["value"]

    if model_type == "random_forest":
        model = RandomForestRegressor(
            n_estimators=200,
            random_state=42,
            n_jobs=-1,
        )
    elif model_type == "linear_regression":
        model = LinearRegression()
    else:
        raise ValueError(
            "Unsupported model type. "
            "Use 'random_forest' or 'linear_regression'."
        )

    model.fit(X_train, y_train)
    predictions = model.predict(X_test)

    mae = mean_absolute_error(y_test, predictions)
    rmse = np.sqrt(mean_squared_error(y_test, predictions))

    metrics = {
        "mae": float(mae),
        "rmse": float(rmse),
        "train_rows": int(len(train_df)),
        "test_rows": int(len(test_df)),
        "training_start": train_df["timestamp"].min(),
        "training_end": train_df["timestamp"].max(),
    }

    # Return only the latest contiguous segment for forecast input.
    latest_history = create_features(latest_history)
    return model, latest_history, metrics

def forecast_next_24_hours(
    station_id: str,
    model_type: str = "random_forest",
):
    """
    Train a model and recursively forecast the next 24 hours.

    Forecast timestamps are maintained in Vietnam local time.
    The forecast is also saved into PostgreSQL.
    """

    model, station_df, metrics = train_model(
        station_id=station_id,
        model_type=model_type,
    )

    station_id = str(station_id)

    if "station_id" in station_df and not station_df["station_id"].astype(str).eq(station_id).all():
        raise ValueError(
            f"Forecast history contains observations for another station than {station_id}."
        )

    history = station_df[
        [
            "timestamp",
            "value",
        ]
    ].copy()

    history = _validate_hourly_history(
        history,
        minimum_rows=24,
        allow_missing_values=True,
    )
    if not np.isfinite(history["value"].tail(24).to_numpy(dtype=float)).all():
        raise ValueError(
            "The latest 24 hourly observations must have finitevalues."
        )

    forecast_points = _recursive_predictions(model, history, horizon=24)

    save_forecast_run(
        station_id=station_id,
        model_type=model_type,
        metrics=metrics,
        forecast_points=forecast_points,
    )

    last_observation = history.iloc[-1]

    return {
        "station_id": station_id,
        "model": model_type,
        "metrics": {
            "mae": metrics["mae"],
            "rmse": metrics["rmse"],
            "train_rows": metrics["train_rows"],
            "test_rows": metrics["test_rows"],
        },
        "last_observation": {
            "timestamp": last_observation["timestamp"],
            "value": float(
                last_observation["value"]
            ),
        },
        "forecast": [
            {
                "timestamp": point["timestamp"],
                "value": point["value"],
            }
            for point in forecast_points
        ],
    }


def save_forecast_run(
    station_id: str,
    model_type: str,
    metrics: dict,
    forecast_points: list,
):
    """
    Save forecast metadata and forecast values
    into PostgreSQL.
    """

    connection = get_connection()

    try:
        with connection:
            with connection.cursor() as cursor:

                insert_run = """
                    INSERT INTO forecast_runs
                    (
                        station_id,
                        model_type,
                        training_start,
                        training_end,
                        train_rows,
                        test_rows,
                        mae,
                        rmse
                    )
                    VALUES
                    (
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s
                    )
                    RETURNING id
                """

                cursor.execute(
                    insert_run,
                    (
                        station_id,
                        model_type,
                        metrics["training_start"],
                        metrics["training_end"],
                        metrics["train_rows"],
                        metrics["test_rows"],
                        metrics["mae"],
                        metrics["rmse"],
                    ),
                )

                forecast_run_id = cursor.fetchone()[0]

                values = [
                    (
                        forecast_run_id,
                        station_id,
                        point["timestamp"],
                        point["value"],
                    )
                    for point in forecast_points
                ]

                insert_values = """
                    INSERT INTO forecast_values
                    (
                        forecast_run_id,
                        station_id,
                        forecast_timestamp,
                        predicted_value
                    )
                    VALUES %s
                """

                from psycopg2.extras import execute_values

                execute_values(
                    cursor,
                    insert_values,
                    values,
                    page_size=100,
                )

                print(
                    f"Saved forecast run: {forecast_run_id}"
                )

    finally:
        connection.close()


def get_station_summary():
    """
    Return summary information for all stations
    directly from PostgreSQL.
    """

    query = """
        SELECT
            station_id,
            COUNT(*) AS observations,
            COUNT(value) AS valid_observations,
            COUNT(*) - COUNT(value) AS missing_values,
            MIN(timestamp) AS start_time,
            MAX(timestamp) AS end_time
        FROM hydrology_observations
        GROUP BY station_id
        ORDER BY station_id
    """

    connection = get_connection()

    try:
        summary_df = pd.read_sql_query(
            query,
            connection,
        )
    finally:
        connection.close()

    results = []

    for row in summary_df.itertuples(
        index=False
    ):

        latest_query = """
            SELECT
                value
            FROM hydrology_observations
            WHERE station_id = %s
              AND value IS NOT NULL
            ORDER BY timestamp DESC
            LIMIT 1
        """

        connection = get_connection()

        try:
            latest_df = pd.read_sql_query(
                latest_query,
                connection,
                params=[str(row.station_id)],
            )
        finally:
            connection.close()

        latest_value = None

        if not latest_df.empty:
            latest_value = float(
                latest_df.iloc[0]["value"]
            )

        results.append(
            {
                "station_id": str(row.station_id),
                "observations": int(
                    row.observations
                ),
                "valid_observations": int(
                    row.valid_observations
                ),
                "missing_values": int(
                    row.missing_values
                ),
                "start_time": row.start_time,
                "end_time": row.end_time,
                "latest_value": latest_value,
            }
        )

    return results


if __name__ == "__main__":

    print(
        "Testing PostgreSQL-backed "
        "forecast service..."
    )

    print("\n--- Station Summary ---")

    summaries = get_station_summary()

    for summary in summaries:
        print(summary)

    print("\n--- 24-Hour Forecast ---")

    result = forecast_next_24_hours(
        station_id="553100",
        model_type="random_forest",
    )

    print(
        f"Station: {result['station_id']}"
    )

    print(
        f"Model: {result['model']}"
    )

    print(
        f"MAE: {result['metrics']['mae']}"
    )

    print(
        f"RMSE: {result['metrics']['rmse']}"
    )

    print(
        f"Forecast points: "
        f"{len(result['forecast'])}"
    )

    print("\nFirst 3 forecasts:")

    for point in result["forecast"][:3]:
        print(point)
