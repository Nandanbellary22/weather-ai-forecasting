
import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException

from backend.routes import weather


class FakeCursor:
    def __init__(self, row):
        self.row = row
        self.query = None
        self.parameters = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, query, parameters):
        self.query = query
        self.parameters = parameters

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, row):
        self.cursor_instance = FakeCursor(row)
        self.closed = False

    def cursor(self):
        return self.cursor_instance

    def close(self):
        self.closed = True


def make_open_meteo_payload():
    times = [
        "2026-10-25T13:00",
        "2026-10-25T14:00",
    ]

    return {
        "latitude": 12.96,
        "longitude": 77.60,
        "timezone": "Asia/Ho_Chi_Minh",
        "hourly": {
            "time": times,
            "temperature_2m": [29.0, 30.0],
            "relative_humidity_2m": [70, 65],
            "dew_point_2m": [23.0, 22.0],
            "precipitation": [0.0, 0.1],
            "rain": [0.0, 0.1],
            "pressure_msl": [1008.0, 1007.0],
            "surface_pressure": [950.0, 949.0],
            "cloud_cover": [40, 35],
            "wind_speed_10m": [5.0, 6.0],
            "wind_direction_10m": [180, 190],
            "wind_gusts_10m": [9.0, 10.0],
        },
    }


class RecentWeatherRouteTests(unittest.TestCase):
    def setUp(self):
        self.connection = FakeConnection((12.96, 77.60))

    def test_returns_recent_weather_and_marks_source_as_model_output(self):
        response = Mock()
        response.json.return_value = make_open_meteo_payload()
        response.raise_for_status.return_value = None

        with (
            patch.object(
                weather,
                "get_db_connection",
                return_value=self.connection,
            ),
            patch.object(weather.requests, "get", return_value=response) as get,
        ):
            result = weather.get_recent_weather("bmt")

        self.assertEqual(result["location_code"], "BMT")
        self.assertEqual(result["source"], "Open-Meteo")
        self.assertEqual(result["data_type"], "weather_model_output")
        self.assertFalse(result["is_verified_station_observation"])
        self.assertFalse(result["database_modified"])
        self.assertFalse(result["model_files_modified"])
        self.assertEqual(result["returned_hour_count"], 2)
        self.assertEqual(result["hourly"][1]["temperature_c"], 30.0)
        self.assertEqual(result["hourly"][1]["precipitation_mm"], 0.1)

        self.assertTrue(self.connection.closed)
        self.assertEqual(
            self.connection.cursor_instance.parameters,
            ("BMT",),
        )

        params = get.call_args.kwargs["params"]
        self.assertEqual(params["past_hours"], 24)
        self.assertEqual(params["forecast_hours"], 24)
        self.assertEqual(params["timezone"], "Asia/Ho_Chi_Minh")

    def test_returns_404_when_location_is_unknown(self):
        connection = FakeConnection(None)

        with (
            patch.object(
                weather,
                "get_db_connection",
                return_value=connection,
            ),
            patch.object(weather.requests, "get") as get,
        ):
            with self.assertRaises(HTTPException) as context:
                weather.get_recent_weather("UNKNOWN")

        self.assertEqual(context.exception.status_code, 404)
        get.assert_not_called()
        self.assertTrue(connection.closed)

    def test_returns_502_when_open_meteo_is_unavailable(self):
        with (
            patch.object(
                weather,
                "get_db_connection",
                return_value=self.connection,
            ),
            patch.object(
                weather.requests,
                "get",
                side_effect=weather.requests.Timeout("timeout"),
            ),
        ):
            with self.assertRaises(HTTPException) as context:
                weather.get_recent_weather("BMT")

        self.assertEqual(context.exception.status_code, 502)


if __name__ == "__main__":
    unittest.main()
