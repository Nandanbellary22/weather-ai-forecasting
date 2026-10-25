
import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_DIR = ROOT / "models" / "weather" / "candidate_temperature_hybrid"

PREDICTIONS_FILE = (
    CANDIDATE_DIR / "independent_test_predictions_sep05_oct16.csv"
)
PER_LOCATION_FILE = (
    CANDIDATE_DIR / "independent_test_per_location_sep05_oct16.csv"
)

WEEKLY_OUTPUT = CANDIDATE_DIR / "weekly_robustness_metrics.csv"
LOCATION_WEEKLY_OUTPUT = CANDIDATE_DIR / "location_weekly_robustness.csv"
REGRESSION_OUTPUT = CANDIDATE_DIR / "consistent_regressions.csv"
SUMMARY_OUTPUT = CANDIDATE_DIR / "weekly_robustness_report.json"

ACTUAL = "actual_next_temperature"

METHODS = {
    "Current temperature baseline": "current_temperature_baseline",
    "Raw MLP": "raw_mlp_prediction",
    "Global hybrid": "global_hybrid_prediction",
    "Location-selected hybrid": "selected_hybrid_prediction",
}


def calculate_metrics(actual, predicted):
    error = predicted - actual
    return {
        "rows": int(len(error)),
        "MAE_C": float(np.mean(np.abs(error))),
        "RMSE_C": float(np.sqrt(np.mean(error**2))),
        "bias_C": float(np.mean(error)),
    }


