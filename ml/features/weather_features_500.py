from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2


# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parents[2]

OUTPUT_DIR = BASE_DIR / "data" / "processed" / "weather_features"

TEMPERATURE_OUTPUT = (
    OUTPUT_DIR / "temperature_features_500.csv"
)

RAINFALL_OUTPUT = (
    OUTPUT_DIR / "rainfall_features_500.csv"
)

TRAIN_RATIO = 0.80


# ============================================================
# DATABASE
# ============================================================

def get_connection():
    return psycopg2.connect(
        host="localhost",
        port=5432,
        dbname="weather_forecasting",
        user="postgres",
    )


# ============================================================
# LOAD WEATHER DATA
# ============================================================

def load_weather_data():

    print("Loading weather data from PostgreSQL...")

    conn = get_connection()

    query = """
        SELECT
            location_code,
            timestamp,
            temperature_2m,
            precipitation_mm,
            relative_humidity_2m,
            surface_pressure_hpa,
            wind_speed_10m,
            cloud_cover,
            latitude,
            longitude
        FROM weather_observations
        ORDER BY location_code, timestamp
    """

    df = pd.read_sql_query(
        query,
        conn,
    )

    conn.close()

    print(f"Rows loaded: {len(df):,}")
    print(
        f"Locations: "
        f"{df['location_code'].nunique():,}"
    )

    return df


# ============================================================
# FEATURE ENGINEERING
# ============================================================

def create_features(df):

    print("\nCreating temporal features...")

    df = df.copy()

    df["timestamp"] = pd.to_datetime(
        df["timestamp"]
    )

    # --------------------------------------------------------
    # Time features
    # --------------------------------------------------------

    df["hour"] = df["timestamp"].dt.hour
    df["day_of_week"] = df["timestamp"].dt.dayofweek
    df["day_of_year"] = df["timestamp"].dt.dayofyear
    df["month"] = df["timestamp"].dt.month

    # Cyclic encoding
    df["hour_sin"] = np.sin(
        2 * np.pi * df["hour"] / 24
    )

    df["hour_cos"] = np.cos(
        2 * np.pi * df["hour"] / 24
    )

    df["day_of_year_sin"] = np.sin(
        2 * np.pi * df["day_of_year"] / 365
    )

    df["day_of_year_cos"] = np.cos(
        2 * np.pi * df["day_of_year"] / 365
    )

    # --------------------------------------------------------
    # Lag features
    # --------------------------------------------------------

    print("Creating lag features...")

    grouped = df.groupby(
        "location_code",
        group_keys=False,
    )

    for lag in [1, 3, 6, 12, 24]:

        df[f"temperature_lag_{lag}"] = (
            grouped["temperature_2m"]
            .shift(lag)
        )

        df[f"rainfall_lag_{lag}"] = (
            grouped["precipitation_mm"]
            .shift(lag)
        )

        df[f"humidity_lag_{lag}"] = (
            grouped["relative_humidity_2m"]
            .shift(lag)
        )

    # --------------------------------------------------------
    # Rolling temperature statistics
    # --------------------------------------------------------

    print("Creating rolling statistics...")

    for window in [6, 12, 24]:

        df[f"temperature_roll_mean_{window}"] = (
            grouped["temperature_2m"]
            .transform(
                lambda x: x.shift(1)
                .rolling(window)
                .mean()
            )
        )

        df[f"temperature_roll_std_{window}"] = (
            grouped["temperature_2m"]
            .transform(
                lambda x: x.shift(1)
                .rolling(window)
                .std()
            )
        )

        df[f"rainfall_roll_sum_{window}"] = (
            grouped["precipitation_mm"]
            .transform(
                lambda x: x.shift(1)
                .rolling(window)
                .sum()
            )
        )

        df[f"rainfall_roll_mean_{window}"] = (
            grouped["precipitation_mm"]
            .transform(
                lambda x: x.shift(1)
                .rolling(window)
                .mean()
            )
        )

    # --------------------------------------------------------
    # Previous-hour target
    # --------------------------------------------------------

    df["temperature_target"] = (
        grouped["temperature_2m"]
        .shift(-1)
    )

    df["rainfall_target"] = (
        grouped["precipitation_mm"]
        .shift(-1)
    )

    # --------------------------------------------------------
    # Location information
    # --------------------------------------------------------

    # Latitude/longitude are static for each location,
    # so retain them as model features.
    df["latitude"] = df["latitude"].astype(float)
    df["longitude"] = df["longitude"].astype(float)

    return df


# ============================================================
# TEMPERATURE DATASET
# ============================================================

