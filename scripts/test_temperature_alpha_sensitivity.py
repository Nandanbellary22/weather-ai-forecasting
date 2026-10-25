
import hashlib
import json
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

OUTPUT_JSON = CANDIDATE / "alpha_sensitivity_oct17_oct21_report.json"
OUTPUT_OVERALL = CANDIDATE / "alpha_sensitivity_oct17_oct21_overall.csv"
OUTPUT_LOCATION = CANDIDATE / "alpha_sensitivity_oct17_oct21_by_location.csv"

START = pd.Timestamp("2026-10-17 00:00:00")
END = pd.Timestamp("2026-10-22 00:00:00")
ALPHAS = [0.0, 0.2, 0.3, 0.4, 0.49]
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
        "samples": 0,
        "absolute_error_sum": 0.0,
        "squared_error_sum": 0.0,
        "signed_error_sum": 0.0,
        "wins": 0,
    }


def add_stats(stats, errors, baseline_errors):
    stats["samples"] += len(errors)
    stats["absolute_error_sum"] += float(np.abs(errors).sum())
    stats["squared_error_sum"] += float(np.square(errors).sum())
    stats["signed_error_sum"] += float(errors.sum())
    stats["wins"] += int(
        (np.abs(errors) < np.abs(baseline_errors)).sum()
    )


def finish_stats(stats):
    n = stats["samples"]
    if n == 0:
        return {"samples": 0}

    baseline_mae = None
    mae = stats["absolute_error_sum"] / n

    return {
        "samples": n,
        "mae": mae,
        "rmse": float(np.sqrt(stats["squared_error_sum"] / n)),
        "bias": stats["signed_error_sum"] / n,
        "wins_vs_baseline_percent": stats["wins"] / n * 100,
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
        "location_code",
        "timestamp",
        "temperature_2m",
        "temperature_target",
        *features,
    ]
    header = pd.read_csv(CSV_PATH, nrows=0).columns.tolist()
    missing = sorted(set(required) - set(header))
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    overall = {alpha: new_stats() for alpha in ALPHAS}
    by_location = {
        alpha: {} for alpha in ALPHAS
    }
    locations_seen = set()
    rows_evaluated = 0

    print("Checkpoint SHA-256:", checkpoint_hash)
    print("Evaluation window:", START, "through", END, "(end exclusive)")
    print("Alphas:", ALPHAS)

    for chunk in pd.read_csv(
        CSV_PATH, usecols=required, chunksize=CHUNK_SIZE
    ):
        timestamps = pd.to_datetime(chunk["timestamp"], errors="coerce")
        in_window = (timestamps >= START) & (timestamps < END)
        if not in_window.any():
            continue

        chunk = chunk.loc[in_window].copy()
        timestamps = timestamps.loc[in_window]
        locations = chunk["location_code"].astype(str).to_numpy()

        current = pd.to_numeric(
            chunk["temperature_2m"], errors="coerce"
        ).to_numpy(dtype=np.float64)
        target = pd.to_numeric(
            chunk["temperature_target"], errors="coerce"
        ).to_numpy(dtype=np.float64)
        X = chunk[features].apply(
            pd.to_numeric, errors="coerce"
        ).to_numpy(dtype=np.float32)

        valid = (
            timestamps.notna().to_numpy()
            & pd.Series(locations).isin(selection).to_numpy()
            & np.isfinite(current)
            & np.isfinite(target)
            & np.isfinite(X).all(axis=1)
        )
        if not valid.any():
            continue

        locations = locations[valid]
        current = current[valid]
        target = target[valid]
        X = X[valid]

        normalized = np.clip((X - means) / scales, -10.0, 10.0)
        with torch.no_grad():
            raw = model(
                torch.from_numpy(normalized.astype(np.float32))
            ).squeeze(1).numpy().astype(np.float64)

        baseline_errors = current - target
        use_model = np.array(
            [selection[loc] == "global" for loc in locations]
        )

        for alpha in ALPHAS:
            prediction = current.copy()
            prediction[use_model] = current[use_model] + alpha * (
                raw[use_model] - current[use_model]
            )
            errors = prediction - target

            add_stats(overall[alpha], errors, baseline_errors)

            for location in np.unique(locations):
                mask = locations == location
                stats = by_location[alpha].setdefault(
                    location, new_stats()
                )
                add_stats(stats, errors[mask], baseline_errors[mask])

        rows_evaluated += len(target)
        locations_seen.update(locations.tolist())

    if rows_evaluated == 0:
        raise RuntimeError("No valid rows found in the evaluation window.")

    overall_records = []
    for alpha in ALPHAS:
        metrics = finish_stats(overall[alpha])
        overall_records.append({"alpha": alpha, **metrics})

    baseline_mae = overall_records[0]["mae"]
    for row in overall_records:
        row["mae_improvement_vs_baseline_percent"] = (
            (baseline_mae - row["mae"]) / baseline_mae * 100
            if baseline_mae else None
        )

    location_records = []
    for alpha in ALPHAS:
        for location, stats in sorted(by_location[alpha].items()):
            location_records.append({
                "alpha": alpha,
                "location_code": location,
                **finish_stats(stats),
            })

    overall_df = pd.DataFrame(overall_records)
    location_df = pd.DataFrame(location_records)

    CANDIDATE.mkdir(parents=True, exist_ok=True)
    overall_df.to_csv(OUTPUT_OVERALL, index=False)
    location_df.to_csv(OUTPUT_LOCATION, index=False)

    report = {
        "evaluation": "development_alpha_sensitivity_diagnostic",
        "start_inclusive": str(START),
        "end_exclusive": str(END),
        "checkpoint_sha256": checkpoint_hash,
        "feature_file": str(CSV_PATH.relative_to(ROOT)),
        "alphas_tested": ALPHAS,
        "rows_evaluated": rows_evaluated,
        "locations_evaluated": len(locations_seen),
        "overall_metrics": overall_records,
        "caveats": [
            "Development diagnostic only; this period is not an untouched test set.",
            "Checkpoint training cutoff is undocumented, so independent validation is unproven.",
            "No model retraining or production changes were performed.",
            "Alpha 0.0 is the current-temperature baseline.",
        ],
        "elapsed_seconds": round(time.time() - started, 2),
    }

    OUTPUT_JSON.write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )

    print("\nOVERALL ALPHA COMPARISON")
    print(
        overall_df.to_string(
            index=False,
            float_format=lambda value: f"{value:.4f}",
        )
    )

    print("\nTOP ALPHA BY OVERALL MAE ON THIS DIAGNOSTIC WINDOW:")
    best = overall_df.loc[overall_df["mae"].idxmin()]
    print(
        f"alpha={best['alpha']:.2f}, "
        f"MAE={best['mae']:.4f}, "
        f"RMSE={best['rmse']:.4f}, "
        f"bias={best['bias']:+.4f} °C"
    )

    print("\nSaved:")
    print(OUTPUT_JSON)
    print(OUTPUT_OVERALL)
    print(OUTPUT_LOCATION)


if __name__ == "__main__":
    main()
