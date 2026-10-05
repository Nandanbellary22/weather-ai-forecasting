from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error


PROJECT_ROOT = Path(__file__).resolve().parents[2]

FEATURE_FILE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "mrc_hourly_features.csv"
)

TARGET_COLUMN = "target_next_hour"

WATER_LEVEL_FEATURES = [
    "hour_of_day",
    "day_of_week",
    "day_of_month",
    "water_level_lag_1",
    "water_level_lag_3",
    "water_level_lag_6",
    "water_level_lag_12",
    "water_level_lag_24",
    "water_level_rolling_mean_3",
    "water_level_rolling_mean_6",
    "water_level_rolling_mean_12",
    "water_level_rolling_mean_24",
]

RAINFALL_FEATURES = [
    "rainfall_lag_1",
    "rainfall_lag_3",
    "rainfall_lag_6",
    "rainfall_lag_12",
    "rainfall_lag_24",
    "rainfall_rolling_sum_3",
    "rainfall_rolling_sum_6",
    "rainfall_rolling_sum_12",
    "rainfall_rolling_sum_24",
]

WATER_LEVEL_PLUS_RAINFALL_FEATURES = (
    WATER_LEVEL_FEATURES
    + RAINFALL_FEATURES
)

DEFAULT_STATIONS = [
    "019803",
    "019804",
    "039801",
    "902601",
]

# Best-performing model from the controlled MRC experiment.
# These are intentionally station-specific because the benchmark
# showed different models performing best at different stations.
BEST_MODELS = {
    "019803": {
        "model": "linear_regression",
        "feature_set": "water_level_only",
    },
    "019804": {
        "model": "random_forest",
        "feature_set": "water_level_only",
    },
    "039801": {
        "model": "linear_regression",
        "feature_set": "water_level_only",
    },
    "902601": {
        "model": "random_forest",
        "feature_set": "water_level_only",
    },
}


def load_feature_data() -> pd.DataFrame:
    """
    Load and validate the MRC hourly feature dataset.
    """

    if not FEATURE_FILE.exists():
        raise FileNotFoundError(
            f"MRC feature file not found: {FEATURE_FILE}"
        )

    df = pd.read_csv(
        FEATURE_FILE,
        dtype={"station_id": str},
    )

    if df.empty:
        raise ValueError(
            "MRC feature dataset is empty."
        )

    required_columns = set(
        WATER_LEVEL_PLUS_RAINFALL_FEATURES
        + [
            "station_id",
            "hour",
            TARGET_COLUMN,
            "next_hour",
            "target_is_next_hour",
        ]
    )

    missing_columns = (
        required_columns - set(df.columns)
    )

    if missing_columns:
        raise ValueError(
            "MRC feature dataset is missing columns: "
            f"{sorted(missing_columns)}"
        )

    df["station_id"] = (
        df["station_id"]
        .astype(str)
        .str.zfill(6)
    )

    df["hour"] = pd.to_datetime(
        df["hour"],
        errors="coerce",
        utc=True,
    )

    df["next_hour"] = pd.to_datetime(
        df["next_hour"],
        errors="coerce",
        utc=True,
    )

    if df["hour"].isna().any():
        raise ValueError(
            "MRC feature dataset contains invalid hour timestamps."
        )

    numeric_columns = (
        WATER_LEVEL_PLUS_RAINFALL_FEATURES
        + [TARGET_COLUMN]
    )

    for column in numeric_columns:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    df["target_is_next_hour"] = (
        df["target_is_next_hour"]
        .astype(bool)
    )

    df = (
        df.sort_values(
            ["station_id", "hour"]
        )
        .reset_index(drop=True)
    )

    return df


def prepare_station_data(
    df: pd.DataFrame,
    station_id: str,
    feature_columns: list[str],
) -> pd.DataFrame:
    """
    Prepare valid historical rows for one station.
    """

    station_id = str(station_id).zfill(6)

    station_df = df[
        df["station_id"] == station_id
    ].copy()

    if station_df.empty:
        raise ValueError(
            f"No MRC feature data found for station "
            f"{station_id}."
        )

    station_df = station_df[
        station_df["target_is_next_hour"] == True
    ].copy()

    required_columns = (
        feature_columns
        + [TARGET_COLUMN]
    )

    station_df = station_df.dropna(
        subset=required_columns
    )

    station_df = (
        station_df
        .sort_values("hour")
        .reset_index(drop=True)
    )

    if len(station_df) < 100:
        raise ValueError(
            f"Not enough valid MRC observations for "
            f"station {station_id}: {len(station_df)} rows."
        )

    return station_df


