import os
import requests
import pandas as pd


BASE_URL = (
    "https://pctt.danang.gov.vn/"
    "DesktopModules/PCTT/api/PCTTApi/"
    "baocaothuydiens_thongke"
)

START_DATE = "2026-07-01"
END_DATE = "2026-07-13"

OUTPUT_DIR = "data/processed"

RAW_OUTPUT = os.path.join(
    OUTPUT_DIR,
    "pctt_raw_13days.csv"
)

CLEAN_OUTPUT = os.path.join(
    OUTPUT_DIR,
    "pctt_clean_13days.csv"
)

QUALITY_OUTPUT = os.path.join(
    OUTPUT_DIR,
    "pctt_quality_report.csv"
)


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


NUMERIC_FIELDS = [
    field
    for field in EXPECTED_FIELDS
    if field not in ["thoigianxa", "ngay", "gio"]
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
        raise ValueError(
            "API response is not a JSON list."
        )

    return pd.DataFrame(data)


def standardize_dataframe(df):
    missing_fields = [
        field
        for field in EXPECTED_FIELDS
        if field not in df.columns
    ]

    if missing_fields:
        raise ValueError(
            f"Missing API fields: {missing_fields}"
        )

    df = df[EXPECTED_FIELDS].copy()

    df["timestamp"] = pd.to_datetime(
        df["thoigianxa"],
        errors="coerce"
    )

    for field in NUMERIC_FIELDS:
        df[field] = pd.to_numeric(
            df[field],
            errors="coerce"
        )

    return df


def rows_are_identical(group):
    """
    Returns True if all records for a timestamp
    contain identical values.
    """

    comparison_columns = [
        field
        for field in EXPECTED_FIELDS
        if field not in ["thoigianxa"]
    ]

    return (
        group[comparison_columns]
        .nunique(dropna=False)
        .max()
        <= 1
    )


def process_day(df, date_str):
    quality_records = []

    # --------------------------------------------------
    # 1. Check timestamps
    # --------------------------------------------------

    invalid_timestamp = df["timestamp"].isna()

    if invalid_timestamp.any():
        quality_records.append({
            "date": date_str,
            "timestamp": "",
            "issue_type": "invalid_timestamp",
            "number_of_records": int(
                invalid_timestamp.sum()
            ),
            "resolution": "flagged",
        })

        df = df[
            ~invalid_timestamp
        ].copy()

    # --------------------------------------------------
    # 2. Missing values
    # --------------------------------------------------

    missing_mask = df[NUMERIC_FIELDS].isna().any(axis=1)

    for _, row in df[missing_mask].iterrows():

        missing_fields = [
            field
            for field in NUMERIC_FIELDS
            if pd.isna(row[field])
        ]

        quality_records.append({
            "date": date_str,
            "timestamp": row["timestamp"],
            "issue_type": "missing_values",
            "number_of_records": 1,
            "resolution": (
                "retained_nan: "
                + ",".join(missing_fields)
            ),
        })

    # --------------------------------------------------
    # 3. Duplicate timestamp detection
    # --------------------------------------------------

    duplicate_mask = df["timestamp"].duplicated(
        keep=False
    )

    duplicate_groups = (
        df[duplicate_mask]
        .groupby("timestamp", sort=True)
    )

    rows_to_keep = []

    for timestamp, group in duplicate_groups:

        if rows_are_identical(group):

            # Exact duplicate.
            # Keep the first copy only.
            rows_to_keep.append(
                group.index[0]
            )

            quality_records.append({
                "date": date_str,
                "timestamp": timestamp,
                "issue_type": "exact_duplicate",
                "number_of_records": len(group),
                "resolution": "kept_first_record",
            })

        else:

            # Conflicting duplicate.
            # Do NOT silently choose one.
            quality_records.append({
                "date": date_str,
                "timestamp": timestamp,
                "issue_type": "conflicting_duplicate",
                "number_of_records": len(group),
                "resolution": "flagged_not_automatically_resolved",
            })

            # We deliberately keep ALL conflicting
            # records in the raw dataset but exclude
            # them from the clean forecasting dataset.

    # --------------------------------------------------
    # 4. Build clean dataset
    # --------------------------------------------------

    duplicate_timestamps = set(
        df.loc[
            duplicate_mask,
            "timestamp"
        ]
    )

    # Remove every timestamp involved in a
    # conflicting duplicate.
    conflicting_timestamps = set()

    for timestamp, group in duplicate_groups:

        if not rows_are_identical(group):
            conflicting_timestamps.add(timestamp)

    clean_df = df[
        ~df["timestamp"].isin(
            conflicting_timestamps
        )
    ].copy()

    # Remove exact duplicate rows while retaining
    # the first observation.
    clean_df = clean_df.drop_duplicates(
        subset=EXPECTED_FIELDS,
        keep="first"
    )

    clean_df = clean_df.sort_values(
        "timestamp"
    ).reset_index(drop=True)

    return clean_df, quality_records


def main():

    print("=" * 80)
    print("PCTT RAW + QUALITY-CONTROL PIPELINE")
    print("=" * 80)

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True
    )

    dates = pd.date_range(
        START_DATE,
        END_DATE,
        freq="D"
    )

    raw_frames = []
    clean_frames = []
    quality_records = []

    for date in dates:

        date_str = date.strftime(
            "%Y-%m-%d"
        )

        print(
            f"\nFetching {date_str}..."
        )

        try:

            raw_df = fetch_day(
                date_str
            )

            raw_df = standardize_dataframe(
                raw_df
            )

            raw_df["source_date"] = date_str

            raw_frames.append(
                raw_df
            )

            clean_df, day_quality = (
                process_day(
                    raw_df,
                    date_str
                )
            )

            clean_df["source_date"] = date_str

            clean_frames.append(
                clean_df
            )

            quality_records.extend(
                day_quality
            )

            print(
                f"  Raw rows   : {len(raw_df)}"
            )

            print(
                f"  Clean rows : {len(clean_df)}"
            )

            print(
                f"  QC issues  : {len(day_quality)}"
            )

        except Exception as exc:

            print(
                f"  ERROR: {exc}"
            )

            quality_records.append({
                "date": date_str,
                "timestamp": "",
                "issue_type": "api_error",
                "number_of_records": 0,
                "resolution": str(exc),
            })

    # --------------------------------------------------
    # Save raw data
    # --------------------------------------------------

    if raw_frames:

        raw_all = pd.concat(
            raw_frames,
            ignore_index=True
        )

        raw_all = raw_all.sort_values(
            "timestamp"
        ).reset_index(drop=True)

        raw_all.to_csv(
            RAW_OUTPUT,
            index=False
        )

    else:
        raw_all = pd.DataFrame()

    # --------------------------------------------------
    # Save clean data
    # --------------------------------------------------

    if clean_frames:

        clean_all = pd.concat(
            clean_frames,
            ignore_index=True
        )

        clean_all = clean_all.sort_values(
            "timestamp"
        ).reset_index(drop=True)

        clean_all.to_csv(
            CLEAN_OUTPUT,
            index=False
        )

    else:
        clean_all = pd.DataFrame()

    # --------------------------------------------------
    # Save quality report
    # --------------------------------------------------

    quality_df = pd.DataFrame(
        quality_records,
        columns=[
            "date",
            "timestamp",
            "issue_type",
            "number_of_records",
            "resolution",
        ]
    )

    quality_df.to_csv(
        QUALITY_OUTPUT,
        index=False
    )

    # --------------------------------------------------
    # Final summary
    # --------------------------------------------------

    print()
    print("=" * 80)
    print("FINAL SUMMARY")
    print("=" * 80)

    print(
        f"Raw rows          : {len(raw_all)}"
    )

    print(
        f"Clean rows        : {len(clean_all)}"
    )

    print(
        f"QC records        : {len(quality_df)}"
    )

    if not quality_df.empty:

        print()
        print("QC issues:")

        print(
            quality_df[
                "issue_type"
            ].value_counts().to_string()
        )

    print()
    print(
        f"Raw output        : {RAW_OUTPUT}"
    )

    print(
        f"Clean output      : {CLEAN_OUTPUT}"
    )

    print(
        f"Quality report    : {QUALITY_OUTPUT}"
    )


if __name__ == "__main__":
    main()