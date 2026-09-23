import requests
import pandas as pd
from datetime import datetime, timedelta


URL = (
    "https://pctt.danang.gov.vn/"
    "DesktopModules/PCTT/api/PCTTApi/"
    "baocaothuydiens_thongke"
)

START_DATE = datetime(2026, 7, 1)
END_DATE = datetime(2026, 7, 13)


EXPECTED_FIELDS = [
    "htl1",
    "qvao1",
    "luuluongnhamay1",
    "qxaquacua1",

    "htl2",
    "qvao2",
    "luuluongnhamay2",
    "qxaquacua2",

    "htl3",
    "qvao3",
    "luuluongnhamay3",
    "qxaquacua3",

    "htl4",
    "qvao4",
    "luuluongnhamay4",
    "qxaquacua4",

    "qvevugia",
    "qvethubon",
]


def fetch_day(date):
    start = date.strftime(
        "%Y-%m-%dT00:00:00+07:00"
    )

    end = date.strftime(
        "%Y-%m-%dT23:59:59+07:00"
    )

    params = {
        "ngaybatdau": start,
        "ngayketthuc": end,
        "lst_thuydien_id": "1,2,3,4",
    }

    response = requests.get(
        URL,
        params=params,
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()

    return pd.DataFrame(data)


def inspect_day(date):

    result = {
        "date": date.strftime("%Y-%m-%d"),
        "status": "ERROR",
        "rows": 0,
        "expected_rows": 24,
        "unique_timestamps": 0,
        "missing_timestamps": 0,
        "duplicate_timestamps": 0,
        "missing_fields": 0,
        "missing_values": 0,
        "error": "",
    }

    try:

        df = fetch_day(date)

        if df.empty:

            result["status"] = "NO_DATA"

            return result

        result["rows"] = len(df)

        # -------------------------------------------------
        # Timestamp checks
        # -------------------------------------------------

        if "thoigianxa" in df.columns:

            timestamps = pd.to_datetime(
                df["thoigianxa"],
                errors="coerce",
            )

            valid_timestamps = timestamps.dropna()

            result["unique_timestamps"] = (
                valid_timestamps.nunique()
            )

            result["duplicate_timestamps"] = (
                len(valid_timestamps)
                - valid_timestamps.nunique()
            )

            # Expected hourly records.
            expected = pd.date_range(
                start=date,
                periods=24,
                freq="h",
            )

            actual = set(
                valid_timestamps
            )

            expected_set = set(expected)

            result["missing_timestamps"] = len(
                expected_set - actual
            )

        else:

            result["error"] = (
                "Missing thoigianxa field"
            )

            return result

        # -------------------------------------------------
        # Field checks
        # -------------------------------------------------

        missing_fields = [
            field
            for field in EXPECTED_FIELDS
            if field not in df.columns
        ]

        result["missing_fields"] = len(
            missing_fields
        )

        if missing_fields:

            result["error"] = (
                "Missing fields: "
                + ", ".join(missing_fields)
            )

            return result

        # -------------------------------------------------
        # Numeric value checks
        # -------------------------------------------------

        numeric_df = df[
            EXPECTED_FIELDS
        ].apply(
            pd.to_numeric,
            errors="coerce",
        )

        result["missing_values"] = int(
            numeric_df.isna().sum().sum()
        )

        # -------------------------------------------------
        # Status
        # -------------------------------------------------

        if result["rows"] == 24:

            result["status"] = "OK"

        else:

            result["status"] = "INCOMPLETE"

        return result

    except Exception as e:

        result["error"] = str(e)

        return result


def main():

    print("=" * 80)
    print("PCTT HISTORICAL COVERAGE AUDIT")
    print("=" * 80)

    print(
        "Period:",
        START_DATE.strftime("%Y-%m-%d"),
        "to",
        END_DATE.strftime("%Y-%m-%d"),
    )

    print()

    results = []

    current = START_DATE

    while current <= END_DATE:

        result = inspect_day(current)

        results.append(result)

        print(
            f"{result['date']} | "
            f"status={result['status']} | "
            f"rows={result['rows']} | "
            f"unique_ts={result['unique_timestamps']} | "
            f"missing_ts={result['missing_timestamps']} | "
            f"duplicate_ts={result['duplicate_timestamps']} | "
            f"missing_values={result['missing_values']}"
        )

        if result["error"]:

            print(
                f"    ERROR: {result['error']}"
            )

        current += timedelta(days=1)

    audit_df = pd.DataFrame(results)

    output_path = (
        "data/processed/"
        "pctt_coverage_audit.csv"
    )

    audit_df.to_csv(
        output_path,
        index=False,
    )

    print()
    print("=" * 80)
    print("FINAL SUMMARY")
    print("=" * 80)

    total_days = len(audit_df)

    ok_days = (
        audit_df["status"] == "OK"
    ).sum()

    incomplete_days = (
        audit_df["status"] == "INCOMPLETE"
    ).sum()

    no_data_days = (
        audit_df["status"] == "NO_DATA"
    ).sum()

    error_days = (
        audit_df["status"] == "ERROR"
    ).sum()

    total_rows = audit_df[
        "rows"
    ].sum()

    expected_rows = total_days * 24

    print(
        f"Days tested       : {total_days}"
    )

    print(
        f"OK days           : {ok_days}"
    )

    print(
        f"Incomplete days   : {incomplete_days}"
    )

    print(
        f"No-data days      : {no_data_days}"
    )

    print(
        f"Error days        : {error_days}"
    )

    print(
        f"Total rows        : {total_rows}"
    )

    print(
        f"Expected rows     : {expected_rows}"
    )

    print()
    print(
        f"Saved audit to: {output_path}"
    )


if __name__ == "__main__":
    main()