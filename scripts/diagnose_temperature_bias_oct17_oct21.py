
import json
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
LOCATION_REPORT = CANDIDATE / "backtest_oct17_oct21_by_location.csv"
OUTPUT_JSON = CANDIDATE / "temperature_bias_diagnostic_oct17_oct21.json"
OUTPUT_CSV = CANDIDATE / "temperature_bias_diagnostic_oct17_oct21.csv"

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


def main():
    for path in (CHECKPOINT_PATH, CONFIG_PATH, CSV_PATH, LOCATION_REPORT):
        if not path.is_file():
            raise FileNotFoundError(f"Required file missing: {path}")

    checkpoint = torch.load(
        CHECKPOINT_PATH, map_location="cpu", weights_only=False
    )
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    selection = config["location_selection"]
    alpha = float(config["calibration"]["alpha"])

    features = list(checkpoint["input_features"])
    means = np.asarray(checkpoint["normalization_means"], dtype=np.float32)
    scales = np.asarray(checkpoint["normalization_scales"], dtype=np.float32)

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
        raise ValueError(f"Missing feature columns: {missing}")

    # Keep only running sums and counts; no prediction history is retained.
    stats = {}
    evaluated_rows = 0

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
            pd.Series(locations).isin(selection).to_numpy()
            & timestamps.notna().to_numpy()
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

        hybrid = current.copy()
        use_model = np.array(
            [selection[loc] == "global" for loc in locations]
        )
        hybrid[use_model] = current[use_model] + alpha * (
            raw[use_model] - current[use_model]
        )

        hybrid_error = hybrid - target
        baseline_error = current - target

        for loc in np.unique(locations):
            mask = locations == loc
            entry = stats.setdefault(
                loc,
                {
                    "samples": 0,
                    "hybrid_error_sum": 0.0,
                    "baseline_error_sum": 0.0,
                    "hybrid_abs_sum": 0.0,
                    "baseline_abs_sum": 0.0,
                },
            )
            he = hybrid_error[mask]
            be = baseline_error[mask]
            entry["samples"] += len(he)
            entry["hybrid_error_sum"] += float(he.sum())
            entry["baseline_error_sum"] += float(be.sum())
            entry["hybrid_abs_sum"] += float(np.abs(he).sum())
            entry["baseline_abs_sum"] += float(np.abs(be).sum())

        evaluated_rows += len(target)

    if not evaluated_rows:
        raise RuntimeError("No valid rows found in the requested date window.")

    records = []
    for loc, item in sorted(stats.items()):
        n = item["samples"]
        records.append(
            {
                "location_code": loc,
                "samples": n,
                "hybrid_bias": item["hybrid_error_sum"] / n,
                "baseline_bias": item["baseline_error_sum"] / n,
                "hybrid_mae": item["hybrid_abs_sum"] / n,
                "baseline_mae": item["baseline_abs_sum"] / n,
                "hybrid_minus_baseline_bias": (
                    item["hybrid_error_sum"] - item["baseline_error_sum"]
                ) / n,
            }
        )

    result = pd.DataFrame(records)
    prior = pd.read_csv(LOCATION_REPORT)
    prior["mae_difference"] = prior["hybrid_mae"] - prior["baseline_mae"]
    regressed = set(
        prior.loc[prior["mae_difference"] > 0, "location_code"].astype(str)
    )
    result["recently_regressed"] = result["location_code"].isin(regressed)

    result.to_csv(OUTPUT_CSV, index=False)

    hybrid_bias = float(
        result["hybrid_bias"].mul(result["samples"]).sum()
        / result["samples"].sum()
    )
    baseline_bias = float(
        result["baseline_bias"].mul(result["samples"]).sum()
        / result["samples"].sum()
    )

    report = {
        "evaluation": "temperature_signed_error_bias_diagnostic",
        "start_inclusive": str(START),
        "end_exclusive": str(END),
        "samples": int(result["samples"].sum()),
        "locations": int(len(result)),
        "hybrid_bias": hybrid_bias,
        "baseline_bias": baseline_bias,
        "bias_definition": "prediction minus observed target; positive means overprediction",
        "recently_regressed_locations": int(result["recently_regressed"].sum()),
        "regressed_location_diagnostics": (
            result[result["recently_regressed"]]
            .sort_values("hybrid_minus_baseline_bias", ascending=False)
            .to_dict(orient="records")
        ),
        "caveat": (
            "Retrospective diagnostic. Checkpoint training cutoff is unknown; "
            "this does not establish independent validation or production readiness."
        ),
    }
    OUTPUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("OVERALL SIGNED-ERROR BIAS")
    print(f"Samples: {report['samples']:,}")
    print(f"Locations: {report['locations']}")
    print(f"Hybrid bias: {hybrid_bias:+.4f} °C")
    print(f"Baseline bias: {baseline_bias:+.4f} °C")
    print("\nRECENTLY REGRESSED LOCATIONS")
    print(
        result[result["recently_regressed"]]
        .sort_values("hybrid_minus_baseline_bias", ascending=False)
        .to_string(index=False, float_format=lambda x: f"{x:+.4f}")
    )
    print("\nSaved:")
    print(OUTPUT_JSON)
    print(OUTPUT_CSV)


if __name__ == "__main__":
    main()
