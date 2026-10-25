
from pathlib import Path
import os

import numpy as np
import pandas as pd
import psycopg2


# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parents[2]
OUTPUT_DIR = BASE_DIR / "data" / "processed" / "weather_features"

TEMPERATURE_OUTPUT = OUTPUT_DIR / "temperature_features_500.csv"
RAINFALL_OUTPUT = OUTPUT_DIR / "rainfall_features_500.csv"

TEMPERATURE_TEMP = OUTPUT_DIR / "temperature_features_500.tmp.csv"
RAINFALL_TEMP = OUTPUT_DIR / "rainfall_features_500.tmp.csv"

EXPECTED_LOCATIONS = 500


# ============================================================
# DATABASE
# ============================================================

def get_connection():
    password = (
        os.environ.get("PGPASSWORD")
        or os.environ.get("POSTGRES_PASSWORD")
    )

    return psycopg2.connect(
        host="localhost",
        port=5432,
        dbname="weather_forecasting",
        user="postgres",
        password=password,
    )


# ============================================================
# LOAD WEATHER DATA
# ============================================================

def load_weather_data():
    print("Loading weather data from PostgreSQL...")

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

    with get_connection() as conn:
        df = pd.read_sql_query(query, conn)

    print(f"Rows loaded: {len(df):,}")
    print(f"Locations: {df['location_code'].nunique():,}")

    return df


# ============================================================
# VALIDATE SOURCE DATA
# ============================================================

def validate_source_data(df):
    print("\nValidating source data...")

    required_columns = [
        "location_code",
        "timestamp",
        "temperature_2m",
        "precipitation_mm",
        "relative_humidity_2m",
        "surface_pressure_hpa",
        "wind_speed_10m",
        "cloud_cover",
        "latitude",
        "longitude",
    ]

    missing_columns = sorted(set(required_columns) - set(df.columns))
    if missing_columns:
        raise ValueError(f"Missing required columns: {missing_columns}")

    if df["location_code"].nunique() != EXPECTED_LOCATIONS:
        raise ValueError(
            f"Expected {EXPECTED_LOCATIONS} locations, "
            f"found {df['location_code'].nunique()}."
        )

    df = df.copy()
    df["location_code"] = df["location_code"].astype("string").str.strip()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")

    if df["location_code"].isna().any() or df["location_code"].eq("").any():
        raise ValueError("Source contains missing location IDs.")

    if df["timestamp"].isna().any():
        raise ValueError("Source contains invalid timestamps.")

    if df.duplicated(["location_code", "timestamp"]).any():
        raise ValueError("Source contains duplicate location/timestamp keys.")

    df = df.sort_values(["location_code", "timestamp"]).reset_index(drop=True)
    coverage = df.groupby("location_code")["timestamp"].agg(["min", "max", "count"])
    if coverage[["min", "max"]].nunique().max() != 1:
        raise ValueError("Locations do not share a common hourly time range.")

    if coverage["count"].nunique() != 1:
        raise ValueError("Locations do not have equal hourly coverage.")

    earliest = coverage["min"].min()
    latest = coverage["max"].max()

    # Verify consecutive observations are exactly one hour apart.
    gaps = (
        df.groupby("location_code")["timestamp"]
        .diff()
        .dropna()
    )

    if not gaps.eq(pd.Timedelta(hours=1)).all():
        raise ValueError("Source contains non-hourly timestamp gaps.")

    expected_hours = int((latest - earliest) / pd.Timedelta(hours=1)) + 1
    if not coverage["count"].eq(expected_hours).all():
        raise ValueError("At least one location has incomplete hourly coverage.")

    numeric_columns = [
        "temperature_2m",
        "precipitation_mm",
        "relative_humidity_2m",
        "surface_pressure_hpa",
        "wind_speed_10m",
        "cloud_cover",
        "latitude",
        "longitude",
    ]

    missing_values = df[numeric_columns].isna().sum()
    missing_values = missing_values[missing_values > 0]

    if not missing_values.empty:
        raise ValueError(
            "Source contains missing values in required numeric fields:\n"
            f"{missing_values}"
        )

    print(f"Source rows: {len(df):,}")
    print(f"Locations: {df['location_code'].nunique():,}")
    print(f"Time range: {earliest} -> {latest}")
    print("Hourly continuity: passed")
    print("Duplicate keys: 0")
    print("Missing required numeric values: 0")

    return df


# ============================================================
# FEATURE ENGINEERING
# ============================================================

