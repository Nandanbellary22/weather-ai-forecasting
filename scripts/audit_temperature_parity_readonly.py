
from pathlib import Path
import hashlib

import numpy as np
import pandas as pd
import torch
from torch import nn


ROOT = Path(__file__).resolve().parent.parent
CANDIDATE_DIR = ROOT / "models" / "weather" / "candidate_temperature_hybrid"
CHECKPOINT_PATH = CANDIDATE_DIR / "temperature_mlp_candidate.pt"
FEATURES_PATH = ROOT / "data" / "processed" / "weather_features" / "temperature_features_500.csv"
REFERENCE_PATH = CANDIDATE_DIR / "independent_test_predictions_sep05_oct16.csv"

TEST_START = pd.Timestamp("2026-09-05 00:00:00")
TEST_END = pd.Timestamp("2026-10-17 00:00:00")
TARGET_LOCATION = "GRID_0116"
TARGET_TIMESTAMP = pd.Timestamp("2026-09-12 22:00:00")
BATCH_SIZE = 8192


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


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def metrics(values):
    values = np.asarray(values, dtype=np.float64)
    return {
        "count": int(values.size),
        "mean_abs": float(np.mean(np.abs(values))) if values.size else None,
        "max_abs": float(np.max(np.abs(values))) if values.size else None,
        "count_gt_0.01": int(np.count_nonzero(np.abs(values) > 0.01)),
        "count_gt_1": int(np.count_nonzero(np.abs(values) > 1.0)),
    }


