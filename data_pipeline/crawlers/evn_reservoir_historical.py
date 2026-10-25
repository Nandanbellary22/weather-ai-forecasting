"""Collect date-specific historical snapshots from EVN's public reservoir page."""

from __future__ import annotations

import argparse
from collections import Counter
import html
import json
import os
import re
import sys
import tempfile
import time
import unicodedata
import uuid
from datetime import date, datetime, time as datetime_time, timedelta, timezone
from html.parser import HTMLParser
from io import StringIO
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit

import pandas as pd
import requests


EVN_URL = (
    "https://hochuathuydien.evn.com.vn/"
    "PageHoChuaThuyDienEmbedEVN.aspx"
)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_PATH = PROJECT_ROOT / "data" / "processed" / "evn_reservoir_historical.csv"
RECOVERY_RESERVOIR = "Lai Châu"
MAIN_OUTPUT_PATHS = {
    OUTPUT_PATH.resolve(),
    (PROJECT_ROOT / "data" / "processed" / "evn_reservoir_historical_test.csv").resolve(),
}
SOURCE = "EVN"

# Candidate collection starts based on the sampled EVN availability probe.
# These are planning cutoffs, not evidence of continuous historical coverage.
RESERVOIR_START_DATES: dict[str, date | None] = {
    'Tuyên Quang': date(2020, 1, 1),
    'Sơn La': date(2020, 1, 1),
    'Hòa Bình': date(2020, 1, 1),
    'Thác Bà': date(2020, 1, 1),
    'Buôn Tua Srah': date(2020, 1, 1),
    'Buôn Kuốp': date(2020, 1, 1),
    'Srêpốk 3': date(2020, 1, 1),
    'Vĩnh Sơn A': date(2020, 1, 1),
    'Vĩnh Sơn B': date(2020, 1, 1),
    'Vĩnh Sơn C': date(2020, 1, 1),
    'An Khê': date(2020, 1, 1),
    'Ka Nak': date(2020, 1, 1),
    'Pleikrông': date(2020, 1, 1),
    'Ialy': date(2020, 1, 1),
    'Bản Vẽ': date(2020, 1, 1),
    'Sông Ba Hạ': date(2020, 1, 1),
    'A Vương': date(2020, 1, 1),
    'Sông Tranh 2': date(2020, 1, 1),
    'Quảng Trị': date(2020, 1, 1),
    'Trị An': date(2020, 1, 1),
    'Đại Ninh': date(2020, 1, 1),
    'Đơn Dương': date(2020, 1, 1),
    'Đồng Nai 3': date(2020, 1, 1),
    'Sê San 3': date(2020, 1, 1),
    'Sê San 3A': date(2020, 1, 1),
    'Sê San 4': date(2020, 1, 1),
    'Thác Mơ': date(2020, 1, 1),
    'Hàm Thuận': date(2020, 1, 1),
    'Đa Mi': date(2020, 1, 1),
    'Sông Hinh': date(2020, 1, 1),
    'Đồng Nai 4': date(2020, 1, 1),
    'Bản Chát': date(2020, 1, 1),
    'Huội Quảng': date(2020, 1, 1),
    'Trung Sơn': date(2020, 1, 1),
    'Sông Bung 2': date(2020, 1, 1),
    'Sông Bung 4': date(2020, 1, 1),
    'Thượng Kon Tum': date(2022, 1, 1),
    'Lai Châu': date(2024, 1, 1),
    'Khe Bố': date(2026, 1, 1),
    'Sê San 4A': None,
    'A Lưới': None,
}
OUTPUT_COLUMNS = [
    "reservoir_name",
    "requested_date",
    "observation_time_raw",
    "observation_timestamp",
    "observation_year_inferred",
    "observation_year_method",
    "water_level_m",
    "normal_water_level_m",
    "dead_water_level_m",
    "inflow_m3s",
    "total_discharge_m3s",
    "spillway_discharge_m3s",
    "powerhouse_discharge_m3s",
    "deep_release_gates",
    "surface_release_gates",
    "source",
    "quality_flag",
    "collection_status",
]
QUALITY_FLAGS = {
    "exact_date",
    "stale_previous_observation",
    "future_observation",
    "missing",
    "ambiguous_year",
}
NUMERIC_FIELDS = OUTPUT_COLUMNS[3:12]
EVN_FIELD_CODES = {
    "water_level_m": {"htl"},
    "normal_water_level_m": {"hdbt"},
    "dead_water_level_m": {"hc"},
    "inflow_m3s": {"qve"},
    "total_discharge_m3s": {"σqx", "∑qx"},
    "spillway_discharge_m3s": {"qxt"},
    "powerhouse_discharge_m3s": {"qxm"},
    "deep_release_gates": {"ncxs"},
    "surface_release_gates": {"ncxm"},
}
OBSERVATION_TIME_RE = re.compile(r"^(\d{2})/(\d{2})\s+(\d{2}):(\d{2})$")