def create_model(model_type: str):
    """
    Create an ML model.
    """

    if model_type == "linear_regression":
        return LinearRegression()

    if model_type == "random_forest":
        return RandomForestRegressor(
            n_estimators=300,
            random_state=42,
            n_jobs=-1,
        )

    raise ValueError(
        "Unsupported model type. "
        "Use 'linear_regression' or "
        "'random_forest'."
    )


def get_feature_columns(
    feature_set: str,
) -> list[str]:
    """
    Return feature columns for a feature set.
    """

    if feature_set == "water_level_only":
        return WATER_LEVEL_FEATURES.copy()

    if feature_set == "water_level_plus_rainfall":
        return WATER_LEVEL_PLUS_RAINFALL_FEATURES.copy()

    raise ValueError(
        "Unsupported feature set. "
        "Use 'water_level_only' or "
        "'water_level_plus_rainfall'."
    )


def calculate_metrics(
    y_true: pd.Series,
    predictions: np.ndarray,
) -> tuple[float, float]:
    """
    Calculate MAE and RMSE.
    """

    mae = mean_absolute_error(
        y_true,
        predictions,
    )

    rmse = np.sqrt(
        mean_squared_error(
            y_true,
            predictions,
        )
    )

    return float(mae), float(rmse)


def evaluate_persistence(
    station_id: str,
    df: pd.DataFrame,
) -> dict:
    """
    Evaluate the persistence baseline.

    The next-hour water level is predicted as
    the latest observed water level.
    """

    feature_columns = [
        "water_level_lag_1"
    ]

    station_df = prepare_station_data(
        df,
        station_id,
        feature_columns,
    )

    split_index = int(
        len(station_df) * 0.80
    )

    train_df = station_df.iloc[
        :split_index
    ].copy()

    test_df = station_df.iloc[
        split_index:
    ].copy()

    predictions = test_df[
        "water_level_lag_1"
    ].to_numpy(dtype=float)

    mae, rmse = calculate_metrics(
        test_df[TARGET_COLUMN],
        predictions,
    )

    return {
        "station_id": str(station_id).zfill(6),
        "experiment": "persistence",
        "model": "persistence",
        "feature_set": "water_level_only",
        "rows": int(len(station_df)),
        "train_rows": int(len(train_df)),
        "test_rows": int(len(test_df)),
        "mae": mae,
        "rmse": rmse,
        "training_start": train_df["hour"].min(),
        "training_end": train_df["hour"].max(),
        "test_start": test_df["hour"].min(),
        "test_end": test_df["hour"].max(),
        "feature_importance": None,
    }


def evaluate_model(
    station_id: str,
    model_type: str,
    feature_set: str,
    df: pd.DataFrame,
) -> dict:
    """
    Evaluate one ML model with one feature set.

    Feature sets:
        water_level_only
        water_level_plus_rainfall
    """

    station_id = str(station_id).zfill(6)

    feature_columns = get_feature_columns(
        feature_set
    )

    station_df = prepare_station_data(
        df,
        station_id,
        feature_columns,
    )

    split_index = int(
        len(station_df) * 0.80
    )

    train_df = station_df.iloc[
        :split_index
    ].copy()

    test_df = station_df.iloc[
        split_index:
    ].copy()

    X_train = train_df[
        feature_columns
    ]

    y_train = train_df[
        TARGET_COLUMN
    ]

    X_test = test_df[
        feature_columns
    ]

    y_test = test_df[
        TARGET_COLUMN
    ]

    model = create_model(
        model_type
    )

    model.fit(
        X_train,
        y_train,
    )

    predictions = model.predict(
        X_test
    )

    mae, rmse = calculate_metrics(
        y_test,
        predictions,
    )

    feature_importance = None

    if model_type == "random_forest":
        feature_importance = {
            feature: float(importance)
            for feature, importance in zip(
                feature_columns,
                model.feature_importances_,
            )
        }

    return {
        "station_id": station_id,
        "experiment": (
            f"{model_type}_{feature_set}"
        ),
        "model": model_type,
        "feature_set": feature_set,
        "rows": int(len(station_df)),
        "train_rows": int(len(train_df)),
        "test_rows": int(len(test_df)),
        "mae": mae,
        "rmse": rmse,
        "training_start": train_df["hour"].min(),
        "training_end": train_df["hour"].max(),
        "test_start": test_df["hour"].min(),
        "test_end": test_df["hour"].max(),
        "feature_importance": feature_importance,
    }


