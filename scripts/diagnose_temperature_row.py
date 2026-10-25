
from pathlib import Path
import hashlib

import numpy as np
import pandas as pd
import torch
from torch import nn

ROOT = Path(__file__).resolve().parent.parent
CANDIDATE = ROOT / "models" / "weather" / "candidate_temperature_hybrid"
CHECKPOINT_PATH = CANDIDATE / "temperature_mlp_candidate.pt"
CSV_PATH = ROOT / "data" / "processed" / "weather_features" / "temperature_features_500.csv"

LOCATION = "GRID_0116"
TIMESTAMP = pd.Timestamp("2026-09-12 22:00:00")
COLAB_RAW_PREDICTION = 19.785026550


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
    print("=== FILES ===")
    print("Checkpoint:", CHECKPOINT_PATH)
    print("Checkpoint exists:", CHECKPOINT_PATH.is_file())
    print("Feature CSV:", CSV_PATH)
    print("Feature CSV exists:", CSV_PATH.is_file())

    if not CHECKPOINT_PATH.is_file() or not CSV_PATH.is_file():
        raise FileNotFoundError("Required checkpoint or feature CSV is missing.")

    digest = hashlib.sha256(CHECKPOINT_PATH.read_bytes()).hexdigest()
    print("Checkpoint SHA-256:", digest)

    checkpoint = torch.load(
        CHECKPOINT_PATH, map_location="cpu", weights_only=False
    )
    features = list(checkpoint["input_features"])
    means = np.asarray(checkpoint["normalization_means"], dtype=np.float32)
    scales = np.asarray(checkpoint["normalization_scales"], dtype=np.float32)

    print("\n=== CHECKPOINT METADATA ===")
    print("Architecture metadata:", checkpoint.get("architecture"))
    print("Target:", checkpoint.get("target"))
    print("Feature count:", len(features))
    print("Feature order:", features)
    print("Means dtype/shape:", means.dtype, means.shape)
    print("Scales dtype/shape:", scales.dtype, scales.shape)

    model = WeatherMLP(len(features))
    model.load_state_dict(checkpoint["model_state_dict"], strict=True)
    model.eval()

    print("Model class:", type(model).__name__)
    print("Layer dimensions: Linear(38,128) -> ReLU -> Linear(128,64) -> ReLU -> Linear(64,1)")
    print("Model device:", next(model.parameters()).device)
    print("Parameter dtype:", next(model.parameters()).dtype)
    print("State dict keys:", list(model.state_dict().keys()))

    # Read only the requested location's rows; do not rewrite the CSV.
    df = pd.read_csv(CSV_PATH, low_memory=False)
    df["timestamp_parsed"] = pd.to_datetime(
        df["timestamp"], errors="coerce"
    )

    match = df[
        (df["location_code"].astype(str) == LOCATION)
        & (df["timestamp_parsed"] == TIMESTAMP)
    ]

    if len(match) != 1:
        raise ValueError(
            f"Expected exactly one matching row; found {len(match)}. "
            "Check the source timestamp and timezone semantics."
        )

    row = match.iloc[0]
    X_raw = pd.to_numeric(row[features], errors="coerce").to_numpy(
        dtype=np.float32
    )

    if X_raw.shape != (38,):
        raise ValueError(f"Expected 38 features; got {X_raw.shape}")

    # Match the stated Colab preprocessing order and NumPy dtype.
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        z_before_clip = (X_raw - means) / scales
        z_after_clip = np.clip(z_before_clip, -10.0, 10.0)
        z_final = np.nan_to_num(
            z_after_clip,
            nan=0.0,
            posinf=10.0,
            neginf=-10.0,
        ).astype(np.float32)

    tensor = torch.from_numpy(z_final)

    with torch.inference_mode():
        raw_output = model(tensor.unsqueeze(0)).item()

    table = pd.DataFrame({
        "index": np.arange(len(features)),
        "feature": features,
        "raw_value": X_raw,
        "mean": means,
        "scale": scales,
        "normalized_before_clip": z_before_clip,
        "normalized_after_clip": z_after_clip,
        "final_tensor_value": z_final,
    })

    pd.set_option("display.max_rows", 100)
    pd.set_option("display.max_columns", 20)
    pd.set_option("display.width", 220)
    pd.set_option("display.float_format", lambda x: f"{x:.9g}")

    print("\n=== EXACT SOURCE ROW ===")
    print("Location:", row["location_code"])
    print("Original timestamp:", repr(row["timestamp"]))
    print("Parsed timestamp:", repr(row["timestamp_parsed"]))
    print("Timestamp timezone:", row["timestamp_parsed"].tz)
    print("Current temperature:", row.get("temperature_2m"))
    print("Source CSV:", CSV_PATH)

    print("\n=== FEATURE-BY-FEATURE DIAGNOSTIC ===")
    print(table.to_string(index=False))

    print("\n=== EXACT 38-VALUE RAW VECTOR ===")
    print(repr(X_raw.tolist()))

    print("\n=== EXACT 38-VALUE NORMALIZED TENSOR ===")
    print(repr(tensor.tolist()))
    print("Tensor shape:", tuple(tensor.shape))
    print("Tensor dtype:", tensor.dtype)
    print("Tensor device:", tensor.device)
    print("Tensor finite:", bool(torch.isfinite(tensor).all()))

    print("\n=== PREDICTION COMPARISON ===")
    print(f"Local raw output: {raw_output:.9f}")
    print(f"Colab raw output: {COLAB_RAW_PREDICTION:.9f}")
    print(f"Absolute difference: {abs(raw_output - COLAB_RAW_PREDICTION):.9f}")

    print("\n=== CLIPPING / NON-FINITE AUDIT ===")
    print("Raw non-finite feature indices:",
          np.flatnonzero(~np.isfinite(X_raw)).tolist())
    print("Pre-clip non-finite normalized indices:",
          np.flatnonzero(~np.isfinite(z_before_clip)).tolist())
    print("Clipped feature indices:",
          np.flatnonzero(z_before_clip != z_after_clip).tolist())
    print("Features clipped:",
          table.loc[z_before_clip != z_after_clip, "feature"].tolist())
    print("Normalized values before clipping:")
    print(repr(z_before_clip.tolist()))

    print("\n=== ROLLING RAINFALL VALUES FROM SOURCE CSV ===")
    for name in [
        "precipitation_mm",
        "rainfall_roll_sum_6",
        "rainfall_roll_sum_12",
        "rainfall_roll_sum_24",
        "rainfall_roll_mean_6",
        "rainfall_roll_mean_12",
        "rainfall_roll_mean_24",
    ]:
        print(f"{name}: {row[name]!r}")

    print("\nThis script reads existing files only. It does not change production code or configuration.")


if __name__ == "__main__":
    main()
