import contextlib
import io
import json
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pandas as pd
import requests

from data_pipeline.crawlers import evn_reservoir_historical as collector
from data_pipeline.database import import_evn_reservoir_historical as importer


class LaiChauRecoveryIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.source = root / "source.csv"
        self.output = root / "recovery.csv"
        self.write_rows([])
        self.options = {collector.RECOVERY_RESERVOIR: "78"}

    def make_record(self, day, *, status="success", quality="exact_date", level=100.0):
        record = collector.make_missing_record(
            collector.RECOVERY_RESERVOIR, date.fromisoformat(day)
        )
        record.update(
            collection_status=status,
            quality_flag=quality,
            water_level_m=level if status == "success" else None,
            observation_timestamp=f"{day} 14:00:00" if quality == "exact_date" else "2023-12-31 14:00:00",
            observation_time_raw="31/12 14:00" if quality == "stale_previous_observation" else "01/01 14:00",
        )
        return record

    def write_rows(self, rows, path=None):
        pd.DataFrame(rows, columns=collector.OUTPUT_COLUMNS).to_csv(
            path or self.source, index=False, encoding="utf-8-sig"
        )

    def read_output(self):
        return pd.read_csv(self.output, dtype=str)

    def run_recovery(
        self, *, start="2024-01-01", end="2024-01-01", refresh=False,
        checkpoint=500, collect_side_effect=None,
    ):
        args = [
            "collector.py", "--collect", "--recovery-lai-chau", "--output", str(self.output),
            "--start-date", start, "--end-date", end, "--request-delay", "0",
            "--checkpoint-every", str(checkpoint),
        ]
        if refresh:
            args.append("--refresh-stale")
        if collect_side_effect is None:
            collect_side_effect = lambda session, name, reservoir_id, requested, **kwargs: (
                self.make_record(requested.isoformat()), None, None
            )
        stdout = io.StringIO()
        with (
            patch.object(collector, "OUTPUT_PATH", self.source),
            patch.object(collector, "fetch_reservoir_options", return_value=self.options) as fetch,
            patch.object(collector, "collect_one", side_effect=collect_side_effect) as collect,
            patch("sys.argv", args),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            collector.main()
        return fetch, collect, stdout.getvalue()

    def test_seeds_existing_lai_chau_rows_and_skips_success_by_default(self):
        original = self.make_record("2024-01-01", level=77.25)
        self.write_rows([original])
        fetch, collect, _ = self.run_recovery()
        self.assertEqual(fetch.call_count, 1)
        collect.assert_not_called()
        saved = self.read_output()
        expected = pd.read_csv(self.source, dtype=str)
        pd.testing.assert_frame_equal(saved[collector.OUTPUT_COLUMNS], expected, check_dtype=False)

    def test_refuses_malformed_output_without_changing_its_bytes(self):
        self.output.write_bytes(b"reservoir_name,wrong_column\nLai Ch\xc3\xa2u,keep-me\n")
        before = self.output.read_bytes()
        with (
            patch.object(collector, "OUTPUT_PATH", self.source),
            patch.object(collector, "fetch_reservoir_options") as fetch,
            patch("sys.argv", ["collector.py", "--collect", "--recovery-lai-chau", "--output", str(self.output), "--start-date", "2024-01-01", "--end-date", "2024-01-01"]),
            contextlib.redirect_stderr(io.StringIO()),
            self.assertRaisesRegex(ValueError, "Invalid recovery CSV schema"),
        ):
            collector.main()
        fetch.assert_not_called()
        self.assertEqual(self.output.read_bytes(), before)

    def test_refuses_unreadable_empty_and_unexpected_reservoir_outputs(self):
        for content, message in ((b"", "Cannot read recovery CSV"),):
            with self.subTest(content=content):
                self.output.write_bytes(content)
                before = self.output.read_bytes()
                with (
                    patch.object(collector, "OUTPUT_PATH", self.source),
                    patch("sys.argv", ["collector.py", "--collect", "--recovery-lai-chau", "--output", str(self.output), "--start-date", "2024-01-01", "--end-date", "2024-01-01"]),
                    contextlib.redirect_stderr(io.StringIO()),
                    self.assertRaisesRegex(ValueError, message),
                ):
                    collector.main()
                self.assertEqual(self.output.read_bytes(), before)
        unexpected = self.make_record("2024-01-01")
        unexpected["reservoir_name"] = "Tuyên Quang"
        self.write_rows([unexpected], self.output)
        before = self.output.read_bytes()
        with (
            patch.object(collector, "OUTPUT_PATH", self.source),
            patch("sys.argv", ["collector.py", "--collect", "--recovery-lai-chau", "--output", str(self.output), "--start-date", "2024-01-01", "--end-date", "2024-01-01"]),
            contextlib.redirect_stderr(io.StringIO()),
            self.assertRaisesRegex(ValueError, "records outside Lai Châu"),
        ):
            collector.main()
        self.assertEqual(self.output.read_bytes(), before)

    def test_refreshes_stale_only_when_explicit(self):
        self.write_rows([self.make_record("2024-01-01", quality="stale_previous_observation", level=55.0)])
        _, collect, _ = self.run_recovery()
        collect.assert_not_called()
        self.assertEqual(self.read_output().iloc[0]["quality_flag"], "stale_previous_observation")

        _, collect, _ = self.run_recovery(refresh=True)
        collect.assert_called_once()
        saved = self.read_output().iloc[0]
        self.assertEqual(saved["quality_flag"], "exact_date")
        self.assertEqual(float(saved["water_level_m"]), 100.0)

    def test_ambiguous_success_remains_seeded_and_is_not_upgraded_on_rerun(self):
        ambiguous = self.make_record("2024-01-01", quality="ambiguous_year", level=66.0)
        ambiguous["observation_timestamp"] = None
        ambiguous["observation_time_raw"] = "01/01 14:00"
        ambiguous["observation_year_inferred"] = None
        ambiguous["observation_year_method"] = None
        self.write_rows([ambiguous])
        _, collect, _ = self.run_recovery(refresh=True)
        collect.assert_not_called()
        saved = self.read_output().iloc[0]
        self.assertEqual(saved["quality_flag"], "ambiguous_year")
        self.assertEqual(saved["observation_time_raw"], "01/01 14:00")
        self.assertTrue(pd.isna(saved["observation_timestamp"]))
        self.assertEqual(float(saved["water_level_m"]), 66.0)

    def test_refresh_request_or_parse_failure_preserves_stale_and_rerun_retries(self):
        for failure_status in ("request_failed", "parse_failed"):
            with self.subTest(status=failure_status):
                self.output.unlink(missing_ok=True)
                self.write_rows([self.make_record("2024-01-01", quality="stale_previous_observation", level=55.0)])
                fail = lambda session, name, rid, requested, **kwargs: (
                    self.make_record(requested.isoformat(), status=failure_status, quality=None),
                    "temporary" if failure_status == "request_failed" else None,
                    "bad response" if failure_status == "parse_failed" else None,
                )
                _, failed_collect, _ = self.run_recovery(refresh=True, collect_side_effect=fail)
                failed_collect.assert_called_once()
                saved = self.read_output().iloc[0]
                self.assertEqual(saved["collection_status"], "success")
                self.assertEqual(saved["quality_flag"], "stale_previous_observation")
                self.assertEqual(float(saved["water_level_m"]), 55.0)

                _, retry_collect, _ = self.run_recovery(refresh=True)
                retry_collect.assert_called_once()
                saved = self.read_output().iloc[0]
                self.assertEqual(saved["quality_flag"], "exact_date")

    def test_checkpoint_then_rerun_keeps_good_rows_and_unique_keys(self):
        first = self.make_record("2024-01-01", level=70.0)
        self.write_rows([first])
        _, collect, _ = self.run_recovery(end="2024-01-03", checkpoint=1)
        self.assertEqual(collect.call_count, 2)
        initial = self.read_output()
        self.assertEqual(len(initial), 3)
        self.assertEqual(float(initial.loc[initial.requested_date == "2024-01-01", "water_level_m"].iloc[0]), 70.0)

        _, rerun_collect, _ = self.run_recovery(end="2024-01-03", checkpoint=1)
        rerun_collect.assert_not_called()
        rerun = self.read_output()
        self.assertEqual(len(rerun), 3)
        self.assertFalse(rerun.duplicated(["reservoir_name", "requested_date"]).any())
        self.assertEqual(float(rerun.loc[rerun.requested_date == "2024-01-01", "water_level_m"].iloc[0]), 70.0)

    def test_request_and_parse_failures_are_retryable_on_later_runs(self):
        for failure_status in ("request_failed", "parse_failed"):
            with self.subTest(status=failure_status):
                self.output.unlink(missing_ok=True)
                def fail(session, name, rid, requested, **kwargs):
                    return (
                        self.make_record(requested.isoformat(), status=failure_status, quality=None),
                        "temporary" if failure_status == "request_failed" else None,
                        "bad response" if failure_status == "parse_failed" else None,
                    )
                _, failed_collect, _ = self.run_recovery(collect_side_effect=fail)
                failed_collect.assert_called_once()
                self.assertEqual(self.read_output().iloc[0]["collection_status"], failure_status)
                _, retry_collect, _ = self.run_recovery()
                retry_collect.assert_called_once()
                self.assertEqual(self.read_output().iloc[0]["collection_status"], "success")

    def test_path_aliases_for_established_csvs_are_rejected(self):
        aliases = [
            collector.OUTPUT_PATH,
            collector.OUTPUT_PATH.parent / "." / collector.OUTPUT_PATH.name,
            collector.OUTPUT_PATH.parent / ".." / "processed" / collector.OUTPUT_PATH.name,
            *collector.MAIN_OUTPUT_PATHS,
        ]
        for alias in aliases:
            with self.subTest(path=alias), self.assertRaises(SystemExit):
                collector.parse_args(["--recovery-lai-chau", "--output", str(alias), "--start-date", "2024-01-01", "--end-date", "2024-01-01"])
        hardlink = self.output.parent / "main-hardlink.csv"
        try:
            os.link(self.source, hardlink)
        except OSError as exc:
            self.skipTest(f"hard links unavailable for this test environment: {exc}")
        with patch.object(collector, "MAIN_OUTPUT_PATHS", {self.source.resolve()}):
            with self.assertRaises(SystemExit):
                collector.parse_args(["--recovery-lai-chau", "--output", str(hardlink), "--start-date", "2024-01-01", "--end-date", "2024-01-01"])

    def test_recovery_requires_both_explicit_dates_before_network_or_output_write(self):
        for dates, message in (
            (("--end-date", "2024-01-01"), "requires an explicit --start-date"),
            (("--start-date", "2024-01-01"), "requires an explicit --end-date"),
        ):
            with self.subTest(dates=dates):
                args = ["collector.py", "--collect", "--recovery-lai-chau", "--output", str(self.output), *dates]
                with (
                    patch.object(collector, "OUTPUT_PATH", self.source),
                    patch.object(collector, "fetch_reservoir_options") as fetch,
                    patch("sys.argv", args),
                    contextlib.redirect_stderr(io.StringIO()),
                    self.assertRaises(SystemExit),
                ):
                    collector.main()
                fetch.assert_not_called()
                self.assertFalse(self.output.exists())

    def test_invalid_and_reversed_dates_fail_before_network_or_output_write(self):
        for date_args in (
            ("--start-date", "2024-02-30", "--end-date", "2024-03-02"),
            ("--start-date", "2024-02-28", "--end-date", "2024-02-30"),
            ("--start-date", "2024-03-02", "--end-date", "2024-03-01"),
        ):
            with self.subTest(date_args=date_args):
                args = ["collector.py", "--collect", "--recovery-lai-chau", "--output", str(self.output), *date_args]
                with (
                    patch.object(collector, "OUTPUT_PATH", self.source),
                    patch.object(collector, "fetch_reservoir_options") as fetch,
                    patch("sys.argv", args),
                    contextlib.redirect_stderr(io.StringIO()),
                    self.assertRaises(SystemExit),
                ):
                    collector.main()
                fetch.assert_not_called()
                self.assertFalse(self.output.exists())

    def test_explicit_non_leap_range_is_inclusive(self):
        _, collect, _ = self.run_recovery(start="2023-03-01", end="2023-03-03")
        self.assertEqual(
            [call.args[3].isoformat() for call in collect.call_args_list],
            ["2023-03-01", "2023-03-02", "2023-03-03"],
        )

    def test_explicit_leap_day_range_includes_both_endpoints(self):
        _, collect, _ = self.run_recovery(start="2024-02-28", end="2024-03-02")
        self.assertEqual(
            [call.args[3].isoformat() for call in collect.call_args_list],
            ["2024-02-28", "2024-02-29", "2024-03-01", "2024-03-02"],
        )

    def test_successes_are_skipped_failures_retry_and_outside_rows_are_untouched(self):
        rows = [
            self.make_record("2024-02-27", level=27.0),
            self.make_record("2024-02-28", level=28.0),
            self.make_record("2024-02-29", level=29.0),
            self.make_record("2024-03-01", status="request_failed", quality=None),
            self.make_record("2024-03-02", level=32.0),
            self.make_record("2024-03-03", level=33.0),
        ]
        self.write_rows(rows)
        _, collect, _ = self.run_recovery(start="2024-02-28", end="2024-03-02")
        self.assertEqual([call.args[3].isoformat() for call in collect.call_args_list], ["2024-03-01"])
        saved = self.read_output().set_index("requested_date")
        for day, level in (("2024-02-27", 27.0), ("2024-03-03", 33.0)):
            self.assertEqual(float(saved.loc[day, "water_level_m"]), level)
        self.assertEqual(saved.loc["2024-03-01", "collection_status"], "success")
        for day, level in (("2024-02-28", 28.0), ("2024-02-29", 29.0), ("2024-03-02", 32.0)):
            self.assertEqual(float(saved.loc[day, "water_level_m"]), level)

    def test_normal_collection_without_start_uses_configured_start(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "normal.csv"
            calls = []

            def collect(session, name, reservoir_id, requested, **kwargs):
                calls.append(requested.isoformat())
                return self.make_record(requested.isoformat()), None, None

            args = ["collector.py", "--collect", "--reservoirs", collector.RECOVERY_RESERVOIR,
                    "--end-date", "2024-01-02", "--request-delay", "0", "--output", str(output)]
            with (
                patch.object(collector, "OUTPUT_PATH", output),
                patch.object(collector, "fetch_reservoir_options", return_value=self.options),
                patch.object(collector, "collect_one", side_effect=collect),
                patch("sys.argv", args),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                collector.main()
            self.assertEqual(calls, ["2024-01-01", "2024-01-02"])


class ConservativeTimestampTests(unittest.TestCase):
    def setUp(self):
        self.requested = date(2024, 1, 1)
        self.session = Mock()
        self.response = Mock(text="<html>mock EVN response</html>")
        self.table = pd.DataFrame(
            columns=["Reservoir", "Observation time", "htl", "qve", "qxt", "qxm"]
        )

    def collect(self):
        with (
            patch.object(collector, "request_with_retries", return_value=(self.response, None)),
            patch.object(collector.pd, "read_html", return_value=[self.table]),
        ):
            return collector.collect_one(
                self.session,
                collector.RECOVERY_RESERVOIR,
                "78",
                self.requested,
                timeout=1,
                retry_count=0,
                retry_backoff=0,
            )

    def test_yearless_timestamp_preserves_raw_and_measurements_without_inference(self):
        self.table.loc[0] = ["Lai Châu", "01/01 14:00", 123.4, 10, 2, 8]
        record, request_error, parse_error = self.collect()
        self.assertIsNone(request_error)
        self.assertIsNone(parse_error)
        self.assertEqual(record["observation_time_raw"], "01/01 14:00")
        self.assertEqual(record["water_level_m"], 123.4)
        self.assertEqual(record["inflow_m3s"], 10.0)
        self.assertEqual(record["requested_date"], "2024-01-01")
        self.assertIsNone(record["observation_timestamp"])
        self.assertIsNone(record["observation_year_inferred"])
        self.assertEqual(record["quality_flag"], "ambiguous_year")
        self.assertEqual(record["collection_status"], "success")

    def test_yearless_timestamp_never_gets_exact_stale_or_future_at_year_boundary(self):
        for requested, raw in (
            (date(2024, 1, 1), "01/01 14:00"),
            (date(2024, 1, 1), "31/12 14:00"),
            (date(2023, 12, 31), "01/01 14:00"),
        ):
            with self.subTest(requested=requested, raw=raw):
                self.requested = requested
                self.table.loc[0] = ["Lai Châu", raw, 123.4, 10, 2, 8]
                record, _, parse_error = self.collect()
                self.assertIsNone(parse_error)
                self.assertEqual(record["quality_flag"], "ambiguous_year")
                self.assertNotIn(
                    record["quality_flag"],
                    {"exact_date", "stale_previous_observation", "future_observation"},
                )

    def test_unrecognized_or_invalid_timestamp_is_parse_failed_not_missing(self):
        for raw in ("01/01/2024 14:00", "not-a-date", "31/02 14:00"):
            with self.subTest(raw=raw):
                self.table.loc[0] = ["Lai Châu", raw, 123.4, 10, 2, 8]
                record, _, parse_error = self.collect()
                self.assertEqual(record["collection_status"], "parse_failed")
                self.assertIsNone(record["quality_flag"])
                self.assertEqual(record["observation_time_raw"], raw)
                self.assertEqual(record["water_level_m"], 123.4)
                self.assertIsNotNone(parse_error)

    def test_recognized_empty_measurement_table_is_missing(self):
        record, request_error, parse_error = self.collect()
        self.assertIsNone(request_error)
        self.assertIsNone(parse_error)
        self.assertEqual(record["collection_status"], "success")
        self.assertEqual(record["quality_flag"], "missing")

    def test_nonempty_row_without_timestamp_is_parse_failed(self):
        self.table.loc[0] = ["Lai Châu", None, 123.4, 10, 2, 8]
        record, _, parse_error = self.collect()
        self.assertEqual(record["collection_status"], "parse_failed")
        self.assertNotEqual(record["quality_flag"], "missing")
        self.assertIsNotNone(parse_error)

    def test_request_failure_keeps_retryable_status(self):
        with patch.object(
            collector, "request_with_retries", return_value=(None, "offline")
        ):
            record, request_error, parse_error = collector.collect_one(
                self.session,
                collector.RECOVERY_RESERVOIR,
                "78",
                self.requested,
                timeout=1,
                retry_count=0,
                retry_backoff=0,
            )
        self.assertEqual(record["collection_status"], "request_failed")
        self.assertEqual(request_error, "offline")
        self.assertIsNone(parse_error)

    def test_importer_accepts_ambiguous_and_parse_failed_rows_offline(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "recovery.csv"
            ambiguous = collector.make_missing_record(
                collector.RECOVERY_RESERVOIR, self.requested
            )
            ambiguous.update(
                observation_time_raw="01/01 14:00",
                observation_year_inferred=None,
                observation_year_method=None,
                water_level_m=123.4,
                quality_flag="ambiguous_year",
                collection_status="success",
            )
            failed = collector.make_missing_record(
                collector.RECOVERY_RESERVOIR, date(2024, 1, 2)
            )
            failed.update(
                observation_time_raw="unknown timestamp",
                quality_flag=None,
                collection_status="parse_failed",
            )
            pd.DataFrame([ambiguous, failed], columns=collector.OUTPUT_COLUMNS).to_csv(
                path, index=False, encoding="utf-8-sig"
            )
            with patch.object(importer, "CSV_PATH", path):
                records = importer.read_records()
        self.assertEqual(len(records), 2)
        self.assertIsNone(records[0][3])
        self.assertEqual(records[0][-2], "ambiguous_year")
        self.assertEqual(records[1][-1], "parse_failed")


class EVNReservoirRowSelectionTests(unittest.TestCase):
    HEADER = """<thead>
      <tr><th>Tên hồ</th><th>Thời điểm</th><th>H<sub>tl</sub></th><th>H<sub>dbt</sub></th><th>H<sub>c</sub></th><th>Q<sub>ve</sub></th><th>Σ<sub>Qx</sub></th><th>Q<sub>xt</sub></th><th>Q<sub>xm</sub></th><th>N<sub>cxs</sub></th><th>N<sub>cxm</sub></th></tr>
      <tr><th colspan="2">Chú thích ký hiệu</th><td>Mực nước thượng lưu (m)</td><td>Mực nước dâng bình thường (m)</td><td>Mực nước chết (m)</td><td>Lưu lượng đến hồ (m3/s)</td><td>Tổng lượng xả (m3/s)</td><td>Tổng lượng xả qua đập tràn (m3/s)</td><td>Tổng lượng xả qua nhà máy (m3/s)</td><td>Số cửa xả sâu</td><td>Số cửa xả mặt</td></tr>
    </thead>"""
    GROUP_ROW = '<tr class="tralter"><td colspan="11"><strong>Tây Bắc Bộ</strong></td></tr>'
    OBSERVATION_ROW = """<tr><td>Lai Châu<br/><small>Đồng bộ lúc: 23:10 31/01</small></td><td>03/01 14:00</td><td>294.63</td><td>295</td><td>265</td><td>81</td><td>489</td><td>0</td><td>489</td><td>0</td><td>0</td></tr>"""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.diagnostics = Path(self.temp.name) / "diagnostics"

    def html(self, rows):
        return (
            "<!doctype html><html><body><table>"
            + self.HEADER
            + "<tbody>"
            + self.GROUP_ROW
            + rows
            + "</tbody></table></body></html>"
        ).encode("utf-8")

    def collect(self, body, *, diagnostics=False, reservoir=collector.RECOVERY_RESERVOIR):
        response = SimpleNamespace(
            content=body,
            text=body.decode("utf-8"),
            status_code=200,
            headers={"Content-Type": "text/html; charset=utf-8"},
        )
        with patch.object(collector, "request_with_retries", return_value=(response, None)):
            return collector.collect_one(
                Mock(),
                reservoir,
                "78",
                date(2024, 1, 3),
                timeout=1,
                retry_count=0,
                retry_backoff=0,
                diagnostics_dir=self.diagnostics if diagnostics else None,
            )

    def test_region_group_row_is_ignored_and_lai_chau_observation_is_preserved(self):
        body = self.html(self.OBSERVATION_ROW)
        record, request_error, parse_error = self.collect(body)
        self.assertIsNone(request_error)
        self.assertIsNone(parse_error)
        self.assertEqual(record["reservoir_name"], "Lai Châu")
        self.assertEqual(record["requested_date"], "2024-01-03")
        self.assertEqual(record["observation_time_raw"], "03/01 14:00")
        self.assertEqual(record["water_level_m"], 294.63)
        self.assertEqual(record["normal_water_level_m"], 295.0)
        self.assertEqual(record["dead_water_level_m"], 265.0)
        self.assertEqual(record["inflow_m3s"], 81.0)
        self.assertEqual(record["total_discharge_m3s"], 489.0)
        self.assertEqual(record["powerhouse_discharge_m3s"], 489.0)
        self.assertEqual(record["quality_flag"], "ambiguous_year")
        self.assertEqual(record["collection_status"], "success")
        self.assertIsNone(record["observation_timestamp"])
        self.assertIsNone(record["observation_year_inferred"])
        self.assertIsNone(record["observation_year_method"])

    def test_multiple_matching_reservoir_rows_fail_and_capture_diagnostics(self):
        duplicate = self.OBSERVATION_ROW.replace("294.63", "294.50")
        record, _, parse_error = self.collect(
            self.html(self.OBSERVATION_ROW + duplicate), diagnostics=True
        )
        self.assertEqual(record["collection_status"], "parse_failed")
        self.assertIn("received 2", parse_error)
        self.assertIsNone(record["observation_time_raw"])
        metadata = json.loads(next(self.diagnostics.glob("*.json")).read_text(encoding="utf-8"))
        candidates = metadata["selected_table"]["candidate_rows"]
        self.assertEqual(len(candidates), 3)  # group heading plus both observations
        self.assertEqual(metadata["collection_outcome"], "parse_failed")
        self.assertEqual(len(list(self.diagnostics.glob("*.html"))), 1)

    def test_zero_matching_rows_fail_safely_without_treating_group_as_missing(self):
        for label in ("Tuyên Quang", "Lai Châu 2"):
            with self.subTest(label=label):
                self.diagnostics.mkdir(exist_ok=True)
                for path in self.diagnostics.iterdir():
                    path.unlink()
                unrelated = self.OBSERVATION_ROW.replace("Lai Châu<br/>", f"{label}<br/>")
                record, _, parse_error = self.collect(
                    self.html(unrelated), diagnostics=True
                )
                self.assertEqual(record["collection_status"], "parse_failed")
                self.assertIsNone(record["quality_flag"])
                self.assertIn("no timestamped row", parse_error)
                self.assertEqual(len(list(self.diagnostics.glob("*.json"))), 1)


class EVNParseDiagnosticsTests(unittest.TestCase):
    HTML = """<!doctype html><html><body>
    <table>
      <thead><tr><th>Reservoir</th><th>Observation time</th><th>htl</th><th>qve</th><th>qxt</th><th>qxm</th></tr></thead>
      <tbody>
        <tr><td>Lai Châu</td><td>01/01 14:00</td><td>123.4</td><td>10</td><td>2</td><td>8</td></tr>
        <tr><td>Lai Châu</td><td>01/01 14:00</td><td>124.0</td><td>10</td><td>2</td><td>8</td></tr>
      </tbody>
    </table></body></html>"""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / "diagnostics"
        self.html_body = self.HTML.encode("utf-8")
        self.response = SimpleNamespace(
            content=self.html_body,
            text=self.HTML,
            status_code=200,
            headers={"Content-Type": "text/html; charset=utf-8", "Set-Cookie": "must-not-be-saved"},
        )

    def collect(self, *, diagnostics_dir=None, reservoir=collector.RECOVERY_RESERVOIR):
        with patch.object(
            collector, "request_with_retries", return_value=(self.response, None)
        ) as request:
            result = collector.collect_one(
                Mock(),
                reservoir,
                "78",
                date(2024, 1, 1),
                timeout=1,
                retry_count=0,
                retry_backoff=0,
                diagnostics_dir=diagnostics_dir,
            )
        return result, request

    def test_parse_failure_captures_raw_body_metadata_and_both_rows(self):
        (record, request_error, parse_error), request = self.collect(
            diagnostics_dir=self.directory
        )
        self.assertIsNone(request_error)
        self.assertIn("Expected one observation row, received 2", parse_error)
        self.assertEqual(record["collection_status"], "parse_failed")
        self.assertIsNone(record["observation_time_raw"])
        self.assertIsNone(record["water_level_m"])
        request.assert_called_once()

        html_files = list(self.directory.glob("*.html"))
        json_files = list(self.directory.glob("*.json"))
        self.assertEqual(len(html_files), 1)
        self.assertEqual(len(json_files), 1)
        self.assertEqual(html_files[0].read_bytes(), self.html_body)
        metadata = json.loads(json_files[0].read_text(encoding="utf-8"))
        self.assertEqual(metadata["reservoir_name"], collector.RECOVERY_RESERVOIR)
        self.assertEqual(metadata["requested_date"], "2024-01-01")
        self.assertEqual(metadata["http_status"], 200)
        self.assertEqual(metadata["content_type"], "text/html; charset=utf-8")
        self.assertEqual(metadata["collection_outcome"], "parse_failed")
        self.assertIn("Expected one observation row, received 2", metadata["parser_error"])
        table = metadata["selected_table"]
        self.assertEqual(table["dimensions"], {"rows": 2, "columns": 6})
        self.assertEqual(len(table["candidate_rows"]), 2)
        self.assertEqual(
            [row["first_two_cells"] for row in table["candidate_rows"]],
            [["Lai Châu", "01/01 14:00"], ["Lai Châu", "01/01 14:00"]],
        )
        self.assertNotIn("Set-Cookie", json_files[0].read_text(encoding="utf-8"))
        self.assertEqual(set(metadata["request_parameters"]), {"td", "vm", "lv", "hc"})

    def test_diagnostics_are_disabled_when_directory_is_not_supplied(self):
        self.assertIsNone(collector.parse_args([]).diagnostics_dir)
        configured = collector.parse_args(["--diagnostics-dir", str(self.directory)])
        self.assertEqual(configured.diagnostics_dir, self.directory)
        (record, _, parse_error), _ = self.collect()
        self.assertEqual(record["collection_status"], "parse_failed")
        self.assertIn("received 2", parse_error)
        self.assertFalse(self.directory.exists())

    def test_safe_filenames_and_unique_artifacts_for_repeated_attempts(self):
        malicious_label = "../Lai Châu/../../pilot?"
        self.collect(diagnostics_dir=self.directory, reservoir=malicious_label)
        self.collect(diagnostics_dir=self.directory, reservoir=malicious_label)
        artifacts = list(self.directory.iterdir())
        self.assertEqual(len(artifacts), 4)
        self.assertEqual(len({path.name for path in artifacts}), 4)
        for path in artifacts:
            self.assertNotIn("..", path.name)
            self.assertNotIn("/", path.name)
            self.assertNotIn("\\", path.name)
            self.assertRegex(path.name, r"^[A-Za-z0-9_.-]+\.(html|json)$")


if __name__ == "__main__":
    unittest.main()