def evaluate_station(
    station_id: str,
    df: pd.DataFrame,
) -> list[dict]:
    """
    Run the complete controlled experiment for one station.

    Experiments:

    1. Persistence
    2. Linear Regression - water level only
    3. Linear Regression - water level + rainfall
    4. Random Forest - water level only
    5. Random Forest - water level + rainfall
    """

    results = []

    results.append(
        evaluate_persistence(
            station_id=station_id,
            df=df,
        )
    )

    for model_type in [
        "linear_regression",
        "random_forest",
    ]:
        results.append(
            evaluate_model(
                station_id=station_id,
                model_type=model_type,
                feature_set="water_level_only",
                df=df,
            )
        )

        results.append(
            evaluate_model(
                station_id=station_id,
                model_type=model_type,
                feature_set="water_level_plus_rainfall",
                df=df,
            )
        )

    return results


def run_controlled_experiment(
    station_ids: list[str] | None = None,
) -> pd.DataFrame:
    """
    Run the controlled feature experiment across stations.
    """

    df = load_feature_data()

    if station_ids is None:
        station_ids = DEFAULT_STATIONS

    normalized_station_ids = [
        str(station_id).zfill(6)
        for station_id in station_ids
    ]

    results = []

    for station_id in normalized_station_ids:
        station_results = evaluate_station(
            station_id=station_id,
            df=df,
        )

        results.extend(
            station_results
        )

    experiment_df = pd.DataFrame(
        results
    )

    if experiment_df.empty:
        raise ValueError(
            "No MRC experiment results were produced."
        )

    return experiment_df


def get_best_model_config(
    station_id: str,
) -> dict:
    """
    Return the validated model configuration for a station.
    """

    station_id = str(station_id).zfill(6)

    if station_id not in BEST_MODELS:
        supported = ", ".join(
            sorted(BEST_MODELS.keys())
        )

        raise ValueError(
            f"No validated MRC forecasting model is "
            f"configured for station {station_id}. "
            f"Currently supported stations: {supported}"
        )

    return BEST_MODELS[station_id].copy()


def train_production_model(
    station_id: str,
    df: pd.DataFrame,
):
    """
    Train the validated production model using all
    available historical rows for the station.

    The model is trained only after the controlled
    experiment has identified the model/feature set.
    """

    station_id = str(station_id).zfill(6)

    config = get_best_model_config(
        station_id
    )

    model_type = config["model"]
    feature_set = config["feature_set"]

    feature_columns = get_feature_columns(
        feature_set
    )

    station_df = prepare_station_data(
        df,
        station_id,
        feature_columns,
    )

    X_train = station_df[
        feature_columns
    ]

    y_train = station_df[
        TARGET_COLUMN
    ]

    model = create_model(
        model_type
    )

    model.fit(
        X_train,
        y_train,
    )

    return (
        model,
        station_df,
        feature_columns,
        config,
    )


def get_validation_metrics(
    station_id: str,
    df: pd.DataFrame,
) -> dict:
    """
    Re-run the station's selected model using the same
    chronological 80/20 validation strategy used in the
    controlled experiment.

    This provides validation metrics alongside the
    production forecast.
    """

    station_id = str(station_id).zfill(6)

    config = get_best_model_config(
        station_id
    )

    feature_columns = get_feature_columns(
        config["feature_set"]
    )

    station_df = prepare_station_data(
        df,
        station_id,
        feature_columns,
    )

    split_index = int(
        len(station_df) * 0.80
    )

    if split_index <= 0 or split_index >= len(station_df):
        raise ValueError(
            f"Unable to create validation split for "
            f"station {station_id}."
        )

    train_df = station_df.iloc[
        :split_index
    ].copy()

    test_df = station_df.iloc[
        split_index:
    ].copy()

    model = create_model(
        config["model"]
    )

    model.fit(
        train_df[feature_columns],
        train_df[TARGET_COLUMN],
    )

    predictions = model.predict(
        test_df[feature_columns]
    )

    mae, rmse = calculate_metrics(
        test_df[TARGET_COLUMN],
        predictions,
    )

    return {
        "mae": mae,
        "rmse": rmse,
        "train_rows": int(len(train_df)),
        "test_rows": int(len(test_df)),
        "validation_start": test_df["hour"].min(),
        "validation_end": test_df["hour"].max(),
    }


