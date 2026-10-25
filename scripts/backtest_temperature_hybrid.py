
import json
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch import nn

ROOT = Path(__file__).resolve().parent.parent
CANDIDATE = ROOT / "models/weather/candidate_temperature_hybrid"
CHECKPOINT_PATH = CANDIDATE / "temperature_mlp_candidate.pt"
CONFIG_PATH = CANDIDATE / "temperature_hybrid_config.json"
CSV_PATH = ROOT / "data/processed/weather_features/temperature_features_500.csv"

REPORT_PATH = CANDIDATE / "historical_backtest_report.json"
MONTHLY_PATH = CANDIDATE / "historical_backtest_monthly.csv"
LOCATION_PATH = CANDIDATE / "historical_backtest_by_location.csv"

CHUNK_SIZE = 100_000


class WeatherMLP(nn.Module):
    def __init__(self, input_size):
        super().__init__()
        self.network = nn.Sequential(
            nn.Linear(input_size, 128),
            nn.ReLU(),
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Linear(64, 1),
        )

    def forward(self, x):
        return self.network(x)


def new_stats():
    return {
        "count": 0,
        "hybrid_abs": 0.0,
        "hybrid_sq": 0.0,
        "baseline_abs": 0.0,
        "baseline_sq": 0.0,
        "hybrid_better": 0,
    }


def add_stats(stats, hybrid_error, baseline_error):
    stats["count"] += int(len(hybrid_error))
    stats["hybrid_abs"] += float(np.abs(hybrid_error).sum())
    stats["hybrid_sq"] += float(np.square(hybrid_error).sum())
    stats["baseline_abs"] += float(np.abs(baseline_error).sum())
    stats["baseline_sq"] += float(np.square(baseline_error).sum())
    stats["hybrid_better"] += int(
        (np.abs(hybrid_error) < np.abs(baseline_error)).sum()
    )


def finish_stats(stats):
    n = stats["count"]
    if not n:
        return {
            "samples": 0,
            "hybrid_mae": None,
            "hybrid_rmse": None,
            "baseline_mae": None,
            "baseline_rmse": None,
            "hybrid_mae_improvement_percent": None,
            "hybrid_wins_percent": None,
        }

    hybrid_mae = stats["hybrid_abs"] / n
    baseline_mae = stats["baseline_abs"] / n
    hybrid_rmse = np.sqrt(stats["hybrid_sq"] / n)
    baseline_rmse = np.sqrt(stats["baseline_sq"] / n)

    improvement = (
        (baseline_mae - hybrid_mae) / baseline_mae * 100.0
        if baseline_mae > 0
        else None
    )

    return {
        "samples": n,
        "hybrid_mae": float(hybrid_mae),
        "hybrid_rmse": float(hybrid_rmse),
        "baseline_mae": float(baseline_mae),
        "baseline_rmse": float(baseline_rmse),
        "hybrid_mae_improvement_percent": (
            float(improvement) if improvement is not None else None
        ),
        "hybrid_wins_percent": float(stats["hybrid_better"] / n * 100.0),
    }


