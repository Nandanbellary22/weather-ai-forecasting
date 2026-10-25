
import json
import hashlib
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch import nn

ROOT = Path(__file__).resolve().parent.parent
CANDIDATE = ROOT / "models" / "weather" / "candidate_temperature_hybrid"
CHECKPOINT_PATH = CANDIDATE / "temperature_mlp_candidate.pt"
CONFIG_PATH = CANDIDATE / "temperature_hybrid_config.json"
CSV_PATH = ROOT / "data" / "processed" / "weather_features" / "temperature_features_500.csv"

REPORT_PATH = CANDIDATE / "backtest_oct17_oct21_report.json"
MONTHLY_PATH = CANDIDATE / "backtest_oct17_oct21_monthly.csv"
LOCATION_PATH = CANDIDATE / "backtest_oct17_oct21_by_location.csv"

START = pd.Timestamp("2026-10-17 00:00:00")
END = pd.Timestamp("2026-10-22 00:00:00")
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
        "hybrid_wins": 0,
    }


def add_stats(stats, hybrid_error, baseline_error):
    stats["count"] += len(hybrid_error)
    stats["hybrid_abs"] += float(np.abs(hybrid_error).sum())
    stats["hybrid_sq"] += float(np.square(hybrid_error).sum())
    stats["baseline_abs"] += float(np.abs(baseline_error).sum())
    stats["baseline_sq"] += float(np.square(baseline_error).sum())
    stats["hybrid_wins"] += int(
        (np.abs(hybrid_error) < np.abs(baseline_error)).sum()
    )


def finish_stats(stats):
    n = stats["count"]
    if not n:
        return {"samples": 0}

    hybrid_mae = stats["hybrid_abs"] / n
    baseline_mae = stats["baseline_abs"] / n

    return {
        "samples": n,
        "hybrid_mae": hybrid_mae,
        "hybrid_rmse": float(np.sqrt(stats["hybrid_sq"] / n)),
        "baseline_mae": baseline_mae,
        "baseline_rmse": float(np.sqrt(stats["baseline_sq"] / n)),
        "hybrid_mae_improvement_percent": (
            (baseline_mae - hybrid_mae) / baseline_mae * 100
            if baseline_mae
            else None
        ),
        "hybrid_wins_percent": stats["hybrid_wins"] / n * 100,
    }