def forecast_next_hour(
    station_id: str,
) -> dict:
    """
    Generate a one-hour-ahead MRC water-level forecast.

    The selected station-specific model is trained on all
    valid historical feature rows, then the latest available
    feature row is used to predict the next hour.

    TARGET_COLUMN is never used as an input feature.
    """

    station_id = str(station_id).zfill(6)

    df = load_feature_data()

    config = get_best_model_config(
        station_id
    )

    model, station_df, feature_columns, _ = (
        train_production_model(
            station_id=station_id,
            df=df,
        )
    )

    latest_row = (
        station_df
        .sort_values("hour")
        .iloc[-1]
    )

    latest_features = latest_row[
        feature_columns
    ]

    if latest_features.isna().any():
        missing_features = (
            latest_features[
                latest_features.isna()
            ]
            .index
            .tolist()
        )

        raise ValueError(
            f"Latest MRC feature row for station "
            f"{station_id} is missing required features: "
            f"{missing_features}"
        )

    prediction = model.predict(
        pd.DataFrame(
            [latest_features.to_dict()]
        )
    )[0]

    forecast_timestamp = (
        latest_row["hour"]
        + pd.Timedelta(hours=1)
    )

    validation = get_validation_metrics(
        station_id=station_id,
        df=df,
    )

    return {
        "station_id": station_id,
        "model": config["model"],
        "feature_set": config["feature_set"],
        "forecast_timestamp": forecast_timestamp,
        "predicted_water_level": float(prediction),
        "latest_observation_timestamp": latest_row["hour"],
        "latest_water_level": float(
            latest_row["water_level"]
        ),
        "validation_mae": validation["mae"],
        "validation_rmse": validation["rmse"],
        "train_rows": validation["train_rows"],
        "test_rows": validation["test_rows"],
        "validation_start": validation[
            "validation_start"
        ],
        "validation_end": validation[
            "validation_end"
        ],
    }


def print_experiment_results(
    experiment_df: pd.DataFrame,
) -> None:
    """
    Print detailed experiment results.
    """

    print()
    print("=" * 90)
    print("MRC CONTROLLED FORECASTING EXPERIMENT")
    print("=" * 90)

    display_columns = [
        "station_id",
        "experiment",
        "rows",
        "train_rows",
        "test_rows",
        "mae",
        "rmse",
    ]

    print(
        experiment_df[
            display_columns
        ].to_string(index=False)
    )

    print()
    print("-" * 90)
    print("BEST EXPERIMENT BY STATION")
    print("-" * 90)

    best_indices = (
        experiment_df
        .groupby("station_id")["mae"]
        .idxmin()
    )

    best_df = (
        experiment_df
        .loc[best_indices]
        .sort_values("station_id")
    )

    print(
        best_df[
            [
                "station_id",
                "experiment",
                "mae",
                "rmse",
            ]
        ].to_string(index=False)
    )

    print()
    print("-" * 90)
    print("AVERAGE PERFORMANCE BY EXPERIMENT")
    print("-" * 90)

    summary = (
        experiment_df
        .groupby(
            [
                "model",
                "feature_set",
            ]
        )
        .agg(
            stations=(
                "station_id",
                "nunique",
            ),
            mean_mae=(
                "mae",
                "mean",
            ),
            mean_rmse=(
                "rmse",
                "mean",
            ),
        )
        .sort_values("mean_mae")
    )

    print(
        summary.to_string()
    )


