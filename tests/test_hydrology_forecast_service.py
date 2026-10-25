import unittest
import warnings
from unittest.mock import patch

import numpy as np
import pandas as pd

from ml.services import forecast_service as service


def hourly_frame(rows=160, *, station_id="s1", start="2024-01-01 00:00"):
    return pd.DataFrame({
        "station_id": [station_id] * rows,
        "timestamp": pd.date_range(start, periods=rows, freq="h", tz=service.SOURCE_TIMEZONE),
        "value": np.arange(rows, dtype=float),
    })


class FeatureAndHistoryTests(unittest.TestCase):
    def test_rolling_features_only_use_values_before_current_timestamp(self):
        data = hourly_frame(30)
        features = service.create_features(data)
        row = 6
        self.assertEqual(features.loc[row, "rolling_mean_6"], np.mean([0, 1, 2, 3, 4, 5]))
        changed = data.copy()
        changed.loc[row, "value"] = 99999
        changed_features = service.create_features(changed)
        self.assertEqual(features.loc[row, "rolling_mean_6"], changed_features.loc[row, "rolling_mean_6"])
        self.assertEqual(features.loc[row, "lag_1"], 5.0)
        self.assertTrue(pd.isna(features.loc[5, "rolling_mean_6"]))

    def test_history_rejects_duplicate_unordered_irregular_and_insufficient_rows(self):
        data = hourly_frame(30)
        duplicate = data.copy()
        duplicate.loc[4, "timestamp"] = duplicate.loc[3, "timestamp"]
        unordered = data.copy()
        unordered.loc[[3, 4], "timestamp"] = unordered.loc[[4, 3], "timestamp"].to_numpy()
        irregular = data.copy()
        irregular.loc[4:, "timestamp"] += pd.Timedelta(hours=1)
        invalid = data.copy()
        invalid.loc[2, "timestamp"] = pd.NaT
        for frame, message in (
            (duplicate, "duplicate timestamps"),
            (unordered, "strictly ordered"),
            (irregular, "irregular"),
            (invalid, "invalid timestamps"),
            (data.iloc[:0], "at least 1 rows"),
        ):
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                service._validate_hourly_history(frame)

    def test_history_rejects_missing_values_and_insufficient_recursive_history(self):
        missing = hourly_frame(30)
        missing.loc[10, "value"] = np.nan
        with self.assertRaisesRegex(ValueError, "missing target"):
            service._validate_hourly_history(missing)
        # Feature generation preserves gaps and does not synthesize target values.
        features = service.create_features(missing)
        self.assertTrue(pd.isna(features.loc[10, "value"]))
        self.assertTrue(pd.isna(features.loc[11, "lag_1"]))
        with self.assertRaisesRegex(ValueError, "at least 24 rows"):
            service._recursive_predictions(None, hourly_frame(23), 24)

    def test_recursive_steps_consume_prior_predictions(self):
        class IncrementFromLag:
            def __init__(self):
                self.seen_lags = []

            def predict(self, features):
                lag = float(features.iloc[0]["lag_1"])
                self.seen_lags.append(lag)
                return np.array([lag + 1])

        history = hourly_frame(30)[["timestamp", "value"]]
        model = IncrementFromLag()
        points = service._recursive_predictions(model, history)
        self.assertEqual(model.seen_lags[:4], [29.0, 30.0, 31.0, 32.0])
        self.assertEqual([point["value"] for point in points[:4]], [30.0, 31.0, 32.0, 33.0])