class ReservoirOptionParser(HTMLParser):
    """Read reservoir labels and values from the page's visible select control."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_reservoir_select = False
        self.current_option_value: str | None = None
        self.current_option_text: list[str] = []
        self.options: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag == "select":
            self.in_reservoir_select = (attrs_dict.get("name") or "").endswith(
                "$ddlHoChua"
            )
        elif tag == "option" and self.in_reservoir_select:
            self.current_option_value = attrs_dict.get("value")
            self.current_option_text = []

    def handle_data(self, data: str) -> None:
        if self.current_option_value is not None:
            self.current_option_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "option" and self.current_option_value is not None:
            label = normalize_text("".join(self.current_option_text))
            if label and self.current_option_value:
                self.options[label] = self.current_option_value
            self.current_option_value = None
            self.current_option_text = []
        elif tag == "select":
            self.in_reservoir_select = False


def normalize_text(value: str) -> str:
    return unicodedata.normalize("NFC", html.unescape(value)).replace("\xa0", " ").strip()


def normalize_header(value: object) -> str:
    """Normalize EVN's short field code, including common mojibake variants."""
    text = normalize_text(str(value)).casefold().replace(" ", "")
    try:
        repaired = text.encode("latin1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        repaired = text
    return repaired.casefold().replace(" ", "")


def request_with_retries(
    session: requests.Session,
    url: str,
    *,
    timeout: float,
    retry_count: int,
    retry_backoff: float,
) -> tuple[requests.Response | None, str | None]:
    """Retry failed HTTP requests, then return the final error for this date."""
    for attempt in range(retry_count + 1):
        try:
            response = session.get(url, timeout=timeout)
            response.raise_for_status()
            return response, None
        except requests.RequestException as exc:
            if attempt >= retry_count:
                return None, str(exc)
            delay = retry_backoff * (2**attempt)
            print(
                f"Request attempt {attempt + 1} failed; retrying in {delay:g}s: {exc}",
                file=sys.stderr,
            )
            if delay:
                time.sleep(delay)
    return None, "Request failed without an exception detail."


def fetch_reservoir_options(
    session: requests.Session,
    *,
    timeout: float,
    retry_count: int,
    retry_backoff: float,
) -> dict[str, str]:
    response, error = request_with_retries(
        session,
        EVN_URL,
        timeout=timeout,
        retry_count=retry_count,
        retry_backoff=retry_backoff,
    )
    if response is None:
        raise requests.RequestException(f"Could not load EVN reservoir selector: {error}")
    parser = ReservoirOptionParser()
    parser.feed(response.text)
    if not parser.options:
        raise ValueError("EVN page did not contain its visible reservoir selector.")
    return parser.options


def resolve_reservoir_names(
    requested_names: list[str], options: dict[str, str]
) -> list[tuple[str, str]]:
    """Resolve labels to IDs from the visible page; never synthesize an ID."""
    by_casefold = {normalize_text(label).casefold(): (label, value) for label, value in options.items()}
    resolved = []
    missing = []
    for requested in requested_names:
        match = by_casefold.get(normalize_text(requested).casefold())
        if match is None:
            missing.append(requested)
        else:
            resolved.append(match)
    if missing:
        raise ValueError(f"Reservoirs not found in EVN's visible selector: {missing}")
    return resolved


def flatten_table(raw: pd.DataFrame) -> pd.DataFrame:
    table = raw.copy()
    if isinstance(table.columns, pd.MultiIndex):
        table.columns = [str(column[0]).strip() for column in table.columns]
    else:
        table.columns = [str(column).strip() for column in table.columns]
    return table


def locate_field_columns(table: pd.DataFrame) -> dict[str, object]:
    normalized = {normalize_header(column): column for column in table.columns}
    fields: dict[str, object] = {}
    for output_name, aliases in EVN_FIELD_CODES.items():
        for alias in aliases:
            if alias in normalized:
                fields[output_name] = normalized[alias]
                break
    # Core fields must exist to interpret a returned record safely.
    required = {"water_level_m", "inflow_m3s", "spillway_discharge_m3s", "powerhouse_discharge_m3s"}
    missing = required - fields.keys()
    if missing:
        raise ValueError(f"EVN table is missing expected measurement columns: {sorted(missing)}")
    return fields


def observation_rows(
    table: pd.DataFrame, reservoir_name: str
) -> list[tuple[str, str, pd.Series]]:
    """Return timestamp rows whose leading label identifies the selected reservoir.

    EVN appends a synchronization annotation after the visible reservoir label.
    Accept the exact label or that observed annotation form; do not accept an
    arbitrary label suffix that could belong to a different reservoir.
    """
    if table.shape[1] < 2:
        raise ValueError("EVN table has fewer than two columns.")
    expected_name = " ".join(normalize_text(reservoir_name).casefold().split())
    found = []
    for _, row in table.iterrows():
        name_value = row.iloc[0]
        timestamp_value = row.iloc[1]
        if pd.isna(name_value) or pd.isna(timestamp_value):
            continue
        name_raw = normalize_text(str(name_value))
        name = " ".join(name_raw.casefold().split())
        annotated_name = re.fullmatch(
            re.escape(expected_name)
            + r"\s+đồng bộ lúc:\s*\d{2}:\d{2}\s+\d{2}/\d{2}",
            name,
        )
        if name != expected_name and annotated_name is None:
            continue
        timestamp_raw = str(timestamp_value)
        found.append((name_raw, timestamp_raw, row))
    return found


def validate_yearless_observation_timestamp(timestamp: str) -> None:
    """Validate only the observed yearless DD/MM HH:MM format; infer no year."""
    match = OBSERVATION_TIME_RE.fullmatch(timestamp)
    if match is None:
        raise ValueError(f"Unexpected EVN observation timestamp: {timestamp!r}")
    day, month, hour, minute = map(int, match.groups())
    try:
        # A leap year validates the month/day pair without assigning a year.
        date(2000, month, day)
        datetime_time(hour, minute)
    except ValueError as exc:
        raise ValueError(f"Invalid EVN observation date/time: {timestamp!r}")


def number_or_none(value: object) -> float | None:
    if pd.isna(value):
        return None
    parsed = pd.to_numeric(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return float(parsed)


def diagnostic_cell(value: object) -> str | None:
    """Convert a table cell into safe, JSON-serializable diagnostic text."""
    if pd.isna(value):
        return None
    return str(value)


def save_parse_diagnostics(
    diagnostics_dir: Path,
    *,
    reservoir_name: str,
    requested_date: date,
    request_url: str,
    response: requests.Response,
    parse_error: Exception,
    table_diagnostic: dict[str, object] | None,
) -> tuple[Path, Path]:
    """Save a parse-failure body and sanitized metadata without overwriting files."""
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    slug = unicodedata.normalize("NFKD", reservoir_name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", slug).strip("_") or "reservoir"
    attempt_id = uuid.uuid4().hex
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    stem = f"{slug}_{requested_date.isoformat()}_{timestamp}_{attempt_id}"
    body_path = diagnostics_dir / f"{stem}.html"
    metadata_path = diagnostics_dir / f"{stem}.json"

    body = getattr(response, "content", None)
    if not isinstance(body, bytes):
        body = str(response.text).encode("utf-8")
    headers = getattr(response, "headers", {}) or {}
    content_type = next(
        (str(value) for key, value in headers.items() if str(key).casefold() == "content-type"),
        None,
    )
    metadata = {
        "attempt_id": attempt_id,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "reservoir_name": reservoir_name,
        "requested_date": requested_date.isoformat(),
        "request_endpoint": EVN_URL,
        "request_parameters": {
            key: value
            for key, value in parse_qsl(urlsplit(request_url).query, keep_blank_values=True)
            if key in {"td", "hc", "vm", "lv"}
        },
        "http_status": getattr(response, "status_code", None),
        "content_type": content_type,
        "selected_table": table_diagnostic,
        "parser_error": f"{type(parse_error).__name__}: {parse_error}",
        "collection_outcome": "parse_failed",
        "response_body_file": body_path.name,
    }
    # Exclusive creation prevents collisions from overwriting earlier evidence.
    with body_path.open("xb") as body_file:
        body_file.write(body)
    with metadata_path.open("x", encoding="utf-8", newline="") as metadata_file:
        json.dump(metadata, metadata_file, ensure_ascii=False, indent=2)
        metadata_file.write("\n")
    return body_path, metadata_path


def make_missing_record(reservoir_name: str, requested_date: date) -> dict[str, object]:
    row = {column: None for column in OUTPUT_COLUMNS}
    row.update(
        reservoir_name=reservoir_name,
        requested_date=requested_date.isoformat(),
        source=SOURCE,
        quality_flag=None,
        collection_status=None,
    )
    return row


def collect_one(
    session: requests.Session,
    reservoir_name: str,
    reservoir_id: str,
    requested_date: date,
    *,
    timeout: float,
    retry_count: int,
    retry_backoff: float,
    diagnostics_dir: Path | None = None,
) -> tuple[dict[str, object], str | None, str | None]:
    """Return (record, request_error, parsing_error) for one public query."""
    record = make_missing_record(reservoir_name, requested_date)
    requested_datetime = datetime.combine(requested_date, datetime_time(14, 0))
    query = urlencode(
        {
            "td": requested_datetime.strftime("%d/%m/%Y %H:%M"),
            "vm": "",
            "lv": "",
            "hc": reservoir_id,
        }
    )
    request_url = f"{EVN_URL}?{query}"
    response, request_error = request_with_retries(
        session,
        request_url,
        timeout=timeout,
        retry_count=retry_count,
        retry_backoff=retry_backoff,
    )
    if response is None:
        record["collection_status"] = "request_failed"
        return record, request_error, None

    table_diagnostic: dict[str, object] | None = None
    try:
        tables = pd.read_html(StringIO(response.text))
        if not tables:
            raise ValueError("No HTML table returned.")
        table = flatten_table(tables[0])
        candidate_rows = [
            {
                "row_index": int(index),
                "first_two_cells": [
                    diagnostic_cell(row.iloc[0]),
                    diagnostic_cell(row.iloc[1]),
                ],
            }
            for index, row in table.iterrows()
            if table.shape[1] >= 2 and not pd.isna(row.iloc[1])
        ]
        table_diagnostic = {
            "columns": [str(column) for column in table.columns],
            "dimensions": {"rows": int(table.shape[0]), "columns": int(table.shape[1])},
            "candidate_rows": candidate_rows,
        }
        field_columns = locate_field_columns(table)
        if table.empty:
            # An expected measurement table with its headers and no data rows
            # is the only currently recognized evidence of a missing result.
            record["collection_status"] = "success"
            record["quality_flag"] = "missing"
            return record, None, None
        rows = observation_rows(table, reservoir_name)
        if not rows:
            raise ValueError(
                f"EVN table contains no timestamped row for reservoir {reservoir_name!r}."
            )

        # Duplicate rows for the selected reservoir remain ambiguous and are not guessed.
        if len(rows) != 1:
            raise ValueError(f"Expected one observation row, received {len(rows)}.")
        _, timestamp_raw, source_row = rows[0]
        record["observation_time_raw"] = timestamp_raw
        for output_name, column in field_columns.items():
            record[output_name] = number_or_none(source_row.get(column))
        validate_yearless_observation_timestamp(normalize_text(timestamp_raw))
        record["observation_timestamp"] = None
        record["observation_year_inferred"] = None
        record["observation_year_method"] = None
        record["collection_status"] = "success"
        record["quality_flag"] = "ambiguous_year"
        return record, None, None
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        record["collection_status"] = "parse_failed"
        parse_error = str(exc)
        if diagnostics_dir is not None:
            try:
                body_path, metadata_path = save_parse_diagnostics(
                    diagnostics_dir,
                    reservoir_name=reservoir_name,
                    requested_date=requested_date,
                    request_url=request_url,
                    response=response,
                    parse_error=exc,
                    table_diagnostic=table_diagnostic,
                )
                print(
                    f"Parse diagnostics saved: {body_path} and {metadata_path}",
                    file=sys.stderr,
                )
            except OSError as diagnostic_error:
                parse_error += f" (diagnostic capture failed: {diagnostic_error})"
                print(f"Could not save EVN parse diagnostics: {diagnostic_error}", file=sys.stderr)
        return record, None, parse_error


def date_range(start: date, end: date) -> list[date]:
    if end < start:
        raise ValueError("End date must be on or after start date.")
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def parse_cli_date(value: str) -> date:
    """Parse a CLI date in the documented YYYY-MM-DD form."""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD format")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid date: {value}") from exc


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", dest="dry_run", action="store_true")
    mode.add_argument(
        "--collect",
        dest="dry_run",
        action="store_false",
        help="Send historical queries and reconcile the CSV. Omit for planning only.",
    )
    parser.set_defaults(dry_run=True)
    parser.add_argument("--start-date", type=parse_cli_date)
    parser.add_argument("--end-date", type=date.fromisoformat, default=date.today())
    parser.add_argument("--request-delay", type=float, default=0.15)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--retry-count", type=int, default=3,
                        help="Retries after the initial request; total attempts are retry-count + 1.")
    parser.add_argument("--retry-backoff", type=float, default=1.0,
                        help="Initial retry delay in seconds; subsequent delays double.")
    parser.add_argument("--checkpoint-every", type=int, default=500,
                        help="Atomically reconcile collected records every N attempted dates.")
    parser.add_argument(
        "--diagnostics-dir",
        type=Path,
        help="Opt in to saving raw response bodies and parse metadata for parsing failures.",
    )
    parser.add_argument(
        "--reservoirs",
        nargs="+",
        help="Reservoir labels exactly as displayed in EVN's selector.",
    )
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument(
        "--recovery-lai-chau",
        action="store_true",
        help="Run isolated Lai Châu recovery; requires --output and never writes either established CSV.",
    )
    parser.add_argument(
        "--refresh-stale",
        action="store_true",
        help="In Lai Châu recovery mode, retry keys currently marked stale_previous_observation.",
    )
    args = parser.parse_args(argv)
    if args.request_delay < 0 or args.timeout <= 0 or args.retry_backoff < 0:
        parser.error("request delay/backoff must be non-negative and timeout must be positive")
    if args.retry_count < 0 or args.checkpoint_every <= 0:
        parser.error("retry count must be non-negative and checkpoint interval must be positive")
    if args.start_date is not None and args.start_date > args.end_date:
        parser.error("--start-date must be on or before --end-date")
    if args.recovery_lai_chau:
        if argv is None:
            explicit_args = sys.argv[1:]
        else:
            explicit_args = argv
        explicit_flags = {
            argument.split("=", 1)[0]
            for argument in explicit_args
            if argument.startswith("--")
        }
        if "--start-date" not in explicit_flags:
            parser.error("--recovery-lai-chau requires an explicit --start-date")
        if "--end-date" not in explicit_flags:
            parser.error("--recovery-lai-chau requires an explicit --end-date")
        if not any(
            argument == "--output" or argument.startswith("--output=")
            for argument in explicit_args
        ):
            parser.error("--recovery-lai-chau requires an explicit --output path")
        try:
            ensure_safe_recovery_output(args.output)
        except ValueError as exc:
            parser.error(str(exc))
        if args.reservoirs and args.reservoirs != [RECOVERY_RESERVOIR]:
            parser.error("Lai Châu recovery cannot target other reservoirs")
        args.reservoirs = [RECOVERY_RESERVOIR]
    elif args.refresh_stale:
        parser.error("--refresh-stale is available only with --recovery-lai-chau")
    return args


def build_collection_plan(
    options: dict[str, str], end_date: date, start_date: date | None = None
) -> list[dict[str, object]]:
    """Join visible EVN names/IDs to configured candidate start dates."""
    plan = []
    for reservoir_name, reservoir_id in options.items():
        configured_start = RESERVOIR_START_DATES.get(reservoir_name)
        collection_start = start_date if start_date is not None else configured_start
        configured = reservoir_name in RESERVOIR_START_DATES
        included = configured and collection_start is not None and collection_start <= end_date
        requested_dates = (
            len(date_range(collection_start, end_date)) if included else 0
        )
        if not configured:
            status = "excluded: no start-date configuration"
        elif collection_start is None:
            status = "excluded: insufficient sampled availability"
        elif collection_start > end_date:
            status = "excluded: start date is after end date"
        else:
            status = "included"
        plan.append(
            {
                "reservoir_name": reservoir_name,
                "evn_id": reservoir_id,
                "configured_start_date": configured_start,
                "collection_start_date": collection_start,
                "included": included,
                "estimated_dates": requested_dates,
                "status": status,
            }
        )
    return plan


def print_collection_plan(plan: list[dict[str, object]], end_date: date) -> None:
    print("EVN historical collection plan (dry run; no observation queries sent)")
    print(f"Configured end date: {end_date.isoformat()}")
    print("reservoir_name | evn_id | configured_start_date | collection_start_date | included | estimated_dates | status")
    total = 0
    for item in plan:
        start = item["configured_start_date"]
        start_text = start.isoformat() if isinstance(start, date) else "—"
        collection_start = item["collection_start_date"]
        collection_start_text = (
            collection_start.isoformat() if isinstance(collection_start, date) else "—"
        )
        total += int(item["estimated_dates"])
        print(
            f"{item['reservoir_name']} | {item['evn_id']} | {start_text} | {collection_start_text} | "
            f"{'yes' if item['included'] else 'no'} | {item['estimated_dates']} | {item['status']}"
        )
    print(f"Visible reservoir options: {len(plan)}")
    print(f"Included reservoirs: {sum(bool(item['included']) for item in plan)}")
    print(f"Excluded reservoirs: {sum(not bool(item['included']) for item in plan)}")
    print(f"Estimated historical date requests: {total}")


def reconcile_csv(path: Path, new_records: list[dict[str, object]]) -> pd.DataFrame:
    """Preserve valid unrelated rows and replace matching reservoir/date keys."""
    if path.exists():
        existing = pd.read_csv(path, dtype=str)
        existing = existing.reindex(columns=OUTPUT_COLUMNS)
        existing = existing.dropna(subset=["reservoir_name", "requested_date"])
        valid_keys = (
            existing["reservoir_name"].astype("string").str.strip().ne("")
            & existing["requested_date"].map(
                lambda value: bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(value)))
            )
        )
        valid_observations = existing["quality_flag"].isin(QUALITY_FLAGS)
        retryable_failures = existing["collection_status"].isin(
            {"request_failed", "parse_failed"}
        )
        existing = existing[
            valid_keys & (valid_observations | retryable_failures)
        ].copy()
    else:
        existing = pd.DataFrame(columns=OUTPUT_COLUMNS)

    combined = pd.concat([existing, pd.DataFrame(new_records, columns=OUTPUT_COLUMNS)], ignore_index=True)
    combined = combined.drop_duplicates(subset=["reservoir_name", "requested_date"], keep="last")
    return combined.reindex(columns=OUTPUT_COLUMNS).sort_values(
        ["requested_date", "reservoir_name"], kind="stable"
    ).reset_index(drop=True)


