import unittest

import pandas as pd

from ml.features import weather_features_500 as features


def source_frame(hours=3, start="2026-01-15 00:00:00"):
    timestamps = pd.date_range(start, periods=hours, freq="h")
    rows = []
    for location in range(features.EXPECTED_LOCATIONS):
        for timestamp in timestamps:
            rows.append({
                "location_code": f"GRID_{location:04d}",
                "timestamp": timestamp,
                "temperature_2m": 20.0,
                "precipitation_mm": 0.0,
                "relative_humidity_2m": 70.0,
                "surface_pressure_hpa": 1000.0,
                "wind_speed_10m": 5.0,
                "cloud_cover": 20.0,
                "latitude": 10.0,
                "longitude": 105.0,
            })
    return pd.DataFrame(rows)


class WeatherSourceValidationTests(unittest.TestCase):
    def test_accepts_complete_hourly_source_with_derived_time_range(self):
        data = source_frame(hours=4, start="2026-10-20 00:00:00")

        validated = features.validate_source_data(data)

        self.assertEqual(len(validated), 500 * 4)
        self.assertEqual(validated["timestamp"].min(), pd.Timestamp("2026-10-20 00:00:00"))
        self.assertEqual(validated["timestamp"].max(), pd.Timestamp("2026-10-20 03:00:00"))

    def test_rejects_location_with_missing_hour(self):
        data = source_frame(hours=3).drop(index=1)

        with self.assertRaisesRegex(ValueError, "common hourly time range|equal hourly coverage|non-hourly|incomplete hourly"):
            features.validate_source_data(data)

    def test_rejects_duplicate_location_timestamp(self):
        data = source_frame(hours=2)
        data = pd.concat([data, data.iloc[[0]]], ignore_index=True)

        with self.assertRaisesRegex(ValueError, "duplicate location/timestamp"):
            features.validate_source_data(data)


if __name__ == "__main__":
    unittest.main()