def print_rainfall_effect(
    experiment_df: pd.DataFrame,
) -> None:
    """
    Compare each ML model with and without rainfall.
    """

    print()
    print("=" * 90)
    print("EFFECT OF ADDING RAINFALL FEATURES")
    print("=" * 90)

    for model_type in [
        "linear_regression",
        "random_forest",
    ]:
        water_only = experiment_df[
            (
                experiment_df["model"]
                == model_type
            )
            & (
                experiment_df["feature_set"]
                == "water_level_only"
            )
        ].copy()

        water_rain = experiment_df[
            (
                experiment_df["model"]
                == model_type
            )
            & (
                experiment_df["feature_set"]
                == "water_level_plus_rainfall"
            )
        ].copy()

        merged = water_only.merge(
            water_rain,
            on="station_id",
            suffixes=(
                "_water",
                "_rainfall",
            ),
        )

        if merged.empty:
            continue

        merged["mae_change"] = (
            merged["mae_rainfall"]
            - merged["mae_water"]
        )

        merged["mae_improvement_percent"] = (
            (
                merged["mae_water"]
                - merged["mae_rainfall"]
            )
            / merged["mae_water"]
            * 100
        )

        print()
        print(
            f"Model: {model_type}"
        )

        print(
            merged[
                [
                    "station_id",
                    "mae_water",
                    "mae_rainfall",
                    "mae_change",
                    "mae_improvement_percent",
                ]
            ].to_string(index=False)
        )


def print_feature_importance(
    experiment_df: pd.DataFrame,
) -> None:
    """
    Print Random Forest feature importance
    for the rainfall-enabled model.
    """

    print()
    print("=" * 90)
    print(
        "RANDOM FOREST FEATURE IMPORTANCE "
        "(WATER LEVEL + RAINFALL)"
    )
    print("=" * 90)

    rf_results = experiment_df[
        (
            experiment_df["model"]
            == "random_forest"
        )
        & (
            experiment_df["feature_set"]
            == "water_level_plus_rainfall"
        )
    ]

    for _, row in rf_results.iterrows():

        importance = row[
            "feature_importance"
        ]

        if not importance:
            continue

        importance_df = (
            pd.DataFrame(
                importance.items(),
                columns=[
                    "feature",
                    "importance",
                ],
            )
            .sort_values(
                "importance",
                ascending=False,
            )
        )

        print()
        print(
            f"Station {row['station_id']}"
        )

        print(
            importance_df
            .head(15)
            .to_string(index=False)
        )


if __name__ == "__main__":

    print("=" * 90)
    print("MRC FORECASTING SERVICE")
    print("=" * 90)

    print()
    print(
        f"Feature file: {FEATURE_FILE}"
    )

    data = load_feature_data()

    print(
        f"Loaded feature rows: "
        f"{len(data):,}"
    )

    print(
        f"Stations available: "
        f"{data['station_id'].nunique()}"
    )

    print()
    print(
        "Stations used in controlled experiment:"
    )

    for station_id in DEFAULT_STATIONS:

        station_rows = data[
            data["station_id"]
            == station_id
        ]

        print(
            f"  {station_id}: "
            f"{len(station_rows)} rows"
        )

    experiment = run_controlled_experiment()

    print_experiment_results(
        experiment
    )

    print_rainfall_effect(
        experiment
    )

    print_feature_importance(
        experiment
    )

    print()
    print("=" * 90)
    print("PRODUCTION FORECAST TEST")
    print("=" * 90)

    for station_id in DEFAULT_STATIONS:

        try:
            result = forecast_next_hour(
                station_id
            )

            print()
            print(
                f"Station: {result['station_id']}"
            )
            print(
                f"Model: {result['model']}"
            )
            print(
                f"Feature set: "
                f"{result['feature_set']}"
            )
            print(
                f"Latest observation: "
                f"{result['latest_observation_timestamp']}"
            )
            print(
                f"Latest water level: "
                f"{result['latest_water_level']:.6f}"
            )
            print(
                f"Forecast timestamp: "
                f"{result['forecast_timestamp']}"
            )
            print(
                f"Predicted water level: "
                f"{result['predicted_water_level']:.6f}"
            )
            print(
                f"Validation MAE: "
                f"{result['validation_mae']:.6f}"
            )
            print(
                f"Validation RMSE: "
                f"{result['validation_rmse']:.6f}"
            )

        except Exception as exc:
            print()
            print(
                f"Forecast failed for "
                f"{station_id}: {exc}"
            )