def successful_existing_keys(path: Path) -> set[tuple[str, str]]:
    """Return completed date keys so reruns retry failures without repeating successes."""
    if not path.exists():
        return set()
    existing = pd.read_csv(path, dtype=str)
    required = {"reservoir_name", "requested_date", "collection_status"}
    if not required.issubset(existing.columns):
        return set()
    completed = existing[existing["collection_status"].str.casefold() == "success"]
    return {
        (str(row.reservoir_name), str(row.requested_date))
        for row in completed[["reservoir_name", "requested_date"]].itertuples(index=False)
        if pd.notna(row.reservoir_name) and pd.notna(row.requested_date)
    }


def read_recovery_rows(path: Path, *, lai_chau_only: bool) -> pd.DataFrame:
    """Read a compatible recovery CSV without discarding malformed contents."""
    if not path.exists():
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    try:
        existing = pd.read_csv(path, dtype=str)
    except (OSError, pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeError) as exc:
        raise ValueError(f"Cannot read recovery CSV {path}: {exc}") from exc
    missing = set(OUTPUT_COLUMNS) - set(existing.columns)
    unexpected = set(existing.columns) - set(OUTPUT_COLUMNS)
    if missing or unexpected:
        raise ValueError(
            f"Invalid recovery CSV schema at {path}; missing columns={sorted(missing)}, "
            f"unexpected columns={sorted(unexpected)}. Expected the EVN historical CSV columns."
        )
    existing = existing[OUTPUT_COLUMNS].copy()
    if existing["reservoir_name"].isna().any() or existing["requested_date"].isna().any():
        raise ValueError(f"Recovery CSV {path} contains rows without a reservoir/date key.")
    if existing.duplicated(["reservoir_name", "requested_date"]).any():
        raise ValueError(f"Recovery CSV {path} contains duplicate reservoir/date keys.")
    if lai_chau_only and (existing["reservoir_name"] != RECOVERY_RESERVOIR).any():
        raise ValueError(
            f"Recovery output {path} contains records outside {RECOVERY_RESERVOIR}."
        )
    if not lai_chau_only:
        existing = existing[existing["reservoir_name"] == RECOVERY_RESERVOIR].copy()
    if not existing.empty:
        invalid_dates = existing["requested_date"].map(
            lambda value: not isinstance(value, str)
            or re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is None
            or _invalid_iso_date(value)
        )
        if invalid_dates.any():
            raise ValueError(f"Recovery CSV {path} contains invalid requested_date values.")
        valid_successes = (
            existing["collection_status"].eq("success")
            & existing["quality_flag"].isin(QUALITY_FLAGS)
        )
        valid_failures = existing["collection_status"].isin(
            {"request_failed", "parse_failed"}
        )
        if not (valid_successes | valid_failures).all():
            raise ValueError(f"Recovery CSV {path} contains invalid collection status/quality values.")
    return existing


