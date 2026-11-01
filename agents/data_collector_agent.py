
"""Central orchestration agent for weather, MRC, EVN and hydrology data collection."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _classify_freshness(
    timestamp: Any,
    now: datetime,
) -> tuple[str, float]:
    """Classify one station observation using its UTC timestamp."""
    import pandas as pd

    observation = pd.Timestamp(timestamp)

    if observation.tzinfo is None:
        observation = observation.tz_localize("UTC")
    else:
        observation = observation.tz_convert("UTC")

    age_hours = (
        now - observation.to_pydatetime()
    ).total_seconds() / 3600

    if age_hours < 0:
        status = "future_timestamp"
    elif age_hours <= 3:
        status = "fresh"
    elif age_hours <= 6:
        status = "aging"
    else:
        status = "stale"

    return status, round(age_hours, 2)


def _run_weather_collector(
    limit: int | None = None,
) -> dict[str, Any]:
    """Refresh Open-Meteo weather model inputs."""
    from data_pipeline.crawlers.weather.refresh_weather_inputs import refresh

    started_at = _utc_now()
    records = refresh(limit=limit)

    if type(records) is not int or records < 1:
        raise RuntimeError(
            f"Weather collector returned an invalid record count: {records!r}"
        )

    return {
        "source": "open_meteo_weather_inputs",
        "status": "success",
        "records_processed": records,
        "started_at_utc": started_at,
        "completed_at_utc": _utc_now(),
    }


def _run_evn_collector() -> dict[str, Any]:
    """Fetch, validate, save and import current EVN reservoir observations."""
    from data_pipeline.crawlers.evn_reservoir import (
        OUTPUT_PATH,
        clean_evn_table,
        fetch_evn_table,
        validate_evn_data,
    )
    from data_pipeline.database.import_evn_reservoirs import (
        import_current_reservoirs,
    )

    started_at = _utc_now()

    # 1. Fetch the live EVN reservoir table.
    raw_df = fetch_evn_table()

    if raw_df is None or raw_df.empty:
        raise RuntimeError("EVN returned an empty reservoir table.")

    # 2. Clean the raw table.
    cleaned_df = clean_evn_table(raw_df)

    if cleaned_df is None or cleaned_df.empty:
        raise RuntimeError(
            "EVN returned data, but no valid reservoir records remained after cleaning."
        )

    # 3. Run the crawler's existing quality report.
    validate_evn_data(cleaned_df)

    # 4. Save the cleaned data for traceability and reuse.
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    cleaned_df.to_csv(
        OUTPUT_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    # 5. Import using the existing database importer.
    # The importer handles timestamp parsing, validation and safe upserts.
    import_result = import_current_reservoirs(
        csv_path=OUTPUT_PATH,
    )

    if import_result.get("status") != "success":
        raise RuntimeError(
            f"EVN database import did not succeed: {import_result}"
        )

    return {
        **import_result,
        "source": "evn_reservoir_current",
        "status": "success",
        "raw_records_received": len(raw_df),
        "cleaned_records": len(cleaned_df),
        "csv_path": str(OUTPUT_PATH),
        "started_at_utc": started_at,
        "completed_at_utc": _utc_now(),
    }


def _run_mrc_collector() -> dict[str, Any]:
    """Collect MRC measurements with station-level quality and freshness reporting."""
    import pandas as pd

    from data_pipeline.database.update_mrc_latest import (
        clean_measurements,
        fetch_station_measurements,
        fetch_vietnam_stations,
        get_db_connection,
        insert_new_records,
        print_latest_database_state,
    )

    started_at = _utc_now()
    stations = fetch_vietnam_stations()

    if not stations:
        raise RuntimeError("MRC returned no Vietnam stations.")

    raw_rows: list[dict[str, Any]] = []
    station_reports: list[dict[str, Any]] = []
    successful_stations = 0
    failed_stations = 0

    # Collect independently so one station failure does not stop the others.
    for station in stations:
        station_id = str(station.get("stationId") or "").strip()
        station_name = station.get("name")

        if not station_id:
            failed_stations += 1
            station_reports.append({
                "station_id": None,
                "station_name": station_name,
                "status": "invalid_data",
                "records_collected": 0,
                "records_validated": 0,
                "latest_observation_utc": None,
                "observation_age_hours": None,
                "error": "Station has no stationId.",
            })
            continue

        try:
            rows = fetch_station_measurements(station_id)

            if not isinstance(rows, list):
                raise TypeError(
                    f"Expected a list of measurements, got {type(rows).__name__}."
                )

            successful_stations += 1

            if not rows:
                station_reports.append({
                    "station_id": station_id,
                    "station_name": station_name,
                    "status": "no_data",
                    "records_collected": 0,
                    "records_validated": 0,
                    "latest_observation_utc": None,
                    "observation_age_hours": None,
                    "error": None,
                })
                continue

            # Use the station ID from the request as the authoritative ID.
            for row in rows:
                if not isinstance(row, dict):
                    raise TypeError(
                        "A measurement record was not a dictionary."
                    )

                normalized_row = dict(row)
                normalized_row["station_id"] = station_id
                raw_rows.append(normalized_row)

            station_reports.append({
                "station_id": station_id,
                "station_name": station_name,
                "status": "pending_validation",
                "records_collected": len(rows),
                "records_validated": 0,
                "latest_observation_utc": None,
                "observation_age_hours": None,
                "error": None,
            })

        except Exception as exc:
            failed_stations += 1
            station_reports.append({
                "station_id": station_id,
                "station_name": station_name,
                "status": "api_error",
                "records_collected": 0,
                "records_validated": 0,
                "latest_observation_utc": None,
                "observation_age_hours": None,
                "error": f"{type(exc).__name__}: {exc}",
            })

    if not raw_rows:
        status_counts: dict[str, int] = {}
        for report in station_reports:
            status = report["status"]
            status_counts[status] = status_counts.get(status, 0) + 1

        raise RuntimeError(
            "MRC collection produced no measurements. "
            f"Station status counts: {status_counts}."
        )

    raw_data = pd.DataFrame(raw_rows)
    cleaned_data = clean_measurements(raw_data)

    if cleaned_data.empty:
        raise RuntimeError(
            "MRC collection returned measurements, but none passed cleaning."
        )

    # Calculate freshness independently for every station.
    now = datetime.now(timezone.utc)
    valid_freshness_statuses: list[str] = []

    for report in station_reports:
        station_id = report["station_id"]

        if not station_id or report["status"] in {"api_error", "no_data"}:
            continue

        station_data = cleaned_data[
            cleaned_data["station_id"].astype(str) == station_id
        ]

        if station_data.empty:
            report["status"] = "invalid_data"
            report["records_validated"] = 0
            report["error"] = (
                "Measurements were returned, but none passed cleaning."
            )
            continue

        latest_timestamp = station_data["timestamp_utc"].max()
        freshness, age_hours = _classify_freshness(latest_timestamp, now)

        report["status"] = freshness
        report["records_validated"] = len(station_data)
        report["latest_observation_utc"] = latest_timestamp.isoformat()
        report["observation_age_hours"] = age_hours

        valid_freshness_statuses.append(freshness)

    if not valid_freshness_statuses:
        status_counts: dict[str, int] = {}
        for report in station_reports:
            status = report["status"]
            status_counts[status] = status_counts.get(status, 0) + 1

        raise RuntimeError(
            "MRC returned measurements, but no station had valid observations. "
            f"Station status counts: {status_counts}."
        )

    # The overall status must not hide stale stations behind one fresh station.
    if "future_timestamp" in valid_freshness_statuses:
        overall_freshness = "future_timestamp"
    elif all(status == "fresh" for status in valid_freshness_statuses):
        overall_freshness = "fresh"
    elif any(status == "fresh" for status in valid_freshness_statuses):
        overall_freshness = "mixed"
    elif "aging" in valid_freshness_statuses:
        overall_freshness = "aging"
    else:
        overall_freshness = "stale"

    status_counts: dict[str, int] = {}
    for report in station_reports:
        status = report["status"]
        status_counts[status] = status_counts.get(status, 0) + 1

    latest_timestamp = cleaned_data["timestamp_utc"].max()

    # Only validated measurements are passed to the existing DB insertion code.
    connection = get_db_connection()

    try:
        submitted = insert_new_records(connection, cleaned_data)
        print_latest_database_state(connection)
    finally:
        connection.close()

    # Keep the one-hour forecast service's derived feature file synchronized
    # with the same persisted telemetry used by the monitoring API.
    try:
        from data_pipeline.database.refresh_mrc_forecast_features import (
            refresh_mrc_forecast_features,
        )

        forecast_feature_refresh = refresh_mrc_forecast_features()
    except Exception as exc:
        forecast_feature_refresh = {
            "status": "failed",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }

    # No-data and invalid-data stations indicate incomplete coverage.
    coverage_problem_statuses = {
        "api_error",
        "no_data",
        "invalid_data",
        "aging",
        "stale",
        "future_timestamp",
    }
    has_coverage_problems = any(
        report["status"] in coverage_problem_statuses
        for report in station_reports
    )

    overall_status = "partial" if has_coverage_problems else "success"
    if forecast_feature_refresh["status"] != "success":
        overall_status = "partial"

    return {
        "source": "mrc_mekong_telemetry",
        "status": overall_status,
        "stations_discovered": len(stations),
        "stations_succeeded": successful_stations,
        "stations_failed": failed_stations,
        "stations_with_valid_data": len(valid_freshness_statuses),
        "station_status_counts": status_counts,
        "station_reports": station_reports,
        "station_failures": [
            report for report in station_reports
            if report["status"] == "api_error"
        ],
        "records_collected": len(raw_data),
        "records_validated": len(cleaned_data),
        "records_submitted_to_insert": submitted,
        "forecast_feature_refresh": forecast_feature_refresh,
        "latest_observation_utc": latest_timestamp.isoformat(),
        "freshness_status": overall_freshness,
        "started_at_utc": started_at,
        "completed_at_utc": _utc_now(),
    }



def _run_hydrology_collector() -> dict[str, Any]:
    """Refresh active national hydrology stations."""
    from data_pipeline.crawlers.refresh_hydrology_observations import refresh

    started_at = _utc_now()
    result = refresh()

    if not isinstance(result, dict) or result.get("status") not in {
        "success",
        "partial",
    }:
        raise RuntimeError(
            f"Hydrology collector returned an invalid result: {result!r}"
        )

    return {
        **result,
        "source": "national_hydrology_station_api",
        "started_at_utc": started_at,
        "completed_at_utc": _utc_now(),
    }


def run_data_collector(
    sources: list[str] | None = None,
    weather_limit: int | None = None,
) -> dict[str, Any]:
    """Run selected collection workers independently."""

    selected_sources = (
        ["weather", "mrc", "evn", "hydrology"] if sources is None else list(sources)
    )
    selected_sources = list(dict.fromkeys(selected_sources))

    supported_sources = {
        "weather": lambda: _run_weather_collector(weather_limit),
        "mrc": _run_mrc_collector,
        "evn": _run_evn_collector,
        "hydrology": _run_hydrology_collector,
    }

    unknown_sources = [
        source for source in selected_sources
        if source not in supported_sources
    ]

    if unknown_sources:
        raise ValueError(
            f"Unsupported collection sources: {unknown_sources}. "
            f"Supported sources: {sorted(supported_sources)}"
        )

    if not selected_sources:
        raise ValueError("At least one collection source must be selected.")

    started_at = _utc_now()
    results: dict[str, Any] = {}
    errors: dict[str, Any] = {}

    for source in selected_sources:
        try:
            results[source] = supported_sources[source]()
        except Exception as exc:
            errors[source] = {
                "error_type": type(exc).__name__,
                "message": str(exc),
                "failed_at_utc": _utc_now(),
            }

    successful_count = sum(
        result.get("status", "success") == "success"
        for result in results.values()
    )
    partial_count = sum(
        result.get("status") == "partial"
        for result in results.values()
    )
    failed_count = len(errors)

    if failed_count == 0 and partial_count == 0:
        overall_status = "success"
    elif successful_count > 0 or partial_count > 0:
        overall_status = "partial"
    else:
        overall_status = "failed"

    return {
        "agent": "data_collector",
        "status": overall_status,
        "started_at_utc": started_at,
        "completed_at_utc": _utc_now(),
        "summary": {
            "requested_sources": len(selected_sources),
            "successful_sources": successful_count,
            "partial_sources": partial_count,
            "failed_sources": failed_count,
        },
        "sources": results,
        "errors": errors,
    }


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description="Run selected Weather AI data collection workers."
    )
    parser.add_argument(
        "--sources",
        nargs="+",
        choices=["weather", "mrc", "evn", "hydrology"],
        default=["weather", "mrc", "evn", "hydrology"],
    )
    parser.add_argument(
        "--weather-limit",
        type=int,
        default=None,
    )

    args = parser.parse_args()

    if args.weather_limit is not None and args.weather_limit < 1:
        parser.error("--weather-limit must be positive.")

    report = run_data_collector(
        sources=args.sources,
        weather_limit=args.weather_limit,
    )

    print(json.dumps(report, indent=2, default=str))

    # Treat partial collection as a non-zero exit so scheduled workflows
    # visibly flag incomplete source/station coverage instead of appearing green.
       # Fail the workflow only for actual collection errors or failed
    # forecast-feature generation. Station freshness/coverage warnings
    # remain visible in the JSON report without failing the workflow.
    mrc_result = report.get("sources", {}).get("mrc", {})
    feature_result = mrc_result.get("forecast_feature_refresh", {})

    has_collection_errors = bool(report.get("errors"))
    has_feature_refresh_failure = (
        bool(mrc_result)
        and feature_result.get("status") != "success"
    )

    if (
        report.get("status") == "failed"
        or has_collection_errors
        or has_feature_refresh_failure
    ):
        raise SystemExit(1)