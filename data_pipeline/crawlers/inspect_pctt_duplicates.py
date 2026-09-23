import requests
import pandas as pd


BASE_URL = "https://pctt.danang.gov.vn/DesktopModules/PCTT/api/PCTTApi/baocaothuydiens_thongke"

START_DATE = "2026-07-01"
END_DATE = "2026-07-13"

EXPECTED_FIELDS = [
    "thoigianxa",
    "ngay",
    "gio",
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


def fetch_day(date_str):
    params = {
        "ngaybatdau": f"{date_str}T00:00:00+07:00",
        "ngayketthuc": f"{date_str}T23:59:59+07:00",
        "lst_thuydien_id": "1,2,3,4",
    }

    response = requests.get(
        BASE_URL,
        params=params,
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()

    if not isinstance(data, list):
        raise ValueError("API response is not a JSON list.")

    return pd.DataFrame(data)


def inspect_duplicates(df, date_str):
    print()
    print("=" * 80)
    print(f"DATE: {date_str}")
    print("=" * 80)

    if "thoigianxa" not in df.columns:
        print("ERROR: 'thoigianxa' field not found.")
        return

    df["timestamp"] = pd.to_datetime(
        df["thoigianxa"],
        errors="coerce",
    )

    duplicate_mask = df["timestamp"].duplicated(
        keep=False
    )

    duplicates = df[duplicate_mask].copy()

    if duplicates.empty:
        print("No duplicate timestamps.")
    else:
        print(f"Duplicate rows found: {len(duplicates)}")
        print()

        columns_to_show = [
            "timestamp",
            "ngay",
            "gio",
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

        columns_to_show = [
            c for c in columns_to_show
            if c in duplicates.columns
        ]

        print(
            duplicates[
                columns_to_show
            ].to_string(index=False)
        )

    # Missing numeric values
    print()
    print("-" * 80)
    print("MISSING VALUES")
    print("-" * 80)

    numeric_fields = [
        c for c in EXPECTED_FIELDS
        if c not in ["thoigianxa", "ngay", "gio"]
        and c in df.columns
    ]

    missing_counts = df[numeric_fields].isna().sum()

    missing_counts = missing_counts[
        missing_counts > 0
    ]

    if missing_counts.empty:
        print("No missing numeric values.")
    else:
        print(missing_counts.to_string())

        print()
        print("Rows containing missing values:")

        missing_rows = df[
            df[numeric_fields].isna().any(axis=1)
        ]

        print(
            missing_rows[
                ["timestamp"] + numeric_fields
            ].to_string(index=False)
        )


def main():
    print("=" * 80)
    print("PCTT DUPLICATE AND MISSING-VALUE INSPECTION")
    print("=" * 80)

    dates = pd.date_range(
        START_DATE,
        END_DATE,
        freq="D",
    )

    for date in dates:
        date_str = date.strftime("%Y-%m-%d")

        try:
            df = fetch_day(date_str)

            inspect_duplicates(
                df,
                date_str,
            )

        except Exception as exc:
            print()
            print(
                f"{date_str} | ERROR | {exc}"
            )


if __name__ == "__main__":
    main()