def _invalid_iso_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
    except ValueError:
        return True
    return False


def recovery_seed(path: Path, *, lai_chau_only: bool = False) -> pd.DataFrame:
    """Read Lai Châu rows from a validated source or isolated recovery CSV."""
    return read_recovery_rows(path, lai_chau_only=lai_chau_only)


def prepare_recovery_seed(source_path: Path, output_path: Path) -> pd.DataFrame:
    """Validate both inputs and combine them before any recovery output is written."""
    source_rows = recovery_seed(source_path)
    output_rows = recovery_seed(output_path, lai_chau_only=True)
    seed = pd.concat([source_rows, output_rows], ignore_index=True)
    return seed.drop_duplicates(
        subset=["reservoir_name", "requested_date"], keep="last"
    ).reindex(columns=OUTPUT_COLUMNS)


def ensure_safe_recovery_output(path: Path) -> None:
    """Reject established CSV targets, including path, symlink, and file aliases."""
    resolved = path.resolve()
    same_file = any(
        path.exists() and protected.exists() and os.path.samefile(path, protected)
        for protected in MAIN_OUTPUT_PATHS
    )
    if resolved in MAIN_OUTPUT_PATHS or same_file:
        raise ValueError("recovery output must be separate from both established historical CSVs")


def recovery_completed_keys(
    frame: pd.DataFrame, *, refresh_stale: bool
) -> set[tuple[str, str]]:
    """Find resumable recovery keys; stale successes are eligible only on request."""
    if frame.empty:
        return set()
    completed = frame[frame["collection_status"].astype("string").str.casefold() == "success"]
    if refresh_stale:
        completed = completed[completed["quality_flag"] != "stale_previous_observation"]
    return {
        (str(row.reservoir_name), str(row.requested_date))
        for row in completed[["reservoir_name", "requested_date"]].itertuples(index=False)
        if pd.notna(row.reservoir_name) and pd.notna(row.requested_date)
    }


