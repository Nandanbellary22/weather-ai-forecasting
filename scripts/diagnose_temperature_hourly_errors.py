
import hashlib
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

OUTPUT_CSV = CANDIDATE / "hourly_error_diagnostic_oct17_oct21.csv"

START = pd.Timestamp("2026-10-17 00:00:00")
END = pd.Timestamp("2026-10-22 00:00:00")
TARGET_LOCATIONS = {"GRID_0198", "GRID_0125", "GRID_0122"}
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
        "temperature_target", *features,
    ]
    header = pd.read_csv(CSV_PATH, nrows=0).columns.tolist()
    missing = sorted(set(required) - set(header))
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    output = []

    for chunk in pd.read_csv(
        CSV_PATH, usecols=required, chunksize=CHUNK_SIZE
    ):
        timestamps = pd.to_datetime(chunk["timestamp"], errors="coerce")
        locations = chunk["location_code"].astype(str)
        mask = (
            timestamps.ge(START)
            & timestamps.lt(END)
            & locations.isin(TARGET_LOCATIONS)
        )
        if not mask.any():
            continue

        part = chunk.loc[mask].copy()
        part["timestamp"] = timestamps.loc[mask]
        part["location_code"] = locations.loc[mask]

        current = pd.to_numeric(
            part["temperature_2m"], errors="coerce"
        ).to_numpy(dtype=np.float64)
        target = pd.to_numeric(
            part["temperature_target"], errors="coerce"
        ).to_numpy(dtype=np.float64)
        X = part[features].apply(
            pd.to_numeric, errors="coerce"
        ).to_numpy(dtype=np.float32)

        locs = part["location_code"].to_numpy()
        valid = (
            np.isfinite(current)
            & np.isfinite(target)
            & np.isfinite(X).all(axis=1)
            & pd.Series(locs).isin(selection).to_numpy()
        )
        if not valid.any():
            continue

        part = part.iloc[np.flatnonzero(valid)]
        current, target, X, locs = (
            current[valid], target[valid], X[valid], locs[valid]
        )

        normalized = np.clip((X - means) / scales, -10.0, 10.0)
        with torch.no_grad():
            raw = model(
                torch.from_numpy(normalized.astype(np.float32))
            ).squeeze(1).numpy().astype(np.float64)

        hybrid = current.copy()
        use_model = np.array([selection[loc] == "global" for loc in locs])
        hybrid[use_model] = current[use_model] + alpha * (
            raw[use_model] - current[use_model]
        )

        part["current_temperature"] = current
        part["target_temperature"] = target
        part["raw_mlp_prediction"] = raw
        part["hybrid_prediction"] = hybrid
        part["baseline_error"] = current - target
        part["hybrid_error"] = hybrid - target
        part["hybrid_absolute_error"] = np.abs(hybrid - target)
        part["baseline_absolute_error"] = np.abs(current - target)
        part["checkpoint_sha256"] = checkpoint_hash

        output.append(part[
            [
                "location_code", "timestamp", "current_temperature",
                "target_temperature", "raw_mlp_prediction",
                "hybrid_prediction", "baseline_error", "hybrid_error",
                "hybrid_absolute_error", "baseline_absolute_error",
                "checkpoint_sha256",
            ]
        ])

    if not output:
        raise RuntimeError("No valid rows found for the target locations.")

    result = pd.concat(output, ignore_index=True)
    result = result.sort_values(["location_code", "timestamp"])
    result.to_csv(OUTPUT_CSV, index=False)

    print("Checkpoint SHA-256:", checkpoint_hash)
    print("Rows:", len(result))
    print("\nLOCATION SUMMARY")
    summary = result.groupby("location_code").agg(
        samples=("hybrid_error", "size"),
        hybrid_bias=("hybrid_error", "mean"),
        baseline_bias=("baseline_error", "mean"),
        hybrid_mae=("hybrid_absolute_error", "mean"),
        baseline_mae=("baseline_absolute_error", "mean"),
    )
    print(summary.to_string(float_format=lambda x: f"{x:+.4f}"))

    print("\nHOURLY HYBRID ERRORS — LARGEST OVERPREDICTIONS")
    print(
        result.sort_values("hybrid_error", ascending=False)[
            ["location_code", "timestamp", "current_temperature",
             "target_temperature", "hybrid_prediction", "hybrid_error"]
        ].head(15).to_string(index=False, float_format=lambda x: f"{x:+.3f}")
    )

    print("\nSaved:", OUTPUT_CSV)


if __name__ == "__main__":
    main()
