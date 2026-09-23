import requests
import pandas as pd
from io import StringIO
from datetime import datetime, timedelta


BASE_URL = "http://203.209.181.170:2018/API_TTB/XUAT/solieu.php"

STATIONS = [
    "553000",
    "553100",
    "553200",
    "553300",
    "553400",
]

# We deliberately test a manageable historical window first.
# After we understand coverage, we can collect the full dataset.
START_DATE = datetime(2026, 7, 1)
END_DATE = datetime(2026, 7, 13)


def fetch_day(station_id: str, date: datetime):

    start_time = date.strftime("%Y-%m-%d 00:00")
    end_time = date.strftime("%Y-%m-%d 23:59")

    params = {
        "matram": station_id,
        "ten_table": "mucnuoc_oday",
        "sophut": 60,
        "tinhtong": 0,
        "thoigianbd": f"'{start_time}'",
        "thoigiankt": f"'{end_time}'",
    }

    response = requests.get(
        BASE_URL,
        params=params,
        timeout=15,
    )

    response.raise_for_status()

    tables = pd.read_html(
        StringIO(response.text)
    )

    if not tables:
        return pd.DataFrame()

    df = tables[0].copy()

    return df


def inspect_day(station_id: str, date: datetime):

    result = {
        "station_id": station_id,
        "date": date.strftime("%Y-%m-%d"),
        "status": "ERROR",
        "rows": 0,
        "numeric_rows": 0,
        "unique_timestamps": 0,
        "missing_values": 0,
        "min_value": None,
        "max_value": None,
        "error": "",
    }

    try:

        df = fetch_day(
            station_id,
            date,
        )

        if df.empty:
            result["status"] = "NO_DATA"
            return result

        result["rows"] = len(df)

        if "so lieu" not in df.columns:
            result["error"] = (
                f"Missing so lieu column: {list(df.columns)}"
            )
            return result

        # Convert observation values to numeric.
        values = pd.to_numeric(
            df["so lieu"],
            errors="coerce",
        )

        result["numeric_rows"] = int(
            values.notna().sum()
        )

        result["missing_values"] = int(
            values.isna().sum()
        )

        if result["numeric_rows"] > 0:

            numeric = values.dropna()

            result["min_value"] = float(
                numeric.min()
            )

            result["max_value"] = float(
                numeric.max()
            )

        # Inspect timestamp column if available.
        if "thoi gian" in df.columns:

            timestamps = pd.to_datetime(
                df["thoi gian"],
                errors="coerce",
            )

            result["unique_timestamps"] = int(
                timestamps.dropna().nunique()
            )

        if result["numeric_rows"] == 0:
            result["status"] = "NO_DATA"

        else:
            result["status"] = "OK"

        return result

    except Exception as e:

        result["error"] = str(e)

        return result


def main():

    print("=" * 80)
    print("HISTORICAL COVERAGE AUDIT")
    print("=" * 80)

    print(
        f"Period: "
        f"{START_DATE.strftime('%Y-%m-%d')} "
        f"to "
        f"{END_DATE.strftime('%Y-%m-%d')}"
    )

    print(
        f"Stations: {', '.join(STATIONS)}"
    )

    print()

    results = []

    total_days = (
        END_DATE - START_DATE
    ).days + 1

    for station_id in STATIONS:

        print("-" * 80)
        print(f"Station {station_id}")
        print("-" * 80)

        station_results = []

        current_date = START_DATE

        while current_date <= END_DATE:

            result = inspect_day(
                station_id,
                current_date,
            )

            results.append(result)
            station_results.append(result)

            if result["status"] == "OK":

                print(
                    f"{result['date']} | "
                    f"rows={result['rows']} | "
                    f"numeric={result['numeric_rows']} | "
                    f"range="
                    f"{result['min_value']} - "
                    f"{result['max_value']}"
                )

            elif result["status"] == "NO_DATA":

                print(
                    f"{result['date']} | NO DATA"
                )

            else:

                print(
                    f"{result['date']} | ERROR | "
                    f"{result['error']}"
                )

            current_date += timedelta(days=1)

        station_df = pd.DataFrame(
            station_results
        )

        ok_days = (
            station_df["status"] == "OK"
        ).sum()

        no_data_days = (
            station_df["status"] == "NO_DATA"
        ).sum()

        error_days = (
            station_df["status"] == "ERROR"
        ).sum()

        total_rows = station_df[
            "numeric_rows"
        ].sum()

        expected_rows = total_days * 24

        print()
        print(
            f"Summary {station_id}:"
        )
        print(
            f"  Days tested     : {total_days}"
        )
        print(
            f"  Complete days   : {ok_days}"
        )
        print(
            f"  No-data days    : {no_data_days}"
        )
        print(
            f"  Error days      : {error_days}"
        )
        print(
            f"  Numeric rows    : {total_rows}"
        )
        print(
            f"  Expected rows   : {expected_rows}"
        )

    # Save detailed audit.
    audit_df = pd.DataFrame(results)

    output_path = (
        "data/processed/"
        "historical_coverage_audit.csv"
    )

    audit_df.to_csv(
        output_path,
        index=False,
    )

    print()
    print("=" * 80)
    print("FINAL SUMMARY")
    print("=" * 80)

    for station_id in STATIONS:

        station_df = audit_df[
            audit_df["station_id"]
            == station_id
        ]

        ok_days = (
            station_df["status"] == "OK"
        ).sum()

        numeric_rows = station_df[
            "numeric_rows"
        ].sum()

        print(
            f"{station_id}: "
            f"{ok_days}/{total_days} days OK | "
            f"{numeric_rows} numeric rows"
        )

    print()
    print(
        f"Saved audit to: {output_path}"
    )


if __name__ == "__main__":
    main()