def main():
    for path in (CHECKPOINT_PATH, FEATURES_PATH, REFERENCE_PATH):
        if not path.is_file():
            raise FileNotFoundError(path)

    print("=== READ-ONLY TEMPERATURE PARITY AUDIT ===")
    print("Checkpoint:", CHECKPOINT_PATH)
    print("Checkpoint SHA-256:", sha256(CHECKPOINT_PATH))
    print("Feature source:", FEATURES_PATH)
    print("Reference predictions:", REFERENCE_PATH)

    for path in (CHECKPOINT_PATH, FEATURES_PATH, REFERENCE_PATH):
        stat = path.stat()
        print(
            f"FILE {path.name}: size={stat.st_size:,}; "
            f"modified={pd.Timestamp(stat.st_mtime, unit='s')}"
        )

    checkpoint = torch.load(
        CHECKPOINT_PATH, map_location="cpu", weights_only=False
    )
    features = list(checkpoint["input_features"])
    means = np.asarray(checkpoint["normalization_means"], dtype=np.float32)
    scales = np.asarray(checkpoint["normalization_scales"], dtype=np.float32)

    if len(features) != 38 or means.shape != (38,) or scales.shape != (38,):
        raise ValueError("Unexpected checkpoint feature or normalization dimensions.")
    if not np.isfinite(means).all() or not np.isfinite(scales).all():
        raise ValueError("Non-finite checkpoint normalization values.")
    if (scales <= 0).any():
        raise ValueError("Checkpoint contains non-positive normalization scales.")

    model = WeatherMLP(len(features))
    model.load_state_dict(checkpoint["model_state_dict"], strict=True)
    model.eval()

    print("\n=== MODEL ===")
    print("Architecture:", checkpoint.get("architecture"))
    print("Target:", checkpoint.get("target"))
    print("Model class:", type(model).__name__)
    print("Feature count:", len(features))
    print("Input dtype: float32")
    print("Parameter dtype:", next(model.parameters()).dtype)
    print("Device:", next(model.parameters()).device)
    print("Feature order:", features)

    # Read only the required feature columns.
    source_columns = ["location_code", "timestamp", *features]
    source = pd.read_csv(FEATURES_PATH, usecols=source_columns)
    source["location_code"] = source["location_code"].astype(str)
    source["timestamp"] = pd.to_datetime(source["timestamp"], errors="coerce")

    source = source[
        source["timestamp"].ge(TEST_START)
        & source["timestamp"].lt(TEST_END)
    ].copy()

    reference = pd.read_csv(REFERENCE_PATH)
    required_reference = {
        "location_code",
        "timestamp",
        "raw_mlp_prediction",
        "current_temperature_baseline",
        "global_hybrid_prediction",
        "selected_hybrid_prediction",
    }
    missing = required_reference - set(reference.columns)
    if missing:
        raise ValueError(f"Reference CSV missing columns: {sorted(missing)}")

    reference["location_code"] = reference["location_code"].astype(str)
    reference["timestamp"] = pd.to_datetime(
        reference["timestamp"], errors="coerce"
    )

    keys = ["location_code", "timestamp"]

    print("\n=== KEY AND ROW AUDIT ===")
    print("Filtered source rows:", len(source))
    print("Reference rows:", len(reference))
    print("Source locations:", source["location_code"].nunique())
    print("Reference locations:", reference["location_code"].nunique())
    print("Source duplicate keys:", int(source.duplicated(keys).sum()))
    print("Reference duplicate keys:", int(reference.duplicated(keys).sum()))
    print("Invalid source timestamps:", int(source["timestamp"].isna().sum()))
    print("Invalid reference timestamps:", int(reference["timestamp"].isna().sum()))

    if source.duplicated(keys).any():
        raise ValueError("Source has duplicate location/timestamp keys.")
    if reference.duplicated(keys).any():
        raise ValueError("Reference has duplicate location/timestamp keys.")
    if source["timestamp"].isna().any() or reference["timestamp"].isna().any():
        raise ValueError("Invalid timestamp found.")

    source_keys = source[keys]
    reference_keys = reference[keys]
    source_index = pd.MultiIndex.from_frame(source_keys)
    reference_index = pd.MultiIndex.from_frame(reference_keys)

    print("Source keys missing from reference:", len(source_index.difference(reference_index)))
    print("Reference keys missing from source:", len(reference_index.difference(source_index)))

    # Align reference predictions by explicit keys, never by positional row order.
    source = source.sort_values(keys).reset_index(drop=True)
    reference = reference.sort_values(keys).reset_index(drop=True)

    joined = source.merge(
        reference,
        on=keys,
        how="outer",
        suffixes=("_source", "_reference"),
        indicator=True,
        validate="one_to_one",
    )
    print("Outer-joined rows:", len(joined))
    print("Join counts:", joined["_merge"].value_counts().to_dict())

    matched = joined[joined["_merge"] == "both"].copy()
    if len(matched) == 0:
        raise ValueError("No matching location/timestamp keys.")

    # Rebuild features in the checkpoint's exact order.
    X = matched[features].apply(
        pd.to_numeric, errors="coerce"
    ).to_numpy(dtype=np.float32)

    print("\n=== INPUT AUDIT ===")
    print("Matched rows:", len(matched))
    print("Raw feature matrix shape:", X.shape)
    print("Raw feature dtype:", X.dtype)
    print("Non-finite raw feature values:", int((~np.isfinite(X)).sum()))

    if not np.isfinite(X).all():
        raise ValueError(
            "Non-finite features exist. Audit stopped rather than silently "
            "changing input handling."
        )

    # Match the documented Colab preprocessing: standardize, then clip.
    with np.errstate(over="ignore", divide="ignore", invalid="ignore"):
        normalized_before_clip = (X - means) / scales
        normalized = np.clip(normalized_before_clip, -10.0, 10.0)

    if not np.isfinite(normalized).all():
        raise ValueError("Normalized inputs contain non-finite values.")

    normalized = normalized.astype(np.float32, copy=False)
    clipped_count_by_feature = np.count_nonzero(
        normalized_before_clip != normalized, axis=0
    )
    print("Normalized dtype:", normalized.dtype)
    print(
        "Features clipped at least once:",
        [
            (features[i], int(count))
            for i, count in enumerate(clipped_count_by_feature)
            if count
        ],
    )

    # Batched inference; no files are written.
    prediction_parts = []
    with torch.inference_mode():
        for start in range(0, len(normalized), BATCH_SIZE):
            batch = torch.from_numpy(normalized[start:start + BATCH_SIZE])
            output = model(batch).squeeze(1).numpy()
            prediction_parts.append(output)

    local_prediction = np.concatenate(prediction_parts).astype(np.float64)

    matched["local_raw_mlp_prediction"] = local_prediction
    matched["raw_prediction_difference"] = (
        local_prediction
        - pd.to_numeric(
            matched["raw_mlp_prediction"], errors="raise"
        ).to_numpy(dtype=np.float64)
    )

    print("\n=== RAW MLP PREDICTION COMPARISON ===")
    print(metrics(matched["raw_prediction_difference"]))

    # Report raw MLP versus hybrid separately to avoid mixing output types.
    for column in (
        "current_temperature_baseline",
        "global_hybrid_prediction",
        "selected_hybrid_prediction",
    ):
        difference = (
            local_prediction
            - pd.to_numeric(matched[column], errors="raise").to_numpy(
                dtype=np.float64
            )
        )
        print(f"Local raw MLP minus {column}:", metrics(difference))

    print("\n=== WORST RAW MLP MISMATCHES ===")
    worst = matched.assign(
        abs_difference=matched["raw_prediction_difference"].abs()
    ).sort_values("abs_difference", ascending=False)

    print(
        worst[
            [
                "location_code",
                "timestamp",
                "local_raw_mlp_prediction",
                "raw_mlp_prediction",
                "raw_prediction_difference",
                "global_hybrid_prediction",
                "selected_hybrid_prediction",
            ]
        ].head(10).to_string(index=False)
    )

    print("\n=== TARGET ROW ===")
    target = matched[
        (matched["location_code"] == TARGET_LOCATION)
        & (matched["timestamp"] == TARGET_TIMESTAMP)
    ]
    if len(target) == 1:
        row = target.iloc[0]
        print("Local raw prediction:", repr(row["local_raw_mlp_prediction"]))
        print("Reference raw prediction:", repr(float(row["raw_mlp_prediction"])))
        print("Difference:", repr(float(row["raw_prediction_difference"])))
        print("Current temperature:", row["current_temperature_baseline"])
        print("Global hybrid:", row["global_hybrid_prediction"])
        print("Selected hybrid:", row["selected_hybrid_prediction"])
    else:
        print("Target row count in joined data:", len(target))

    print("\n=== FINAL STATUS ===")
    print("No checkpoint, configuration, reference artifact, or production file was written.")
    print("This audit does not establish the provenance of the original comparison.")
    print("Compare this output with the earlier reported mismatch counts.")


if __name__ == "__main__":
    main()
