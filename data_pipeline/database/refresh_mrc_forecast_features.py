"""Rebuild the one-hour MRC model feature snapshot from persisted telemetry."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pandas as pd

from backend.database import get_connection
from ml.features import create_mrc_features as feature_builder


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FEATURE_FILE = PROJECT_ROOT / "data" / "processed" / "mrc_hourly_features.csv"
BACKUP_FILE = FEATURE_FILE.with_suffix(FEATURE_FILE.suffix + ".before_refresh.bak")

MEASUREMENTS_QUERY = """
    SELECT station_id, timestamp_utc, water_level, rainfall,
           temperature, battery
    FROM mrc_hydromet_observations
    ORDER BY station_id, timestamp_utc
"""


def load_measurements(connection_factory=get_connection) -> pd.DataFrame:
    """Read persisted MRC history; never modify source observations."""
    connection = connection_factory()
    try:
        return pd.read_sql_query(MEASUREMENTS_QUERY, connection)
    finally:
        connection.close()


def build_feature_snapshot(measurements: pd.DataFrame) -> pd.DataFrame:
    """Use the canonical hourly, gap-aware MRC feature builder in memory."""
    required = {
        "station_id", "timestamp_utc", "water_level", "rainfall",
        "temperature", "battery",
    }
    missing = required - set(measurements.columns)
    if missing:
        raise ValueError(f"MRC measurements missing required columns: {sorted(missing)}")
    if measurements.empty:
        raise ValueError("No persisted MRC observations are available to build forecast features.")

    raw = measurements.copy()
    raw["station_id"] = feature_builder.preserve_station_ids(raw["station_id"])
    raw["timestamp_utc"] = pd.to_datetime(raw["timestamp_utc"], utc=True, errors="coerce")
    for column in ("water_level", "rainfall", "temperature", "battery"):
        raw[column] = pd.to_numeric(raw[column], errors="coerce")
    raw = raw.dropna(subset=["station_id", "timestamp_utc"])
    raw = raw.drop_duplicates(["station_id", "timestamp_utc"], keep="last")
    raw = raw.sort_values(["station_id", "timestamp_utc"]).reset_index(drop=True)
    if raw.empty:
        raise ValueError("MRC observations contained no valid station/timestamp rows.")

    hourly = feature_builder.aggregate_to_hourly(raw)
    grid = feature_builder.build_complete_hourly_grid(hourly)
    if grid.empty:
        raise ValueError("MRC observations did not produce an hourly feature timeline.")
    features = feature_builder.create_time_features(grid)
    features = feature_builder.create_lag_and_rolling_features(features)
    features = feature_builder.create_target(features)
    features = feature_builder.reorder_columns(features)
    features["station_id"] = feature_builder.preserve_station_ids(features["station_id"])

    if features.empty or features.duplicated(["station_id", "hour"]).any():
        raise ValueError("MRC feature snapshot is empty or contains duplicate station/hour rows.")
    if not {"hour_complete", "water_level", "target_is_next_hour"}.issubset(features.columns):
        raise ValueError("MRC feature snapshot is missing required inference fields.")
    return features


def refresh_mrc_forecast_features(
    measurements: pd.DataFrame | None = None,
    output_file: Path | str = FEATURE_FILE,
) -> dict:
    """Atomically refresh the derived feature CSV, retaining a one-time backup."""
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    source = load_measurements() if measurements is None else measurements
    features = build_feature_snapshot(source)

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output_path.stem}.", suffix=".tmp", dir=output_path.parent
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        features.to_csv(temporary_path, index=False)
        check = pd.read_csv(temporary_path, dtype={"station_id": "string"}, usecols=["station_id", "hour", "hour_complete"])
        if check.empty or check["station_id"].isna().any():
            raise ValueError("Written MRC feature snapshot failed its read-back validation.")
        backup_path = (
            BACKUP_FILE if output_path.resolve() == FEATURE_FILE.resolve()
            else output_path.with_suffix(output_path.suffix + ".before_refresh.bak")
        )
        if output_path.exists() and not backup_path.exists():
            shutil.copy2(output_path, backup_path)
        os.replace(temporary_path, output_path)
    finally:
        temporary_path.unlink(missing_ok=True)

    latest_complete = features.loc[features["hour_complete"].fillna(False), "hour"].max()
    return {
        "status": "success",
        "feature_rows": int(len(features)),
        "station_count": int(features["station_id"].nunique()),
        "latest_complete_hour_utc": latest_complete.isoformat() if pd.notna(latest_complete) else None,
        "feature_file": str(output_path),
    }
