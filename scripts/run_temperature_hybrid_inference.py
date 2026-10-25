import json
import time
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
OUTPUT_CSV = CANDIDATE / "latest_500_predictions.csv"
OUTPUT_JSON = CANDIDATE / "bulk_inference_report.json"

CHUNK_SIZE = 100_000
STALE_AFTER_HOURS = 24


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


def main():
    started = time.perf_counter()
    print("=== Loading candidate ===", flush=True)

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
    selection = config["location_selection"]
    alpha = float(config["calibration"]["alpha"])

    if len(features) != 38 or len(set(features)) != 38:
        raise ValueError("Checkpoint must contain 38 unique input features.")
    if means.shape != (38,) or scales.shape != (38,):
        raise ValueError("Normalization arrays must have length 38.")
    if not np.isfinite(means).all() or not np.isfinite(scales).all():
        raise ValueError("Normalization arrays contain non-finite values.")
    if (scales <= 0).any():
        raise ValueError("Normalization scales must be positive.")
    if not 0 <= alpha <= 1:
        raise ValueError("Calibration alpha must be between 0 and 1.")
    if len(selection) != 500:
        raise ValueError("Expected 500 configured locations.")
    if set(selection.values()) - {"global", "baseline"}:
        raise ValueError("Unknown location-selection rule.")

    model = WeatherMLP(len(features))
    model.load_state_dict(checkpoint["model_state_dict"], strict=True)
    model.eval()

    print("Checkpoint loaded. Features:", len(features), flush=True)
    print("Scanning CSV in chunks; this may take a few minutes.", flush=True)

    header = pd.read_csv(CSV_PATH, nrows=0).columns.tolist()
    required = {"location_code", "timestamp", "temperature_2m", *features}
    missing = required - set(header)
    if missing:
        raise ValueError(f"CSV is missing columns: {sorted(missing)}")

    target_available = "temperature_target" in header
    usecols = ["location_code", "timestamp", "temperature_2m", *features]
    if target_available:
        usecols.append("temperature_target")

    latest = {}
    rows_scanned = 0

    for chunk in pd.read_csv(CSV_PATH, usecols=usecols, chunksize=CHUNK_SIZE):
        rows_scanned += len(chunk)
        chunk["location_code"] = chunk["location_code"].astype(str)
        chunk["_ts"] = pd.to_datetime(chunk["timestamp"], errors="coerce")
        chunk = chunk.dropna(subset=["_ts", "location_code"])

        # Keep one latest timestamp row per location from this chunk.
        indices = chunk.groupby("location_code", sort=False)["_ts"].idxmax()
        for _, row in chunk.loc[indices].iterrows():
            loc = row["location_code"]
            old = latest.get(loc)
            if old is None or row["_ts"] >= old["_ts"]:
                latest[loc] = row

        if rows_scanned % 500_000 == 0:
            print(
                f"Scanned {rows_scanned:,} rows; "
                f"{len(latest)} locations found",
                flush=True,
            )

    expected = set(map(str, selection.keys()))
    found = set(latest.keys())
    missing_locations = sorted(expected - found)
    if missing_locations:
        raise ValueError(
            f"Missing {len(missing_locations)} configured locations: "
            f"{missing_locations[:10]}"
        )

    rows = [latest[loc] for loc in sorted(expected)]
    latest_df = pd.DataFrame(rows).reset_index(drop=True)
    X = latest_df[features].apply(pd.to_numeric, errors="coerce").to_numpy(
        dtype=np.float32
    )
    current = pd.to_numeric(
        latest_df["temperature_2m"], errors="coerce"
    ).to_numpy(dtype=np.float64)

    if not np.isfinite(X).all():
        raise ValueError("Latest rows contain missing/non-finite input features.")
    if not np.isfinite(current).all():
        raise ValueError("Current temperature contains missing/non-finite values.")

    X = np.clip((X - means) / scales, -10.0, 10.0)
    with torch.inference_mode():
        mlp_pred = model(torch.from_numpy(X)).squeeze(1).numpy().astype(np.float64)

    if not np.isfinite(mlp_pred).all():
        raise ValueError("MLP predictions contain non-finite values.")

    locations = latest_df["location_code"].astype(str).tolist()
    rules = [selection[loc] for loc in locations]
    global_mask = np.array([r == "global" for r in rules])

    hybrid = current.copy()
    hybrid[global_mask] = current[global_mask] + alpha * (
        mlp_pred[global_mask] - current[global_mask]
    )

    result = pd.DataFrame({
        "location_code": locations,
        "source_timestamp": latest_df["timestamp"].astype(str).to_numpy(),
        "selection_rule": rules,
        "current_temperature": current,
        "mlp_prediction": mlp_pred,
        "hybrid_prediction": hybrid,
        "calibration_alpha": alpha,
    })

    evaluation = {
        "target_rows_available": 0,
        "note": "Target is evaluation-only, never a model input.",
    }
    if target_available:
        target = pd.to_numeric(
            latest_df["temperature_target"], errors="coerce"
        ).to_numpy(dtype=np.float64)
        result["temperature_target_for_evaluation_only"] = target
        valid = np.isfinite(target)
        evaluation["target_rows_available"] = int(valid.sum())
        if valid.any():
            e_h = hybrid[valid] - target[valid]
            e_b = current[valid] - target[valid]
            evaluation.update({
                "hybrid_mae": float(np.mean(np.abs(e_h))),
                "hybrid_rmse": float(np.sqrt(np.mean(e_h ** 2))),
                "baseline_mae": float(np.mean(np.abs(e_b))),
                "baseline_rmse": float(np.sqrt(np.mean(e_b ** 2))),
                "warning": (
                    "Verify target timestamp semantics before interpreting "
                    "these latest-row metrics as forecast validation."
                ),
            })

    latest_ts = pd.to_datetime(latest_df["timestamp"], errors="coerce").max()
    now = pd.Timestamp.now()
    age_hours = (now - latest_ts).total_seconds() / 3600

    CANDIDATE.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUTPUT_CSV, index=False)

    report = {
        "status": "candidate_inference_completed",
        "production_files_modified": False,
        "rows_scanned": rows_scanned,
        "locations_predicted": len(result),
        "feature_count": len(features),
        "alpha": alpha,
        "selection_counts": {
            "global": int(global_mask.sum()),
            "baseline": int((~global_mask).sum()),
        },
        "latest_source_timestamp": str(latest_ts),
        "source_data_age_hours": round(float(age_hours), 2),
        "source_data_stale": bool(age_hours > STALE_AFTER_HOURS),
        "evaluation": evaluation,
        "elapsed_seconds": round(time.perf_counter() - started, 2),
        "prediction_csv": str(OUTPUT_CSV),
        "report_json": str(OUTPUT_JSON),
        "warning": (
            "Experimental candidate only. Historical/stale inputs are not "
            "live forecasts. Do not promote to production without independent "
            "temporal validation."
        ),
    }
    with OUTPUT_JSON.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, allow_nan=False)

    print("\n=== BULK INFERENCE RESULT ===")
    print("Rows scanned:", f"{rows_scanned:,}")
    print("Locations predicted:", len(result))
    print("Latest source timestamp:", latest_ts)
    print("Source data stale:", report["source_data_stale"])
    print("Selection counts:", report["selection_counts"])
    print("Prediction CSV:", OUTPUT_CSV)
    print("Report JSON:", OUTPUT_JSON)
    print("Evaluation:", json.dumps(evaluation, indent=2))
    print("Elapsed seconds:", report["elapsed_seconds"])
    print("Production models/services were not modified.")


if __name__ == "__main__":
    main()