class RecursiveEvaluationTests(unittest.TestCase):
    class MeanModel:
        fit_targets = []
        prediction_features = []

        def __init__(self, **kwargs):
            self.options = kwargs

        def fit(self, features, targets):
            self.__class__.fit_targets.append(np.asarray(targets, dtype=float).copy())
            self.mean = float(np.mean(targets))
            return self

        def predict(self, features):
            self.__class__.prediction_features.extend(
                features.to_dict(orient="records")
            )
            return np.full(len(features), self.mean, dtype=float)

    def test_chronological_recursive_windows_and_full_precision_baselines(self):
        data = hourly_frame(24 * 5 + 24)
        self.MeanModel.fit_targets = []
        with patch.object(service, "RandomForestRegressor", self.MeanModel):
            result = service.evaluate_recursive_forecasts(
                data, "s1", max_windows=3, minimum_train_rows=30
            )
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["windows"], 3)
        self.assertEqual(result["points"], 72)
        self.assertEqual(result["evaluated_observations"], 72)
        self.assertEqual(result["excluded_comparisons"], 0)
        self.assertEqual(result["evaluated_windows"], 3)
        self.assertEqual(len(self.MeanModel.fit_targets), 3)
        # The targets in each fit precede that window's monotonic test values.
        test_starts = [len(data) - 24 * window for window in (3, 2, 1)]
        for fitted_targets, test_start in zip(self.MeanModel.fit_targets, test_starts):
            self.assertLess(np.max(fitted_targets), data.iloc[test_start]["value"])
        self.assertGreater(result["random_forest"]["rmse"], 0.0)
        self.assertGreater(result["persistence"]["mae"], 0.0)
        self.assertIsInstance(result["random_forest"]["rmse"], float)
        expected_baseline_rmse = np.sqrt(np.mean(np.square(np.arange(1, 25))))
        self.assertAlmostEqual(result["persistence"]["mae"], 12.5)
        self.assertAlmostEqual(result["persistence"]["rmse"], expected_baseline_rmse)
        forest_errors = np.concatenate([
            np.arange(24.5, 48.0),
            np.arange(36.5, 60.0),
            np.arange(48.5, 72.0),
        ])
        self.assertAlmostEqual(result["random_forest"]["mae"], 48.0)
        expected_forest_rmse = np.sqrt(np.mean(np.square(forest_errors)))
        self.assertAlmostEqual(result["random_forest"]["rmse"], expected_forest_rmse)
        self.assertFalse(result["random_forest_better_on_both_metrics"])
        self.assertEqual(
            sum(window["evaluated_observations"] for window in result["window_results"]),
            result["evaluated_observations"],
        )
        self.assertLess(result["evaluation_start"], result["evaluation_end"])

    def test_future_actual_values_do_not_change_earlier_recursive_inputs(self):
        original = hourly_frame(24 * 6)
        altered = original.copy()
        altered.loc[altered.index >= 24 * 6 - 12, "value"] += 100000
        for frame in (original, altered):
            self.MeanModel.fit_targets = []
            self.MeanModel.prediction_features = []
            with patch.object(service, "RandomForestRegressor", self.MeanModel):
                result = service.evaluate_recursive_forecasts(
                    frame, "s1", max_windows=3, minimum_train_rows=30
                )
            self.assertEqual(result["status"], "success")
            if frame is original:
                original_features = list(self.MeanModel.prediction_features)
            else:
                self.assertEqual(self.MeanModel.prediction_features, original_features)

    def test_invalid_future_comparisons_are_excluded_and_counted(self):
        data = hourly_frame(24 * 6)
        data.loc[data.index[-12:], "value"] = np.nan
        with patch.object(service, "RandomForestRegressor", self.MeanModel):
            result = service.evaluate_recursive_forecasts(
                data, "s1", max_windows=3, minimum_train_rows=30
            )
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["excluded_comparisons"], 12)
        self.assertEqual(result["evaluated_observations"], result["points"])

    def test_evaluation_returns_insufficient_without_zero_metrics(self):
        result = service.evaluate_recursive_forecasts(
            hourly_frame(80), "s1", minimum_train_rows=100
        )
        self.assertEqual(result["status"], "insufficient")
        self.assertIn("reason", result)
        self.assertNotIn("rmse", result)
        self.assertNotIn("mae", result)

    def test_evaluation_reports_irregular_data_as_insufficient(self):
        data = hourly_frame(160)
        data.loc[50:, "timestamp"] += pd.Timedelta(hours=1)
        result = service.evaluate_recursive_forecasts(data, "s1")
        self.assertEqual(result["status"], "insufficient")
        self.assertIn("irregular", result["reason"])


class PredictionIntegrityTests(unittest.TestCase):
    def test_validates_count_hourly_order_uniqueness_and_finite_values(self):
        origin = pd.Timestamp("2024-01-01 00:00", tz=service.SOURCE_TIMEZONE)
        points = [
            {"timestamp": origin + pd.Timedelta(hours=i), "value": float(i)}
            for i in range(1, 25)
        ]
        service._validate_forecast_points(points, origin=origin)
        cases = [
            (points[:-1], "exactly 24"),
            ([*points[:2], points[0], *points[3:]], "unique and ordered"),
            ([*points[:1], {**points[1], "timestamp": points[1]["timestamp"] + pd.Timedelta(minutes=1)}, *points[2:]], "hourly"),
            ([*points[:1], {**points[1], "value": float("nan")}, *points[2:]], "non-finite"),
        ]
        for candidate, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                service._validate_forecast_points(candidate, origin=origin)

    def test_constant_predictions_are_a_warning_not_a_failure(self):
        origin = pd.Timestamp("2024-01-01 00:00", tz=service.SOURCE_TIMEZONE)
        points = [
            {"timestamp": origin + pd.Timedelta(hours=i), "value": 4.0}
            for i in range(1, 25)
        ]
        with self.assertWarnsRegex(RuntimeWarning, "constant"):
            service._validate_forecast_points(points, origin=origin)

    def test_live_response_shape_remains_compatible_without_evaluator_or_database(self):
        class StepModel:
            def predict(self, features):
                return np.array([float(features.iloc[0]["lag_1"] + 1)])

        history = hourly_frame(30)[["station_id", "timestamp", "value"]]
        metrics = {
            "mae": 1.25,
            "rmse": 2.5,
            "train_rows": 120,
            "test_rows": 30,
            "training_start": history["timestamp"].iloc[0],
            "training_end": history["timestamp"].iloc[-1],
        }
        with (
            patch.object(service, "train_model", return_value=(StepModel(), history, metrics)),
            patch.object(service, "save_forecast_run") as save,
        ):
            result = service.forecast_next_24_hours("s1")
        self.assertEqual(set(result), {"station_id", "model", "metrics", "last_observation", "forecast"})
        self.assertEqual(set(result["metrics"]), {"mae", "rmse", "train_rows", "test_rows"})
        self.assertEqual(len(result["forecast"]), 24)
        self.assertEqual(result["forecast"][0]["timestamp"], history["timestamp"].iloc[-1] + pd.Timedelta(hours=1))
        self.assertEqual(result["station_id"], "s1")
        save.assert_called_once()

    def test_forecast_rejects_history_associated_with_another_station(self):
        class StepModel:
            def predict(self, features):
                return np.array([1.0])

        history = hourly_frame(30, station_id="different")[
            ["station_id", "timestamp", "value"]
        ]
        metrics = {
            "mae": 1.0,
            "rmse": 1.0,
            "train_rows": 10,
            "test_rows": 2,
            "training_start": history["timestamp"].iloc[0],
            "training_end": history["timestamp"].iloc[-1],
        }
        with (
            patch.object(service, "train_model", return_value=(StepModel(), history, metrics)),
            patch.object(service, "save_forecast_run") as save,
            self.assertRaisesRegex(ValueError, "another station"),
        ):
            service.forecast_next_24_hours("s1")
        save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