def reconcile_recovery_csv(
    path: Path, new_records: list[dict[str, object]]
) -> pd.DataFrame:
    """Merge attempts while retaining a prior valid stale row on failed refresh."""
    existing = recovery_seed(path, lai_chau_only=True)
    if new_records and not existing.empty:
        previous = existing.set_index(["reservoir_name", "requested_date"], drop=False)
        kept = []
        for record in new_records:
            key = (record.get("reservoir_name"), record.get("requested_date"))
            old = previous.loc[key] if key in previous.index else None
            failed = record.get("collection_status") in {"request_failed", "parse_failed"}
            if (
                old is not None
                and failed
                and old["collection_status"] == "success"
                and old["quality_flag"] == "stale_previous_observation"
            ):
                continue
            kept.append(record)
        new_records = kept
    return reconcile_csv(path, new_records)


def save_csv_atomically(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8-sig", newline="", suffix=".tmp", dir=path.parent, delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
            frame.to_csv(temporary, index=False)
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def print_validation(
    frame: pd.DataFrame,
    run_records: list[dict[str, object]],
    request_failures: list[tuple[str, str, str]],
    parsing_failures: list[tuple[str, str, str]],
    start: date,
    end: date,
    skipped_completed: int,
    elapsed_seconds: float,
) -> None:
    print("\nEVN historical collection validation")
    print("Full-CSV metrics:")
    print(f"  Total rows: {len(frame)}")
    print(f"  Unique reservoirs: {frame['reservoir_name'].nunique()}")
    represented_dates = pd.to_datetime(frame["requested_date"], errors="coerce")
    represented_dates = represented_dates.dropna()
    if represented_dates.empty:
        csv_date_range = "none"
    else:
        csv_date_range = (
            f"{represented_dates.min().date().isoformat()} through "
            f"{represented_dates.max().date().isoformat()}"
        )
    print(f"  Requested-date range represented in CSV: {csv_date_range}")
    print(
        "  Duplicate (reservoir_name, requested_date) keys: "
        f"{frame.duplicated(['reservoir_name', 'requested_date']).sum()}"
    )
    print("  Quality-flag counts across full CSV:")
    for flag, count in frame["quality_flag"].value_counts(dropna=False).items():
        print(f"    {flag if pd.notna(flag) else 'unset'}: {count}")
    print("  Collection-status counts across full CSV:")
    for status, count in frame["collection_status"].value_counts(dropna=False).items():
        print(f"    {status if pd.notna(status) else 'unset'}: {count}")

    print("Current-run metrics:")
    print(f"  Configured run date range: {start.isoformat()} through {end.isoformat()}")
    print(f"  Dates attempted: {len(run_records)}")
    denominator = len(run_records)
    for flag in (
        "exact_date",
        "stale_previous_observation",
        "future_observation",
        "ambiguous_year",
        "missing",
    ):
        count = sum(record["quality_flag"] == flag for record in run_records)
        percentage = 100.0 * count / denominator if denominator else 0.0
        print(f"  {flag}: {count} ({percentage:.1f}%)")
    successful_results = sum(
        record["collection_status"] == "success"
        and record["observation_timestamp"] is not None
        for record in run_records
    )
    print(f"  Successful timestamped results: {successful_results}")
    print(f"  Request failures: {len(request_failures)}")
    for name, requested, error in request_failures:
        print(f"  REQUEST {name} {requested}: {error}")
    print(f"  Parsing failures: {len(parsing_failures)}")
    for name, requested, error in parsing_failures:
        print(f"  PARSE {name} {requested}: {error}")
    print(f"  Skipped completed records: {skipped_completed}")
    print(f"  Elapsed time: {elapsed_seconds:.1f}s")
    stale = [record for record in run_records if record["quality_flag"] == "stale_previous_observation"]
    print("Current-run stale cases:")
    if stale:
        for record in stale:
            print(
                f"  {record['reservoir_name']} requested {record['requested_date']}"
                f" -> observation {record['observation_timestamp']}"
            )
    else:
        print("  None")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = parse_args()
    recovery_frame: pd.DataFrame | None = None
    if args.recovery_lai_chau and not args.dry_run:
        ensure_safe_recovery_output(args.output)
        recovery_frame = prepare_recovery_seed(OUTPUT_PATH, args.output)
        # Validation of both existing CSVs completes before this first write.
        save_csv_atomically(args.output, recovery_frame)
    with requests.Session() as session:
        session.headers.update({"User-Agent": "Mozilla/5.0"})
        options = fetch_reservoir_options(
            session,
            timeout=args.timeout,
            retry_count=args.retry_count,
            retry_backoff=args.retry_backoff,
        )
        if args.reservoirs:
            selected = dict(resolve_reservoir_names(args.reservoirs, options))
            options = {
                name: reservoir_id
                for name, reservoir_id in options.items()
                if name in selected
            }

        plan = build_collection_plan(options, args.end_date, args.start_date)
        if args.dry_run:
            print_collection_plan(plan, args.end_date)
            return

        included = [item for item in plan if item["included"]]
        if not included:
            raise ValueError("No configured reservoirs are eligible for collection.")

        if args.recovery_lai_chau:
            assert recovery_frame is not None
            completed_keys = recovery_completed_keys(
                recovery_frame, refresh_stale=args.refresh_stale
            )
        else:
            completed_keys = successful_existing_keys(args.output)
        run_records = []
        pending_records = []
        request_failures = []
        parsing_failures = []
        counts: Counter[str] = Counter()
        started = time.monotonic()
        last_progress_at = 0

        def report_progress(reservoirs_processed: int, *, force: bool = False) -> None:
            nonlocal last_progress_at
            if not force and counts["dates_attempted"] - last_progress_at < 100:
                return
            last_progress_at = counts["dates_attempted"]
            elapsed = time.monotonic() - started
            print(
                "Progress: "
                f"reservoirs {reservoirs_processed}/{len(included)}; "
                f"dates attempted {counts['dates_attempted']}; "
                f"successes {counts['successes']}; missing {counts['missing']}; "
                f"stale {counts['stale_previous_observation']}; "
                f"future {counts['future_observation']}; "
                f"request failures {counts['request_failed']}; "
                f"parse failures {counts['parse_failed']}; "
                f"skipped completed {counts['skipped_completed']}; "
                f"elapsed {elapsed:.1f}s"
            )

        for reservoir_index, item in enumerate(included, start=1):
            name = str(item["reservoir_name"])
            reservoir_id = str(item["evn_id"])
            start_date = item["collection_start_date"]
            assert isinstance(start_date, date)
            for requested_date in date_range(start_date, args.end_date):
                key = (name, requested_date.isoformat())
                if key in completed_keys:
                    counts["skipped_completed"] += 1
                    continue
                record, request_error, parsing_error = collect_one(
                    session,
                    name,
                    reservoir_id,
                    requested_date,
                    timeout=args.timeout,
                    retry_count=args.retry_count,
                    retry_backoff=args.retry_backoff,
                    diagnostics_dir=args.diagnostics_dir,
                )
                run_records.append(record)
                pending_records.append(record)
                counts["dates_attempted"] += 1
                if record["collection_status"] == "success":
                    if record["quality_flag"] == "missing":
                        counts["missing"] += 1
                    else:
                        counts["successes"] += 1
                        counts[str(record["quality_flag"])] += 1
                    completed_keys.add(key)
                if request_error:
                    request_failures.append((name, requested_date.isoformat(), request_error))
                    counts["request_failed"] += 1
                if parsing_error:
                    parsing_failures.append((name, requested_date.isoformat(), parsing_error))
                    counts["parse_failed"] += 1
                if len(pending_records) >= args.checkpoint_every:
                    checkpoint = (
                        reconcile_recovery_csv(args.output, pending_records)
                        if args.recovery_lai_chau
                        else reconcile_csv(args.output, pending_records)
                    )
                    save_csv_atomically(args.output, checkpoint)
                    pending_records.clear()
                report_progress(reservoir_index)
                # Keep consecutive public date requests modest and predictable.
                if args.request_delay:
                    time.sleep(args.request_delay)
            report_progress(reservoir_index, force=True)

    if pending_records:
        frame = (
            reconcile_recovery_csv(args.output, pending_records)
            if args.recovery_lai_chau
            else reconcile_csv(args.output, pending_records)
        )
        save_csv_atomically(args.output, frame)
    elif args.output.exists():
        frame = (
            reconcile_recovery_csv(args.output, [])
            if args.recovery_lai_chau
            else reconcile_csv(args.output, [])
        )
    else:
        frame = pd.DataFrame(columns=OUTPUT_COLUMNS)
    print_validation(
        frame,
        run_records,
        request_failures,
        parsing_failures,
        min(item["collection_start_date"] for item in included),
        args.end_date,
        counts["skipped_completed"],
        time.monotonic() - started,
    )
    print(f"CSV saved: {args.output}")


if __name__ == "__main__":
    main()
