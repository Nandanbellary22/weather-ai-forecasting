import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from backend.routes import weather


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.query = None
        self.parameters = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, query, parameters):
        self.query = query
        self.parameters = parameters

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, rows):
        self.cursor_instance = FakeCursor(rows)
        self.closed = False

    def cursor(self):
        return self.cursor_instance

    def close(self):
        self.closed = True


class WeatherLocationsRouteTests(unittest.TestCase):
    def setUp(self):
        self.timestamp = datetime(2026, 7, 13, 23, tzinfo=timezone.utc)
        self.row = (
            "GRID_0001",
            21.0,
            105.0,
            self.timestamp,
            29.5,
            0.2,
            93.0,
            19.4,
            1008.4,
            862.7,
            3.8,
            185.0,
            11.2,
            70.0,
        )
        self.connection = FakeConnection([self.row])

    def call_endpoint(self):
        with patch.object(weather, "get_db_connection", return_value=self.connection):
            return weather.get_weather_locations(limit=25)

    def test_returns_existing_and_imported_weather_fields_from_latest_row(self):
        result = self.call_endpoint()

        self.assertEqual(len(result), 1)
        self.assertEqual(
            result[0],
            {
                "location_code": "GRID_0001",
                "latitude": 21.0,
                "longitude": 105.0,
                "timestamp": self.timestamp,
                "temperature_c": 29.5,
                "rainfall_mm": 0.2,
                "relative_humidity_2m": 93.0,
                "dew_point_2m": 19.4,
                "pressure_msl": 1008.4,
                "surface_pressure_hpa": 862.7,
                "wind_speed_10m": 3.8,
                "wind_direction_10m": 185.0,
                "wind_gusts_10m": 11.2,
                "cloud_cover": 70.0,
            },
        )
        self.assertEqual(self.connection.cursor_instance.parameters, (25,))
        query = self.connection.cursor_instance.query
        self.assertIn("DISTINCT ON (location_code)", query)
        self.assertIn("ORDER BY location_code, timestamp DESC", query)
        self.assertTrue(self.connection.closed)

    def test_database_nulls_are_preserved_as_none_for_json_null_serialization(self):
        nullable_fields = [None] * 8
        row_with_missing_weather = self.row[:6] + tuple(nullable_fields)
        connection = FakeConnection([row_with_missing_weather])

        with patch.object(weather, "get_db_connection", return_value=connection):
            result = weather.get_weather_locations(limit=1)

        for field in (
            "relative_humidity_2m",
            "dew_point_2m",
            "pressure_msl",
            "surface_pressure_hpa",
            "wind_speed_10m",
            "wind_direction_10m",
            "wind_gusts_10m",
            "cloud_cover",
        ):
            with self.subTest(field=field):
                self.assertIsNone(result[0][field])


if __name__ == "__main__":
    unittest.main()
