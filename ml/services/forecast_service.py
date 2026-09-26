import os
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error


PROJECT_ROOT = Path(__file__).resolve().parents[2]


DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "weather_forecasting",
    "user": "postgres",
}


def get_connection():
    password = os.getenv("POSTGRES_PASSWORD")

    if not password:
        raise RuntimeError(
            "POSTGRES_PASSWORD environment variable is not set."
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
    """

    data = df.copy()

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
        .rolling(6)
        .mean()
    )

    data["rolling_mean_12"] = (
        data["value"]
        .rolling(12)
        .mean()
    )

    data["rolling_mean_24"] = (
        data["value"]
        .rolling(24)
        .mean()
    )

    return data


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
    """
    Train a forecasting model using PostgreSQL observations.
    """

    df = load_data()

    station_id = str(station_id)

    station_df = df[
        df["station_id"] == station_id
    ].copy()

    if station_df.empty:
        raise ValueError(
            f"No data found for station {station_id}."
        )

    station_df = create_features(station_df)

    model_data = station_df.dropna(
        subset=FEATURE_COLUMNS + ["value"]
    ).copy()

    if len(model_data) < 100:
        raise ValueError(
            f"Not enough valid observations for station {station_id}."
        )

    split_index = int(
        len(model_data) * 0.80
    )

    train_df = model_data.iloc[:split_index]
    test_df = model_data.iloc[split_index:]

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

    model.fit(
        X_train,
        y_train,
    )

    predictions = model.predict(X_test)

    mae = mean_absolute_error(
        y_test,
        predictions,
    )

    rmse = np.sqrt(
        mean_squared_error(
            y_test,
            predictions,
        )
    )

    metrics = {
        "mae": float(mae),
        "rmse": float(rmse),
        "train_rows": int(len(train_df)),
        "test_rows": int(len(test_df)),
        "training_start": train_df["timestamp"].min(),
        "training_end": train_df["timestamp"].max(),
    }

    return model, station_df, metrics


def forecast_next_24_hours(
    station_id: str,
    model_type: str = "random_forest",
):
    """
    Train a model and recursively forecast the next 24 hours.

    The forecast is also saved into PostgreSQL.
    """

    model, station_df, metrics = train_model(
        station_id=station_id,
        model_type=model_type,
    )

    station_id = str(station_id)

    history = station_df[
        [
            "timestamp",
            "value",
        ]
    ].copy()

    history = history.dropna(
        subset=["value"]
    ).sort_values(
        "timestamp"
    ).reset_index(drop=True)

    if len(history) < 24:
        raise ValueError(
            "Not enough historical observations "
            "for recursive forecasting."
        )

    forecast_points = []

    values = list(
        history["value"].astype(float)
    )

    timestamps = list(
        history["timestamp"]
    )

    last_timestamp = timestamps[-1]

    for step in range(1, 25):

        forecast_timestamp = (
            last_timestamp
            + pd.Timedelta(hours=step)
        )

        current_hour = forecast_timestamp.hour
        current_day_of_week = (
            forecast_timestamp.dayofweek
        )
        current_day_of_month = (
            forecast_timestamp.day
        )

        lag_1 = values[-1]
        lag_3 = values[-3]
        lag_6 = values[-6]
        lag_12 = values[-12]
        lag_24 = values[-24]

        rolling_mean_6 = float(
            np.mean(values[-6:])
        )

        rolling_mean_12 = float(
            np.mean(values[-12:])
        )

        rolling_mean_24 = float(
            np.mean(values[-24:])
        )

        features = pd.DataFrame(
            [
                {
                    "hour": current_hour,
                    "day_of_week": current_day_of_week,
                    "day_of_month": current_day_of_month,
                    "lag_1": lag_1,
                    "lag_3": lag_3,
                    "lag_6": lag_6,
                    "lag_12": lag_12,
                    "lag_24": lag_24,
                    "rolling_mean_6": rolling_mean_6,
                    "rolling_mean_12": rolling_mean_12,
                    "rolling_mean_24": rolling_mean_24,
                }
            ]
        )

        prediction = float(
            model.predict(
                features[FEATURE_COLUMNS]
            )[0]
        )

        values.append(prediction)

        forecast_points.append(
            {
                "timestamp": forecast_timestamp,
                "value": prediction,
            }
        )

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