def main():
    if not PREDICTIONS_FILE.exists():
        raise FileNotFoundError(f"Missing file: {PREDICTIONS_FILE}")

    if not PER_LOCATION_FILE.exists():
        raise FileNotFoundError(f"Missing file: {PER_LOCATION_FILE}")

    print("Loading saved test predictions...")
    df = pd.read_csv(PREDICTIONS_FILE)

    required = ["location_code", "timestamp", ACTUAL, *METHODS.values()]
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError(f"Missing required prediction columns: {missing}")

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")

    numeric_columns = [ACTUAL, *METHODS.values()]
    for column in numeric_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    original_rows = len(df)
    df = df.dropna(subset=["location_code", "timestamp", *numeric_columns])
    removed_rows = original_rows - len(df)

    if df.empty:
        raise ValueError("No valid prediction rows remain after data validation.")

    # Monday-starting calendar weeks. The first and last weeks may be partial.
    df["week_start"] = (
        df["timestamp"].dt.to_period("W-SUN").dt.start_time
    )

    print(f"Valid prediction rows: {len(df):,}")
    print(f"Rows removed due to missing/invalid data: {removed_rows:,}")
    print(f"Locations: {df['location_code'].nunique():,}")
    print(
        f"Test dates: {df['timestamp'].min()} to "
        f"{df['timestamp'].max()}"
    )
    print("\nCalculating weekly metrics...")

    weekly_records = []

    for week_start, group in df.groupby("week_start", sort=True):
        for method_name, prediction_column in METHODS.items():
            metrics = calculate_metrics(
                group[ACTUAL].to_numpy(dtype=float),
                group[prediction_column].to_numpy(dtype=float),
            )

            weekly_records.append({
                "week_start": week_start.strftime("%Y-%m-%d"),
                "week_end_exclusive": (
                    week_start + pd.Timedelta(days=7)
                ).strftime("%Y-%m-%d"),
                "method": method_name,
                **metrics,
            })

    weekly = pd.DataFrame(weekly_records)
    weekly.to_csv(WEEKLY_OUTPUT, index=False)

    # Per-location, per-week comparison between the selected hybrid and baseline.
    print("Calculating per-location weekly regressions...")

    location_week_records = []

    for (location, week_start), group in df.groupby(
        ["location_code", "week_start"], sort=True
    ):
        actual = group[ACTUAL].to_numpy(dtype=float)
        baseline = group["current_temperature_baseline"].to_numpy(dtype=float)
        selected = group["selected_hybrid_prediction"].to_numpy(dtype=float)
        global_hybrid = group["global_hybrid_prediction"].to_numpy(dtype=float)

        baseline_mae = float(np.mean(np.abs(baseline - actual)))
        selected_mae = float(np.mean(np.abs(selected - actual)))
        global_mae = float(np.mean(np.abs(global_hybrid - actual)))

        delta = selected_mae - baseline_mae
        tolerance = 1e-9

        if delta > tolerance:
            outcome = "worse"
        elif delta < -tolerance:
            outcome = "better"
        else:
            outcome = "tied"

        location_week_records.append({
            "location_code": location,
            "week_start": week_start.strftime("%Y-%m-%d"),
            "rows": len(group),
            "baseline_MAE_C": baseline_mae,
            "global_hybrid_MAE_C": global_mae,
            "selected_hybrid_MAE_C": selected_mae,
            "selected_minus_baseline_MAE_C": delta,
            "outcome_vs_baseline": outcome,
        })

    location_weekly = pd.DataFrame(location_week_records)
    location_weekly.to_csv(LOCATION_WEEKLY_OUTPUT, index=False)

    # Aggregate location-level weekly outcomes.
    regression_records = []

    for location, group in location_weekly.groupby("location_code"):
        worse_weeks = int((group["outcome_vs_baseline"] == "worse").sum())
        better_weeks = int((group["outcome_vs_baseline"] == "better").sum())
        tied_weeks = int((group["outcome_vs_baseline"] == "tied").sum())

        regression_records.append({
            "location_code": location,
            "weeks_evaluated": len(group),
            "weeks_worse": worse_weeks,
            "weeks_better": better_weeks,
            "weeks_tied": tied_weeks,
            "worse_week_fraction": worse_weeks / len(group),
            "mean_weekly_baseline_MAE_C": group["baseline_MAE_C"].mean(),
            "mean_weekly_selected_MAE_C": group["selected_hybrid_MAE_C"].mean(),
            "mean_weekly_MAE_change_C": (
                group["selected_minus_baseline_MAE_C"].mean()
            ),
            "overall_test_MAE_change_C": None,
        })

    regressions = pd.DataFrame(regression_records)

    # Also attach full-test per-location metrics from the existing report.
    per_location = pd.read_csv(PER_LOCATION_FILE)
    expected_location_columns = [
        "location_code",
        "baseline_MAE_C",
        "selected_hybrid_MAE_C",
        "selected_minus_baseline_MAE_C",
        "selection",
    ]
    missing_location = [
        column for column in expected_location_columns
        if column not in per_location.columns
    ]
    if missing_location:
        raise ValueError(
            f"Missing per-location report columns: {missing_location}"
        )

    per_location = per_location.rename(columns={
        "baseline_MAE_C": "full_test_baseline_MAE_C",
        "selected_hybrid_MAE_C": "full_test_selected_MAE_C",
        "selected_minus_baseline_MAE_C": "overall_test_MAE_change_C",
    })

    regressions = regressions.drop(columns=["overall_test_MAE_change_C"])
    regressions = regressions.merge(
        per_location[
            [
                "location_code",
                "selection",
                "full_test_baseline_MAE_C",
                "full_test_selected_MAE_C",
                "overall_test_MAE_change_C",
            ]
        ],
        on="location_code",
        how="left",
    )

    regressions = regressions.sort_values(
        [
            "worse_week_fraction",
            "overall_test_MAE_change_C",
        ],
        ascending=[False, False],
    )

    regressions.to_csv(REGRESSION_OUTPUT, index=False)

    # Overall metrics calculated from the exact saved prediction rows.
    overall_metrics = {}
    actual = df[ACTUAL].to_numpy(dtype=float)

    for method_name, prediction_column in METHODS.items():
        overall_metrics[method_name] = calculate_metrics(
            actual,
            df[prediction_column].to_numpy(dtype=float),
        )

    total_locations = int(df["location_code"].nunique())
    consistently_worse = int(
        (
            (regressions["weeks_worse"] > regressions["weeks_better"])
            & (regressions["weeks_worse"] > regressions["weeks_tied"])
        ).sum()
    )
    worse_every_week = int(
        (
            (regressions["weeks_worse"] == regressions["weeks_evaluated"])
            & (regressions["weeks_evaluated"] > 0)
        ).sum()
    )

    report = {
        "analysis": "temperature_hybrid_weekly_robustness",
        "input_predictions": str(PREDICTIONS_FILE.relative_to(ROOT)),
        "valid_rows": int(len(df)),
        "removed_invalid_rows": int(removed_rows),
        "locations": total_locations,
        "week_definition": "Monday through Sunday; first/last weeks may be partial",
        "overall_metrics": overall_metrics,
        "location_regression_summary": {
            "locations_hybrid_worse_in_more_weeks_than_better_or_tied": (
                consistently_worse
            ),
            "locations_hybrid_worse_every_evaluated_week": worse_every_week,
        },
        "outputs": [
            str(WEEKLY_OUTPUT.relative_to(ROOT)),
            str(LOCATION_WEEKLY_OUTPUT.relative_to(ROOT)),
            str(REGRESSION_OUTPUT.relative_to(ROOT)),
        ],
        "safety": (
            "Read-only analysis of saved candidate predictions. "
            "No production models, services, or database were modified."
        ),
    }

    with SUMMARY_OUTPUT.open("w", encoding="utf-8") as file:
        json.dump(report, file, indent=2)

    print("\n=== WEEKLY METRICS ===")
    print(
        weekly.pivot(
            index="week_start",
            columns="method",
            values="MAE_C",
        ).round(4).to_string()
    )

    print("\n=== LOCATION REGRESSION SUMMARY ===")
    print(f"Locations evaluated: {total_locations}")
    print(
        "Hybrid worse in more weeks than better/tied:",
        consistently_worse,
    )
    print("Hybrid worse in every evaluated week:", worse_every_week)

    print("\n=== TOP 15 LOCATIONS TO INVESTIGATE ===")
    columns_to_show = [
        "location_code",
        "selection",
        "weeks_worse",
        "weeks_better",
        "weeks_tied",
        "worse_week_fraction",
        "overall_test_MAE_change_C",
    ]
    print(regressions[columns_to_show].head(15).round(4).to_string(index=False))

    print("\n=== OUTPUT FILES ===")
    print(WEEKLY_OUTPUT)
    print(LOCATION_WEEKLY_OUTPUT)
    print(REGRESSION_OUTPUT)
    print(SUMMARY_OUTPUT)
    print("\nCompleted. Production files were not modified.")


if __name__ == "__main__":
    main()