def main():
    started = time.perf_counter()
    print("=== Historical temperature hybrid backtest ===", flush=True)

    for path in (CHECKPOINT_PATH, CONFIG_PATH, CSV_PATH):
        if not path.is_file():
            raise FileNotFoundError(f"Required file missing: {path}")

    checkpoint = torch.load(
        CHECKPOINT_PATH, map_location="cpu", weights_only=False
    )
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        config = json.load(f)

    features = list(checkpoint["input_features"])
    means = np.asarray(checkpoint["normalization_means"], dtype=np.float32)
    scales = np.asarray(checkpoint["normalization_scales"], dtype=np.float32)
    selection = {str(k): v for k, v in config["location_selection"].items()}
    alpha = float(config["calibration"]["alpha"])

    if len(features) != 38 or len(set(features)) != 38:
        raise ValueError("Expected 38 unique checkpoint input features.")
    if means.shape != (38,) or scales.shape != (38,):
        raise ValueError("Checkpoint normalization arrays must have length 38.")
    if not np.isfinite(means).all() or not np.isfinite(scales).all():
        raise ValueError("Normalization arrays contain non-finite values.")
    if (scales <= 0).any():
        raise ValueError("Normalization scales must be positive.")
    if not 0 <= alpha <= 1:
        raise ValueError("Calibration alpha must be between 0 and 1.")
    if len(selection) != 500:
        raise ValueError("Expected configuration for exactly 500 locations.")
    if set(selection.values()) - {"global", "baseline"}:
        raise ValueError("Unknown location-selection rule.")

    model = WeatherMLP(len(features))
    model.load_state_dict(checkpoint["model_state_dict"], strict=True)
    model.eval()

    header = pd.read_csv(CSV_PATH, nrows=0).columns.tolist()
    required = {
        "location_code",
        "timestamp",
        "temperature_2m",
        "temperature_target",
        *features,
    }
    missing = required - set(header)
    if missing:
        raise ValueError(f"CSV missing required columns: {sorted(missing)}")

    usecols = list(dict.fromkeys([
        "location_code",
        "timestamp",
        "temperature_2m",
        "temperature_target",
        *features,
    ]))

    overall = new_stats()
    monthly = defaultdict(new_stats)
    locations = defaultdict(new_stats)
    seen_locations = set()
    rows_scanned = 0
    valid_rows = 0
    invalid_rows = 0
    first_timestamp = None
    last_timestamp = None

    print("Checkpoint loaded; scanning historical feature rows.", flush=True)

    for chunk in pd.read_csv(
        CSV_PATH, usecols=usecols, chunksize=CHUNK_SIZE
    ):
        rows_scanned += len(chunk)
        chunk["location_code"] = chunk["location_code"].astype(str)
        timestamps = pd.to_datetime(chunk["timestamp"], errors="coerce")

        valid_locations = chunk["location_code"].isin(selection)
        X = chunk[features].apply(
            pd.to_numeric, errors="coerce"
        ).to_numpy(dtype=np.float32)
        current = pd.to_numeric(
            chunk["temperature_2m"], errors="coerce"
        ).to_numpy(dtype=np.float64)
        target = pd.to_numeric(
            chunk["temperature_target"], errors="coerce"
        ).to_numpy(dtype=np.float64)

        valid = (
            valid_locations.to_numpy()
            & timestamps.notna().to_numpy()
            & np.isfinite(X).all(axis=1)
            & np.isfinite(current)
            & np.isfinite(target)
        )

        invalid_rows += int((~valid).sum())
        if not valid.any():
            continue

        valid_indices = np.flatnonzero(valid)
        valid_X = X[valid]
        valid_current = current[valid]
        valid_target = target[valid]
        valid_locs = chunk["location_code"].to_numpy()[valid]
        valid_times = timestamps.iloc[valid_indices]

        normalized = np.clip((valid_X - means) / scales, -10.0, 10.0)
        with torch.inference_mode():
            mlp_prediction = (
                model(torch.from_numpy(normalized))
                .squeeze(1)
                .numpy()
                .astype(np.float64)
            )

        if not np.isfinite(mlp_prediction).all():
            raise ValueError("Model produced non-finite predictions.")

        hybrid = valid_current.copy()
        global_mask = np.array(
            [selection[loc] == "global" for loc in valid_locs],
            dtype=bool,
        )
        hybrid[global_mask] += alpha * (
            mlp_prediction[global_mask] - valid_current[global_mask]
        )

        hybrid_error = hybrid - valid_target
        baseline_error = valid_current - valid_target

        add_stats(overall, hybrid_error, baseline_error)
        valid_rows += len(valid_indices)
        seen_locations.update(valid_locs.tolist())

        chunk_first = valid_times.min()
        chunk_last = valid_times.max()
        first_timestamp = (
            chunk_first if first_timestamp is None
            else min(first_timestamp, chunk_first)
        )
        last_timestamp = (
            chunk_last if last_timestamp is None
            else max(last_timestamp, chunk_last)
        )

        months = valid_times.dt.strftime("%Y-%m").to_numpy()

        for month in np.unique(months):
            mask = months == month
            add_stats(
                monthly[month],
                hybrid_error[mask],
                baseline_error[mask],
            )

        for loc in np.unique(valid_locs):
            mask = valid_locs == loc
            add_stats(
                locations[loc],
                hybrid_error[mask],
                baseline_error[mask],
            )

        if rows_scanned % 500_000 < CHUNK_SIZE:
            print(
                f"Scanned {rows_scanned:,} rows; "
                f"valid evaluation samples {valid_rows:,}",
                flush=True,
            )

    missing_locations = sorted(set(selection) - seen_locations)
    if missing_locations:
        raise ValueError(
            f"No valid evaluation rows for {len(missing_locations)} locations: "
            f"{missing_locations[:10]}"
        )
    if valid_rows == 0:
        raise ValueError("No valid historical evaluation rows were found.")

    monthly_rows = []
    for month in sorted(monthly):
        monthly_rows.append({
            "month": month,
            **finish_stats(monthly[month]),
        })

    location_rows = []
    for loc in sorted(locations):
        location_rows.append({
            "location_code": loc,
            "selection_rule": selection[loc],
            **finish_stats(locations[loc]),
        })

    monthly_df = pd.DataFrame(monthly_rows)
    location_df = pd.DataFrame(location_rows)

    CANDIDATE.mkdir(parents=True, exist_ok=True)
    monthly_df.to_csv(MONTHLY_PATH, index=False)
    location_df.to_csv(LOCATION_PATH, index=False)

    report = {
        "status": "historical_backtest_completed",
        "production_files_modified": False,
        "candidate_checkpoint": str(CHECKPOINT_PATH),
        "alpha": alpha,
        "feature_count": len(features),
        "configured_locations": len(selection),
        "locations_evaluated": len(seen_locations),
        "rows_scanned": rows_scanned,
        "valid_evaluation_samples": valid_rows,
        "rows_excluded_for_invalid_data_or_unconfigured_location": invalid_rows,
        "first_feature_timestamp": str(first_timestamp),
        "last_feature_timestamp": str(last_timestamp),
        "target_semantics": (
            "temperature_target is expected to be the next hourly "
            "temperature for the same location."
        ),
        "overall_metrics": finish_stats(overall),
        "monthly_metrics": monthly_rows,
        "location_metrics_csv": str(LOCATION_PATH),
        "monthly_metrics_csv": str(MONTHLY_PATH),
        "interpretation_warning": (
            "This is a retrospective evaluation, not automatically an "
            "independent out-of-sample test. Confirm the candidate checkpoint "
            "training cutoff and location-selection tuning period before "
            "treating these metrics as independent temporal validation. "
            "The target column is used only for scoring, never as a model input."
        ),
        "elapsed_seconds": round(time.perf_counter() - started, 2),
    }

    with REPORT_PATH.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, allow_nan=False)

    print("\n=== HISTORICAL BACKTEST RESULTS ===")
    print("Rows scanned:", f"{rows_scanned:,}")
    print("Valid evaluation samples:", f"{valid_rows:,}")
    print("Locations evaluated:", len(seen_locations))
    print("Feature timestamp range:", first_timestamp, "to", last_timestamp)
    print(json.dumps(report["overall_metrics"], indent=2))
    print("\nMonthly metrics:")
    print(monthly_df.to_string(index=False))
    print("\nReports saved:")
    print(REPORT_PATH)
    print(MONTHLY_PATH)
    print(LOCATION_PATH)
    print("Production models/services were not modified.")
    print("Elapsed seconds:", report["elapsed_seconds"])


if __name__ == "__main__":
    main()