def create_features(df):
    print("\nCreating temporal features...")

    df = df.copy()
    df = df.sort_values(
        ["location_code", "timestamp"]
    ).reset_index(drop=True)

    df["hour"] = df["timestamp"].dt.hour
    df["day_of_week"] = df["timestamp"].dt.dayofweek
    df["day_of_year"] = df["timestamp"].dt.dayofyear
    df["month"] = df["timestamp"].dt.month

    df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24)

    df["day_of_year_sin"] = np.sin(
        2 * np.pi * df["day_of_year"] / 365
    )
    df["day_of_year_cos"] = np.cos(
        2 * np.pi * df["day_of_year"] / 365
    )

    print("Creating lag features...")

    grouped = df.groupby("location_code", sort=False)

    for lag in [1, 3, 6, 12, 24]:
        df[f"temperature_lag_{lag}"] = (
            grouped["temperature_2m"].shift(lag)
        )
        df[f"rainfall_lag_{lag}"] = (
            grouped["precipitation_mm"].shift(lag)
        )
        df[f"humidity_lag_{lag}"] = (
            grouped["relative_humidity_2m"].shift(lag)
        )

    print("Creating rolling statistics...")

    for window in [6, 12, 24]:
        df[f"temperature_roll_mean_{window}"] = (
            df.groupby("location_code", sort=False)["temperature_2m"]
            .transform(
                lambda x: x.shift(1).rolling(window).mean()
            )
        )

        df[f"temperature_roll_std_{window}"] = (
            df.groupby("location_code", sort=False)["temperature_2m"]
            .transform(
                lambda x: x.shift(1).rolling(window).std()
            )
        )

        df[f"rainfall_roll_sum_{window}"] = (
            df.groupby("location_code", sort=False)["precipitation_mm"]
            .transform(
                lambda x: x.shift(1).rolling(window).sum()
            )
        )

        df[f"rainfall_roll_mean_{window}"] = (
            df.groupby("location_code", sort=False)["precipitation_mm"]
            .transform(
                lambda x: x.shift(1).rolling(window).mean()
            )
        )

    print("Creating next-hour targets...")

    df["temperature_target"] = (
        df.groupby("location_code", sort=False)["temperature_2m"]
        .shift(-1)
    )

    df["rainfall_target"] = (
        df.groupby("location_code", sort=False)["precipitation_mm"]
        .shift(-1)
    )

    df["latitude"] = df["latitude"].astype(float)
    df["longitude"] = df["longitude"].astype(float)

    return df


# ============================================================
# BUILD TEMPERATURE DATASET
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

    result = df[feature_columns].dropna().copy()

    print(f"Temperature feature rows: {len(result):,}")
    print(f"Temperature features: {len(result.columns)}")

    return result


# ============================================================
# BUILD RAINFALL DATASET
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

    result = df[feature_columns].dropna().copy()

    print(f"Rainfall feature rows: {len(result):,}")
    print(f"Rainfall features: {len(result.columns)}")

    return result


# ============================================================
# VALIDATE FEATURE DATASETS
# ============================================================

def validate_feature_dataset(df, name):
    if df.empty:
        raise ValueError(f"{name} dataset is empty.")

    if df["location_code"].nunique() != EXPECTED_LOCATIONS:
        raise ValueError(
            f"{name}: expected {EXPECTED_LOCATIONS} locations, "
            f"found {df['location_code'].nunique()}."
        )

    if df.duplicated(["location_code", "timestamp"]).any():
        raise ValueError(f"{name}: duplicate location/timestamp keys.")

    if df.isna().any().any():
        raise ValueError(f"{name}: unexpected missing feature values.")

    print(
        f"{name} validation passed: "
        f"{len(df):,} rows, "
        f"{df['location_code'].nunique()} locations, "
        f"{df['timestamp'].min()} -> {df['timestamp'].max()}"
    )


# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 70)
    print("500-LOCATION WEATHER FEATURE GENERATION")
    print("=" * 70)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    df = load_weather_data()
    df = validate_source_data(df)

    df = create_features(df)

    temperature_df = build_temperature_dataset(df)
    rainfall_df = build_rainfall_dataset(df)

    validate_feature_dataset(temperature_df, "Temperature")
    validate_feature_dataset(rainfall_df, "Rainfall")

    print("\nWriting temporary feature files...")

    temperature_df.to_csv(TEMPERATURE_TEMP, index=False)
    rainfall_df.to_csv(RAINFALL_TEMP, index=False)

    # Check the written files before replacing the existing outputs.
    temperature_check = pd.read_csv(
        TEMPERATURE_TEMP,
        usecols=["location_code", "timestamp"],
    )
    rainfall_check = pd.read_csv(
        RAINFALL_TEMP,
        usecols=["location_code", "timestamp"],
    )

    if len(temperature_check) != len(temperature_df):
        raise ValueError("Temperature temporary-file row count mismatch.")

    if len(rainfall_check) != len(rainfall_df):
        raise ValueError("Rainfall temporary-file row count mismatch.")

    # Replacements happen only after both datasets have been generated
    # and their temporary files have passed row-count checks.
    os.replace(TEMPERATURE_TEMP, TEMPERATURE_OUTPUT)
    os.replace(RAINFALL_TEMP, RAINFALL_OUTPUT)

    print("\n" + "=" * 70)
    print("FEATURE GENERATION COMPLETE")
    print("=" * 70)
    print(f"Weather observations: {len(df):,}")
    print(f"Locations: {df['location_code'].nunique():,}")
    print(f"Temperature rows: {len(temperature_df):,}")
    print(f"Rainfall rows: {len(rainfall_df):,}")
    print(f"Temperature file: {TEMPERATURE_OUTPUT}")
    print(f"Rainfall file: {RAINFALL_OUTPUT}")
    print("=" * 70)


if __name__ == "__main__":
    main()
