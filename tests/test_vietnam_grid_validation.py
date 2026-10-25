import unittest

from shapely.geometry import GeometryCollection, Polygon, box

from data_pipeline.crawlers.weather.validate_vietnam_grid import validate_grid_rows


class VietnamGridValidationTests(unittest.TestCase):
    def setUp(self):
        self.boundary = box(100, 0, 110, 20)
        self.hashes = {
            "grid_sha256": "grid-hash",
            "boundary_sha256": "boundary-hash",
            "run_timestamp_utc": "2026-10-11T00:00:00Z",
        }

    def test_coordinate_axis_order_is_longitude_then_latitude(self):
        report = validate_grid_rows(
            [{"location_id": "P1", "latitude": "5", "longitude": "105"}],
            self.boundary,
            **self.hashes,
        )

        self.assertEqual(report["classification_counts"]["strictly_interior"], 1)
        self.assertEqual(report["points"][0]["classification"], "strictly_interior")

    def test_interior_boundary_and_exterior_are_separated(self):
        rows = [
            {"location_id": "inside", "latitude": 10, "longitude": 105},
            {"location_id": "edge", "latitude": 10, "longitude": 100},
            {"location_id": "outside", "latitude": 10, "longitude": 111},
        ]
        report = validate_grid_rows(rows, self.boundary, **self.hashes)

        self.assertEqual(
            report["classification_counts"],
            {
                "strictly_interior": 1,
                "boundary_touching": 1,
                "outside": 1,
                "invalid_coordinate": 0,
            },
        )
        self.assertFalse(report["validation_passed"])
        self.assertEqual(report["points"][1]["classification"], "boundary_touching")
        self.assertEqual(report["points"][2]["location_id"], "outside")

    def test_empty_and_invalid_geometries_are_rejected(self):
        invalid = Polygon([(0, 0), (1, 1), (1, 0), (0, 1), (0, 0)])
        for geometry in (GeometryCollection(), invalid):
            with self.subTest(geometry=geometry.geom_type):
                with self.assertRaises(ValueError):
                    validate_grid_rows([], geometry, **self.hashes)

    def test_non_finite_and_out_of_range_coordinates_are_reported(self):
        rows = [
            {"location_id": "nan", "latitude": "NaN", "longitude": 105},
            {"location_id": "inf", "latitude": 10, "longitude": "Infinity"},
            {"location_id": "lat-range", "latitude": 91, "longitude": 105},
            {"location_id": "lon-range", "latitude": 10, "longitude": 181},
            {"location_id": "missing", "latitude": "", "longitude": 105},
        ]
        report = validate_grid_rows(rows, self.boundary, **self.hashes)

        self.assertEqual(report["classification_counts"]["invalid_coordinate"], 5)
        self.assertEqual(report["classified_point_count"], len(rows))
        self.assertFalse(report["validation_passed"])

    def test_duplicate_ids_and_coordinates_are_reported_without_dropping_rows(self):
        rows = [
            {"location_id": "same-id", "latitude": 10, "longitude": 105},
            {"location_id": "same-id", "latitude": 11, "longitude": 106},
            {"location_id": "other-id", "latitude": 10, "longitude": 105},
        ]
        report = validate_grid_rows(rows, self.boundary, **self.hashes)

        self.assertEqual(report["grid_count"], 3)
        self.assertEqual(report["classified_point_count"], 3)
        self.assertEqual(report["duplicate_location_ids"][0]["location_id"], "same-id")
        self.assertEqual(report["duplicate_coordinates"][0]["rows"][0]["location_id"], "same-id")
        self.assertEqual(report["duplicate_coordinates"][0]["rows"][1]["location_id"], "other-id")
        self.assertFalse(report["validation_passed"])

    def test_report_is_stable_when_run_timestamp_is_fixed(self):
        rows = [
            {"location_id": "P1", "latitude": 5, "longitude": 105},
            {"location_id": "P2", "latitude": 10, "longitude": 106},
        ]
        first = validate_grid_rows(rows, self.boundary, **self.hashes)
        second = validate_grid_rows(rows, self.boundary, **self.hashes)

        self.assertEqual(first, second)
        self.assertEqual(first["run_timestamp_utc"], self.hashes["run_timestamp_utc"])
        self.assertEqual(first["grid_file_sha256"], "grid-hash")
        self.assertEqual(first["boundary_file_sha256"], "boundary-hash")
        self.assertEqual(first["classified_point_count"], 2)


if __name__ == "__main__":
    unittest.main()