def build_temperature_dataset(df):

    print("\nBuilding temperature ML dataset...")

    feature_columns = [
        "location_code",
        "timestamp",
        "latitude",
        "longitude",

        "temperature_2m",
        "relative_humidity_2m",
        "surface_pressure_hpa",
        "wind_speed_10m",
        "cloud_cover",
        "precipitation_mm",

        "hour",
        "day_of_week",
        "day_of_year",
        "month",

        "hour_sin",
        "hour_cos",
        "day_of_year_sin",
        "day_of_year_cos",

        "temperature_lag_1",
        "temperature_lag_3",
        "temperature_lag_6",
        "temperature_lag_12",
        "temperature_lag_24",

        "humidity_lag_1",
        "humidity_lag_3",
        "humidity_lag_6",
        "humidity_lag_12",
        "humidity_lag_24",

        "temperature_roll_mean_6",
        "temperature_roll_std_6",
        "temperature_roll_mean_12",
        "temperature_roll_std_12",
        "temperature_roll_mean_24",
        "temperature_roll_std_24",

        "rainfall_roll_sum_6",
        "rainfall_roll_sum_12",
        "rainfall_roll_sum_24",

        "rainfall_roll_mean_6",
        "rainfall_roll_mean_12",
        "rainfall_roll_mean_24",

        "temperature_target",
    ]

    result = df[feature_columns].copy()

    result = result.dropna()

    print(
        f"Temperature feature rows: "
        f"{len(result):,}"
    )

    print(
        f"Temperature features: "
        f"{len(result.columns)}"
    )

    return result


# ============================================================
# RAINFALL DATASET
# ============================================================

def build_rainfall_dataset(df):

    print("\nBuilding rainfall ML dataset...")

    feature_columns = [
        "location_code",
        "timestamp",
        "latitude",
        "longitude",

        "temperature_2m",
        "relative_humidity_2m",
        "surface_pressure_hpa",
        "wind_speed_10m",
        "cloud_cover",

        "precipitation_mm",

        "hour",
        "day_of_week",
        "day_of_year",
        "month",

        "hour_sin",
        "hour_cos",
        "day_of_year_sin",
        "day_of_year_cos",

        "rainfall_lag_1",
        "rainfall_lag_3",
        "rainfall_lag_6",
        "rainfall_lag_12",
        "rainfall_lag_24",

        "temperature_lag_1",
        "temperature_lag_3",
        "temperature_lag_6",
        "temperature_lag_12",
        "temperature_lag_24",

        "rainfall_roll_sum_6",
        "rainfall_roll_sum_12",
        "rainfall_roll_sum_24",

        "rainfall_roll_mean_6",
        "rainfall_roll_mean_12",
        "rainfall_roll_mean_24",

        "rainfall_target",
    ]

    result = df[feature_columns].copy()

    result = result.dropna()

    print(
        f"Rainfall feature rows: "
        f"{len(result):,}"
    )

    print(
        f"Rainfall features: "
        f"{len(result.columns)}"
    )

    return result


# ============================================================
# SAVE DATASETS
# ============================================================

def save_dataset(
    df,
    output_file,
):

    output_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    df.to_csv(
        output_file,
        index=False,
    )

    print(
        f"Saved: {output_file}"
    )

    print(
        f"Rows: {len(df):,}"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print("500-LOCATION WEATHER FEATURE GENERATION")
    print("=" * 70)

    # --------------------------------------------------------
    # Load
    # --------------------------------------------------------

    df = load_weather_data()

    # --------------------------------------------------------
    # Basic validation
    # --------------------------------------------------------

    print("\nValidating dataset...")

    print(
        f"Locations: "
        f"{df['location_code'].nunique()}"
    )

    print(
        f"Rows: "
        f"{len(df):,}"
    )

    print(
        f"Time range: "
        f"{df['timestamp'].min()} → "
        f"{df['timestamp'].max()}"
    )

    # --------------------------------------------------------
    # Feature engineering
    # --------------------------------------------------------

    df = create_features(df)

    # --------------------------------------------------------
    # Build temperature dataset
    # --------------------------------------------------------

    temperature_df = build_temperature_dataset(df)

    # --------------------------------------------------------
    # Build rainfall dataset
    # --------------------------------------------------------

    rainfall_df = build_rainfall_dataset(df)

    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    print("\nSaving feature datasets...")

    save_dataset(
        temperature_df,
        TEMPERATURE_OUTPUT,
    )

    save_dataset(
        rainfall_df,
        RAINFALL_OUTPUT,
    )

    # --------------------------------------------------------
    # Final summary
    # --------------------------------------------------------

    print("\n" + "=" * 70)
    print("FEATURE GENERATION COMPLETE")
    print("=" * 70)

    print(
        f"Weather observations : {len(df):,}"
    )

    print(
        f"Locations             : "
        f"{df['location_code'].nunique():,}"
    )

    print(
        f"Temperature rows      : "
        f"{len(temperature_df):,}"
    )

    print(
        f"Rainfall rows         : "
        f"{len(rainfall_df):,}"
    )

    print(
        f"\nTemperature file:"
        f"\n{TEMPERATURE_OUTPUT}"
    )

    print(
        f"\nRainfall file:"
        f"\n{RAINFALL_OUTPUT}"
    )

    print("=" * 70)


if __name__ == "__main__":
    main()