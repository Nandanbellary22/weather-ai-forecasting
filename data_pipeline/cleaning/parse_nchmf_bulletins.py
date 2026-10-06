from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Optional

import pandas as pd


# =============================================================================
# PATHS
# =============================================================================

INDEX_INPUT = Path("data/raw/nchmf/index.csv")
WARNINGS_OUTPUT = Path("data/processed/nchmf_flood_warnings.csv")
FORECASTS_OUTPUT = Path("data/processed/nchmf_river_forecasts.csv")


# =============================================================================
# TEXT NORMALIZATION
# =============================================================================

def normalize_unicode(text: str) -> str:
    if text is None:
        return ""

    text = str(text)
    text = unicodedata.normalize("NFC", text)

    text = text.replace("\xa0", " ")
    text = text.replace("\u200b", "")
    text = text.replace("\ufeff", "")

    text = text.replace("\r\n", "\n").replace("\r", "\n")

    return "\n".join(line.rstrip() for line in text.split("\n"))


def compact_text(text: str) -> str:
    text = normalize_unicode(text)
    return re.sub(r"\s+", " ", text).strip()


def clean_value(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None

    value = re.sub(r"\s+", " ", str(value)).strip()

    if not value:
        return None

    return value


def parse_decimal(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None

    value = str(value).strip().replace(" ", "").replace(",", ".")

    try:
        return float(value)
    except ValueError:
        return None


# =============================================================================
# BULLETIN ID
# =============================================================================

def extract_bulletin_id(text: str) -> Optional[str]:
    normalized = normalize_unicode(text)

    patterns = [
        r"\b((?:C|D)BLU_[0-9]+/[0-9]+h[0-9]*/DBQG)\b",
        r"\b((?:C|D)BLU_[0-9]+/[0-9]+h/DBQG)\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if match:
            return clean_value(match.group(1))

    return None


# =============================================================================
# BULLETIN DATETIME
# =============================================================================

def extract_bulletin_datetime(
    row: pd.Series,
    text: str,
) -> Optional[pd.Timestamp]:
    """
    The archive datetime is NOT necessarily the actual bulletin issue time.

    Prefer:
        Hà Nội, ngày DD tháng MM năm YYYY
        Tin phát lúc: HHhMM

    Fall back to the archive/index datetime only if the source text
    does not contain enough information.
    """

    normalized = normalize_unicode(text)
    compact = compact_text(text)

    date_match = re.search(
        r"Hà Nội,\s*ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})",
        compact,
        flags=re.IGNORECASE,
    )

    if date_match:
        year = int(date_match.group(3))
        month = int(date_match.group(2))
        day = int(date_match.group(1))

        time_match = re.search(
            r"Tin phát lúc\s*:\s*(\d{1,2})h(?:([0-5]\d))?",
            compact,
            flags=re.IGNORECASE,
        )

        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2) or 0)

            try:
                return pd.Timestamp(
                    year=year,
                    month=month,
                    day=day,
                    hour=hour,
                    minute=minute,
                )
            except ValueError:
                pass

        # If the issue time isn't present, try the bulletin ID.
        id_match = re.search(
            r"\b(?:C|D)BLU_[0-9]+/([0-9]{1,2})h([0-5]\d)/DBQG\b",
            normalized,
            flags=re.IGNORECASE,
        )

        if id_match:
            hour = int(id_match.group(1))
            minute = int(id_match.group(2))

            try:
                return pd.Timestamp(
                    year=year,
                    month=month,
                    day=day,
                    hour=hour,
                    minute=minute,
                )
            except ValueError:
                pass

        try:
            return pd.Timestamp(
                year=year,
                month=month,
                day=day,
            )
        except ValueError:
            pass

    if "bulletin_datetime" in row.index:
        value = pd.to_datetime(
            row.get("bulletin_datetime"),
            errors="coerce",
        )

        if not pd.isna(value):
            return value

    return None


# =============================================================================
# STATION
# =============================================================================

def extract_station(text: str) -> Optional[str]:
    """
    Extract a complete station name.

    Examples:
        trạm Tà Lài
        trạm Kim Long
        trạm Tân Châu
        trạm Châu Đốc

    We stop at known sentence/verb boundaries rather than whitespace.
    """

    normalized = normalize_unicode(text)

    patterns = [
        r"\btrạm\s+([A-ZÀ-ỸĐ][A-Za-zÀ-ỹĐđ]*(?:\s+[A-ZÀ-ỸĐ][A-Za-zÀ-ỹĐđ]*){0,5})(?=\s+(?:đang|ở|lúc|mực|dao|biến|và|có|trên|đạt|xuống|lên)\b|[.,;:\n])",
        r"\btrạm\s+([A-ZÀ-ỸĐ][A-Za-zÀ-ỹĐđ]*(?:\s+[A-ZÀ-ỸĐ][A-Za-zÀ-ỹĐđ]*){0,5})(?=\s|[.,;:\n])",
    ]

    candidates = []

    for pattern in patterns:
        for match in re.finditer(
            pattern,
            normalized,
            flags=re.IGNORECASE,
        ):
            station = clean_value(match.group(1))

            if station:
                station = station.strip(" ,.;:-")
                candidates.append(station)

    if not candidates:
        return None

    # Prefer known/common multi-word station names.
    for station in candidates:
        if len(station.split()) >= 2:
            return station

    return candidates[0]


# =============================================================================
# RIVER
# =============================================================================

def extract_river(
    text: str,
    station: Optional[str],
) -> Optional[str]:
    """
    Extract the river associated with the station.

    The key rule is:

        sông <RIVER> ... tại trạm <STATION>

    rather than simply taking everything after "sông".

    This prevents values such as:

        ĐỒNG NAI 1. Hiện trạng Mực nước...

    from being incorrectly stored as the river.
    """

    normalized = normalize_unicode(text)

    if station:
        escaped_station = re.escape(station)

        patterns = [
            rf"\bsông\s+(.{{1,100}}?)\s+tại\s+trạm\s+{escaped_station}\b",
            rf"\bsông\s+(.{{1,100}}?)\s+ở\s+trạm\s+{escaped_station}\b",
            rf"\bsông\s+(.{{1,100}}?)\s*,?\s*trạm\s+{escaped_station}\b",
        ]

        for pattern in patterns:
            matches = list(
                re.finditer(
                    pattern,
                    normalized,
                    flags=re.IGNORECASE | re.DOTALL,
                )
            )

            if matches:
                river = clean_value(matches[-1].group(1))

                if river:
                    river = re.sub(
                        r"\s*\([^)]*\)\s*$",
                        "",
                        river,
                    )
                    river = river.strip(" ,.;:-")

                    if river:
                        return river

    # Fallback: use the bulletin title if it contains a single river.
    title = ""

    # This fallback is deliberately conservative.
    compact = compact_text(text)

    title_match = re.search(
        r"TIN\s+(?:CẢNH\s+BÁO\s+)?LŨ\s+TRÊN\s+SÔNG\s+(.+?)(?=\s*\(|\s*\d{1,2}/\d{1,2}/|\s*$)",
        compact,
        flags=re.IGNORECASE,
    )

    if title_match:
        river = clean_value(title_match.group(1))

        if river:
            river = re.sub(
                r"\s+và\s+sông\s+.+$",
                "",
                river,
                flags=re.IGNORECASE,
            )

            return river.strip(" ,.;:-")

    return None


# =============================================================================
# OBSERVED WATER LEVEL
# =============================================================================

def extract_observed_measurement(
    text: str,
    bulletin_datetime: Optional[pd.Timestamp],
) -> tuple[Optional[pd.Timestamp], Optional[float]]:
    compact = compact_text(text)

    patterns = [
        r"Lúc\s+(\d{1,2})h(?:([0-5]\d))?\s+ngày\s+(\d{1,2})/(\d{1,2})"
        r".{0,700}?"
        r"mực nước.{0,300}?"
        r"(?:là|đạt|ở mức)\s*"
        r"([0-9]+(?:[.,][0-9]+)?)\s*m",

        r"Lúc\s+(\d{1,2})h(?:([0-5]\d))?\s+ngày\s+(\d{1,2})/(\d{1,2})"
        r".{0,700}?"
        r"mực nước.{0,300}?"
        r"([0-9]+(?:[.,][0-9]+)?)\s*m",
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            compact,
            flags=re.IGNORECASE,
        )

        if not match:
            continue

        try:
            hour = int(match.group(1))
            minute = int(match.group(2) or 0)
            day = int(match.group(3))
            month = int(match.group(4))
            water_level = parse_decimal(match.group(5))

            if water_level is None:
                continue

            if bulletin_datetime is not None:
                year = int(bulletin_datetime.year)
            else:
                year = pd.Timestamp.now().year

            observed_time = pd.Timestamp(
                year=year,
                month=month,
                day=day,
                hour=hour,
                minute=minute,
            )

            return observed_time, water_level

        except (ValueError, TypeError):
            continue

    # Fallback numeric water level.
    fallback_patterns = [
        r"mực nước.{0,400}?(?:là|đạt|ở mức)\s*"
        r"([0-9]+(?:[.,][0-9]+)?)\s*m",
        r"mực nước.{0,400}?"
        r"([0-9]+(?:[.,][0-9]+)?)\s*m",
    ]

    for pattern in fallback_patterns:
        match = re.search(
            pattern,
            compact,
            flags=re.IGNORECASE,
        )

        if match:
            value = parse_decimal(match.group(1))

            if value is not None:
                return None, value

    return None, None


# =============================================================================
# THRESHOLD
# =============================================================================

def extract_threshold_relation(
    text: str,
) -> tuple[Optional[str], Optional[str], Optional[float]]:
    compact = compact_text(text)

    patterns = [
        r"\b(trên|dưới)\s+"
        r"(?:mức\s+)?"
        r"(?:báo động\s*)?"
        r"\(?(BĐ)\)?\s*([123])\s*"
        r"([0-9]+(?:[.,][0-9]+)?)\s*m",

        r"\b(trên|dưới)\s+"
        r"báo động\s*"
        r"\(?(BĐ)\)?\s*([123])\s*"
        r"([0-9]+(?:[.,][0-9]+)?)\s*m",
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            compact,
            flags=re.IGNORECASE,
        )

        if match:
            relation = match.group(1).lower()
            code = f"{match.group(2).upper()}{match.group(3)}"
            difference = parse_decimal(match.group(4))

            return code, relation, difference

    # Threshold without difference.
    match = re.search(
        r"\b(trên|dưới)\s+"
        r"(?:mức\s+)?"
        r"(?:báo động\s*)?"
        r"\(?(BĐ)\)?\s*([123])\b",
        compact,
        flags=re.IGNORECASE,
    )

    if match:
        return (
            f"{match.group(2).upper()}{match.group(3)}",
            match.group(1).lower(),
            None,
        )

    match = re.search(
        r"ở\s+mức\s+\(?(BĐ)\)?\s*([123])",
        compact,
        flags=re.IGNORECASE,
    )

    if match:
        return (
            f"{match.group(1).upper()}{match.group(2)}",
            "at",
            None,
        )

    return None, None, None


# =============================================================================
# RISK LEVEL
# =============================================================================

def extract_risk_level(text: str) -> Optional[int]:
    compact = compact_text(text)

    match = re.search(
        r"rủi ro thiên tai do lũ\s*:\s*Cấp\s*([123])",
        compact,
        flags=re.IGNORECASE,
    )

    if match:
        return int(match.group(1))

    match = re.search(
        r"rủi ro thiên tai do lũ\s*:\s*Cấp\s*([123])\s*[-–]\s*([123])",
        compact,
        flags=re.IGNORECASE,
    )

    if match:
        return int(match.group(1))

    return None


# =============================================================================
# FORECAST PERIOD
# =============================================================================

def extract_forecast_period(text: str) -> Optional[str]:
    compact = compact_text(text)

    match = re.search(
        r"Trong\s+(\d+)\s+giờ\s+tới",
        compact,
        flags=re.IGNORECASE,
    )

    if match:
        return f"{match.group(1)} hours"

    match = re.search(
        r"Từ\s+nay\s*\([^)]*\)\s*đến\s*([0-9]{1,2}/[0-9]{1,2})",
        compact,
        flags=re.IGNORECASE,
    )

    if match:
        return match.group(0)

    return None


# =============================================================================
# FORECAST THRESHOLDS
# =============================================================================

def extract_forecast_thresholds(text: str) -> Optional[str]:
    compact = compact_text(text)

    matches = []

    patterns = [
        r"\bBĐ[123]\s*[-–]\s*BĐ[123]\b",
        r"(?:trên|dưới|ở mức|dao động ở mức)\s+"
        r"(?:mức\s+)?"
        r"(?:báo động\s*)?"
        r"\(?(?:BĐ)\)?\s*[123]",
    ]

    for pattern in patterns:
        for match in re.finditer(
            pattern,
            compact,
            flags=re.IGNORECASE,
        ):
            value = clean_value(match.group(0))

            if value and value not in matches:
                matches.append(value)

    return "; ".join(matches) if matches else None


# =============================================================================
# AFFECTED AREA
# =============================================================================

def extract_affected_area(text: str) -> Optional[str]:
    compact = compact_text(text)

    patterns = [
        r"Nguy cơ xảy ra ngập lụt\s+(.*?)(?=\s+3\.\s*Cảnh báo)",
        r"Nguy cơ xảy ra ngập lụt\s+(.*?)(?=\s+4\.\s*Cảnh báo)",
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            compact,
            flags=re.IGNORECASE,
        )

        if match:
            value = clean_value(match.group(1))

            if value:
                return value

    return None


# =============================================================================
# IMPACT
# =============================================================================

def extract_impact(text: str) -> Optional[str]:
    compact = compact_text(text)

    match = re.search(
        r"4\.\s*Cảnh báo tác động của lũ\s*:\s*(.*?)(?=\s+Tin phát lúc:)",
        compact,
        flags=re.IGNORECASE,
    )

    if match:
        return clean_value(match.group(1))

    return None


# =============================================================================
# APPENDIX PARSER
# =============================================================================

def parse_appendix_forecasts(
    text: str,
    bulletin_datetime: Optional[pd.Timestamp],
    bulletin_id: Optional[str],
) -> list[dict]:
    """
    Parse the long hydrological forecast table.

    This parser is intentionally conservative.

    It only accepts rows that look like actual table rows and preserves
    every numeric token in its raw form.

    No unit conversion is performed.
    """

    normalized = normalize_unicode(text)

    # Find the appendix/table region.
    markers = [
        r"Bảng\s+mực\s+nước,\s*lưu\s*lượng\s*thực\s*đo\s*và\s*dự\s*báo",
        r"Bảng\s+mực\s*nước.*?dự\s*báo\s*các\s*trạm",
    ]

    start = None

    for marker in markers:
        match = re.search(
            marker,
            normalized,
            flags=re.IGNORECASE,
        )

        if match:
            start = match.end()
            break

    if start is None:
        return []

    appendix = normalized[start:]

    # Remove obvious footer/signature.
    appendix = re.split(
        r"\n\s*(?:PHÓ\s+TRƯỞNG|Nơi nhận|Tin phát lúc:)",
        appendix,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]

    lines = [
        re.sub(r"\s+", " ", line).strip()
        for line in appendix.splitlines()
        if line.strip()
    ]

    records = []

    # Known river names seen in NCHMF bulletins and the appendix.
    river_names = [
        "Đà",
        "Thao",
        "Lô",
        "Cầu",
        "Thương",
        "Lục Nam",
        "Hồng",
        "Thái Bình",
        "Mã",
        "Cả",
        "La",
        "Giang",
        "Hương",
        "Thu Bồn",
        "Trà Khúc",
        "Kôn",
        "Đà Rằng",
        "Đăkbla",
        "Krông Ana",
        "Đồng Nai",
        "Bé",
        "Tiền",
        "Hậu",
    ]

    river_pattern = "|".join(
        re.escape(river)
        for river in sorted(
            river_names,
            key=len,
            reverse=True,
        )
    )

    # A valid row normally starts with a known river name.
    row_pattern = re.compile(
        rf"^(?P<river>{river_pattern})\s+"
        rf"(?P<rest>.+?)\s+"
        rf"(?P<numbers>"
        rf"[-+]?\d+(?:[.,]\d+)?"
        rf"(?:\s+[-+]?\d+(?:[.,]\d+)?)+"
        rf")$",
        flags=re.IGNORECASE,
    )

    for line in lines:
        match = row_pattern.match(line)

        if not match:
            continue

        river = clean_value(match.group("river"))
        rest = clean_value(match.group("rest"))
        numbers = re.findall(
            r"[-+]?\d+(?:[.,]\d+)?",
            match.group("numbers"),
        )

        if not river or not rest or len(numbers) < 3:
            continue

        # Station is normally the text immediately before the first number.
        station = rest.strip()

        # Remove common category/header fragments.
        station = re.sub(
            r"\b(?:mực nước|lưu lượng|thực đo|dự báo)\b.*$",
            "",
            station,
            flags=re.IGNORECASE,
        ).strip()

        if not station:
            continue

        records.append(
            {
                "bulletin_datetime": bulletin_datetime,
                "bulletin_id": bulletin_id,
                "river": river,
                "station": station,
                "raw_station_text": rest,
                "observed_value_1_raw": numbers[0],
                "observed_value_2_raw": numbers[1] if len(numbers) > 1 else None,
                "observed_value_3_raw": numbers[2] if len(numbers) > 2 else None,
                "forecast_value_1_raw": numbers[3] if len(numbers) > 3 else None,
                "forecast_value_2_raw": numbers[4] if len(numbers) > 4 else None,
                "forecast_value_3_raw": numbers[5] if len(numbers) > 5 else None,
                "all_numeric_values_raw": "|".join(numbers),
                "source_text": line,
            }
        )

    return records


# =============================================================================
# MAIN BULLETIN PARSER
# =============================================================================

def parse_bulletin(row: pd.Series) -> tuple[dict, list[dict]]:
    text = normalize_unicode(row.get("full_text", ""))

    bulletin_datetime = extract_bulletin_datetime(
        row,
        text,
    )

    bulletin_id = extract_bulletin_id(text)

    station = extract_station(text)

    river = extract_river(
        text,
        station,
    )

    observed_time, observed_water_level = extract_observed_measurement(
        text,
        bulletin_datetime,
    )

    threshold_code, threshold_relation, threshold_difference = (
        extract_threshold_relation(text)
    )

    risk_level = extract_risk_level(text)
    forecast_period = extract_forecast_period(text)
    forecast_thresholds = extract_forecast_thresholds(text)
    affected_area = extract_affected_area(text)
    impact = extract_impact(text)

    warning_record = {
        "bulletin_datetime": bulletin_datetime,
        "bulletin_id": bulletin_id,
        "bulletin_title": clean_value(row.get("bulletin_title")),
        "bulletin_url": clean_value(row.get("bulletin_url")),
        "pdf_url": clean_value(row.get("pdf_url")),
        "river": river,
        "station": station,
        "observed_time": observed_time,
        "observed_water_level_m": observed_water_level,
        "threshold_code": threshold_code,
        "threshold_relation": threshold_relation,
        "threshold_difference_m": threshold_difference,
        "risk_level": risk_level,
        "forecast_period": forecast_period,
        "forecast_thresholds": forecast_thresholds,
        "affected_area": affected_area,
        "impact": impact,
        "source_text": text,
        "source_pdf": clean_value(row.get("pdf_path")),
        "source": "NCHMF",
        "collected_at": clean_value(row.get("collected_at")),
    }

    appendix_records = parse_appendix_forecasts(
        text,
        bulletin_datetime,
        bulletin_id,
    )

    for record in appendix_records:
        record.update(
            {
                "bulletin_title": clean_value(row.get("bulletin_title")),
                "bulletin_url": clean_value(row.get("bulletin_url")),
                "pdf_url": clean_value(row.get("pdf_url")),
                "source_pdf": clean_value(row.get("pdf_path")),
                "source": "NCHMF",
            }
        )

    return warning_record, appendix_records


# =============================================================================
# VALIDATION
# =============================================================================

def validate_warning_output(df: pd.DataFrame) -> None:
    if df.empty:
        raise RuntimeError("NCHMF warning output is empty.")

    required_columns = [
        "bulletin_datetime",
        "bulletin_id",
        "river",
        "station",
        "observed_time",
        "observed_water_level_m",
        "threshold_code",
        "threshold_relation",
        "threshold_difference_m",
        "risk_level",
    ]

    missing = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing:
        raise RuntimeError(
            f"Missing required warning columns: {missing}"
        )

    numeric_columns = [
        "observed_water_level_m",
        "threshold_difference_m",
        "risk_level",
    ]

    for column in numeric_columns:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    invalid_risk = df[
        df["risk_level"].notna()
        & ~df["risk_level"].isin([1, 2, 3])
    ]

    if not invalid_risk.empty:
        raise RuntimeError(
            f"Invalid risk levels detected: "
            f"{invalid_risk['risk_level'].unique()}"
        )


# =============================================================================
# MAIN
# =============================================================================

def main() -> None:
    print("=" * 80)
    print("NCHMF FLOOD BULLETIN STRUCTURED PARSER")
    print("=" * 80)

    if not INDEX_INPUT.exists():
        raise FileNotFoundError(
            f"Input file not found: {INDEX_INPUT}"
        )

    df = pd.read_csv(
        INDEX_INPUT,
        dtype=str,
        keep_default_na=False,
    )

    print(f"Input rows: {len(df)}")

    warning_records = []
    forecast_records = []

    successful_source_texts = 0
    parser_failures = 0

    for _, row in df.iterrows():
        text = row.get("full_text", "")

        if not text or not str(text).strip():
            continue

        successful_source_texts += 1

        try:
            warning, appendix = parse_bulletin(row)

            warning_records.append(warning)
            forecast_records.extend(appendix)

        except Exception as exc:
            parser_failures += 1

            print(
                f"[PARSER ERROR] "
                f"{row.get('bulletin_title', '')}: {exc}"
            )

    warnings_df = pd.DataFrame(warning_records)
    forecasts_df = pd.DataFrame(forecast_records)

    # -------------------------------------------------------------------------
    # WARNING OUTPUT
    # -------------------------------------------------------------------------

    if not warnings_df.empty:
        warnings_df["bulletin_datetime"] = pd.to_datetime(
            warnings_df["bulletin_datetime"],
            errors="coerce",
        )

        warnings_df["observed_time"] = pd.to_datetime(
            warnings_df["observed_time"],
            errors="coerce",
        )

        validate_warning_output(warnings_df)

        warnings_df = warnings_df.sort_values(
            ["bulletin_datetime", "river", "station"],
            na_position="last",
        ).reset_index(drop=True)

    # -------------------------------------------------------------------------
    # FORECAST OUTPUT
    # -------------------------------------------------------------------------

    if not forecasts_df.empty:
        forecasts_df["bulletin_datetime"] = pd.to_datetime(
            forecasts_df["bulletin_datetime"],
            errors="coerce",
        )

        forecasts_df = forecasts_df.sort_values(
            ["bulletin_datetime", "river", "station"],
            na_position="last",
        ).reset_index(drop=True)

    # -------------------------------------------------------------------------
    # SAVE
    # -------------------------------------------------------------------------

    WARNINGS_OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    warnings_df.to_csv(
        WARNINGS_OUTPUT,
        index=False,
        encoding="utf-8-sig",
    )

    forecasts_df.to_csv(
        FORECASTS_OUTPUT,
        index=False,
        encoding="utf-8-sig",
    )

    # -------------------------------------------------------------------------
    # SUMMARY
    # -------------------------------------------------------------------------

    print()
    print("=" * 80)
    print("PARSING COMPLETE")
    print("=" * 80)

    print(f"Input bulletins          : {len(df)}")
    print(f"Successful source texts  : {successful_source_texts}")
    print(f"Parser successes         : {len(warning_records)}")
    print(f"Parser failures          : {parser_failures}")

    print()
    print("Flood warning records")
    print("-" * 80)
    print(f"Rows                     : {len(warnings_df)}")

    if not warnings_df.empty:
        print(
            f"With river              : "
            f"{warnings_df['river'].notna().sum()}"
        )

        print(
            f"With station            : "
            f"{warnings_df['station'].notna().sum()}"
        )

        print(
            f"With numeric water level: "
            f"{warnings_df['observed_water_level_m'].notna().sum()}"
        )

        print(
            f"With threshold relation : "
            f"{warnings_df['threshold_relation'].notna().sum()}"
        )

        print()
        print("Unique rivers:")
        print(
            warnings_df["river"]
            .dropna()
            .value_counts()
            .to_string()
        )

        print()
        print("Station examples:")
        print(
            warnings_df[
                [
                    "bulletin_datetime",
                    "bulletin_id",
                    "river",
                    "station",
                    "observed_time",
                    "observed_water_level_m",
                    "threshold_code",
                    "threshold_relation",
                    "threshold_difference_m",
                ]
            ]
            .head(10)
            .to_string(index=False)
        )

    print()
    print("Detailed appendix forecast records")
    print("-" * 80)
    print(f"Rows                     : {len(forecasts_df)}")

    if not forecasts_df.empty:
        print(
            f"Unique stations         : "
            f"{forecasts_df['station'].nunique()}"
        )

        print(
            f"Unique rivers           : "
            f"{forecasts_df['river'].nunique()}"
        )

    print()
    print("Output files")
    print("-" * 80)
    print(f"Warnings : {WARNINGS_OUTPUT}")
    print(f"Forecasts: {FORECASTS_OUTPUT}")

    print()
    print("=" * 80)
    print("NCHMF PARSER FINISHED")
    print("=" * 80)


if __name__ == "__main__":
    main()