def main():
    started = time.time()

    for path in (CHECKPOINT_PATH, CONFIG_PATH, CSV_PATH):
        if not path.is_file():
            raise FileNotFoundError(f"Required file missing: {path}")

    checkpoint_hash = hashlib.sha256(CHECKPOINT_PATH.read_bytes()).hexdigest()
    checkpoint = torch.load(
        CHECKPOINT_PATH, map_location="cpu", weights_only=False
    )
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    features = list(checkpoint["input_features"])
    means = np.asarray(checkpoint["normalization_means"], dtype=np.float32)
    scales = np.asarray(checkpoint["normalization_scales"], dtype=np.float32)
    selection = config["location_selection"]
    alpha = float(config["calibration"]["alpha"])

    if len(features) != 38 or means.shape != (38,) or scales.shape != (38,):
        raise ValueError("Unexpected checkpoint feature or normalization shape.")
    if not np.isfinite(means).all() or not np.isfinite(scales).all():
        raise ValueError("Non-finite normalization values.")
    if (scales <= 0).any():
        raise ValueError("Normalization scales must be positive.")

    model = WeatherMLP(len(features))
    model.load_state_dict(checkpoint["model_state_dict"], strict=True)
    model.eval()

    required = [
        "location_code", "timestamp", "temperature_2m",
        "temperature_target", *features
    ]
    header = pd.read_csv(CSV_PATH, nrows=0).columns.tolist()
    missing = sorted(set(required) - set(header))
    if missing:
        raise ValueError(f"Missing required CSV columns: {missing}")

    overall = new_stats()
    monthly = {}
    by_location = {}
    valid_rows = 0
    locations_seen = set()
    first_timestamp = None
    last_timestamp = None

    print("Checkpoint SHA-256:", checkpoint_hash, flush=True)
    print("Evaluating:", START, "through", END, "(end exclusive)", flush=True)

    for chunk in pd.read_csv(
        CSV_PATH, usecols=required, chunksize=CHUNK_SIZE
    ):
        timestamps = pd.to_datetime(chunk["timestamp"], errors="coerce")
        in_window = (timestamps >= START) & (timestamps < END)
        if not in_window.any():
            continue

        chunk = chunk.loc[in_window].copy()
        timestamps = timestamps.loc[in_window]
        chunk["location_code"] = chunk["location_code"].astype(str)

        locations = chunk["location_code"].to_numpy()
        current = pd.to_numeric(
            chunk["temperature_2m"], errors="coerce"
        ).to_numpy(dtype=np.float64)
        target = pd.to_numeric(
            chunk["temperature_target"], errors="coerce"
        ).to_numpy(dtype=np.float64)
        X = chunk[features].apply(pd.to_numeric, errors="coerce").to_numpy(
            dtype=np.float32
        )

        valid = (
            pd.Series(locations).isin(selection).to_numpy()
            & timestamps.notna().to_numpy()
            & np.isfinite(X).all(axis=1)
            & np.isfinite(current)
            & np.isfinite(target)
        )
        if not valid.any():
            continue

        X = X[valid]
        current = current[valid]
        target = target[valid]
        locations = locations[valid]
        valid_times = timestamps.iloc[np.flatnonzero(valid)]

        normalized = np.clip((X - means) / scales, -10.0, 10.0)
        with torch.no_grad():
            raw_prediction = model(
                torch.from_numpy(normalized.astype(np.float32))
            ).squeeze(1).numpy().astype(np.float64)

        hybrid = current.copy()
        use_model = np.array(
            [selection[location] == "global" for location in locations]
        )
        hybrid[use_model] = current[use_model] + alpha * (
            raw_prediction[use_model] - current[use_model]
        )

        hybrid_error = hybrid - target
        baseline_error = current - target
        add_stats(overall, hybrid_error, baseline_error)
        valid_rows += len(target)
        locations_seen.update(locations.tolist())

        for month in pd.to_datetime(valid_times).dt.strftime("%Y-%m").unique():
            mask = pd.to_datetime(valid_times).dt.strftime("%Y-%m").to_numpy() == month
            monthly.setdefault(month, new_stats())
            add_stats(monthly[month], hybrid_error[mask], baseline_error[mask])

        for location in np.unique(locations):
            mask = locations == location
            by_location.setdefault(location, new_stats())
            add_stats(
                by_location[location], hybrid_error[mask], baseline_error[mask]
            )

    if not valid_rows:
        raise RuntimeError("No valid rows found in the requested date window.")

    report = {
        "evaluation": "frozen_temperature_hybrid_later_period_backtest",
        "start_inclusive": str(START),
        "end_exclusive": str(END),
        "checkpoint_sha256": checkpoint_hash,
        "checkpoint_path": str(CHECKPOINT_PATH.relative_to(ROOT)),
        "feature_file": str(CSV_PATH.relative_to(ROOT)),
        "alpha": alpha,
        "rows_evaluated": valid_rows,
        "locations_evaluated": len(locations_seen),
        "first_feature_timestamp": str(START),
        "last_window_end_exclusive": str(END),
        "overall_metrics": finish_stats(overall),
        "monthly_metrics": {
            month: finish_stats(stats) for month, stats in sorted(monthly.items())
        },
        "caveats": [
            "The checkpoint training cutoff is undocumented, so independence is not proven.",
            "This is retrospective evaluation, not live forecast validation.",
            "The temperature_target column is evaluation-only, not a model input.",
            "Existing reports and production files were not modified by this script.",
        ],
        "elapsed_seconds": round(time.time() - started, 2),
    }

    CANDIDATE.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    pd.DataFrame([
        {"month": month, **metrics}
        for month, metrics in report["monthly_metrics"].items()
    ]).to_csv(MONTHLY_PATH, index=False)
    pd.DataFrame([
        {"location_code": location, **finish_stats(stats)}
        for location, stats in sorted(by_location.items())
    ]).to_csv(LOCATION_PATH, index=False)

    print("\nOVERALL METRICS")
    print(json.dumps(report["overall_metrics"], indent=2))
    print("\nMONTHLY METRICS")
    print(json.dumps(report["monthly_metrics"], indent=2))
    print("\nLocations evaluated:", len(locations_seen))
    print("\nSaved reports:")
    print(REPORT_PATH)
    print(MONTHLY_PATH)
    print(LOCATION_PATH)


if __name__ == "__main__":
    main()
