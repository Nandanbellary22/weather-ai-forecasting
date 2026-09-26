import os
import requests
import pandas as pd


BASE_URL = (
    "https://pctt.danang.gov.vn/"
    "DesktopModules/PCTT/api/PCTTApi/"
    "baocaothuydiens_thongke"
)

START_DATE = "2026-01-15"
END_DATE = "2026-07-13"

OUTPUT_DIR = "data/processed"

RAW_INPUT = os.path.join(
    OUTPUT_DIR,
    "pctt_historical_180days_raw.csv"
)

CLEAN_OUTPUT = os.path.join(
    OUTPUT_DIR,
    "pctt_historical_180days_clean.csv"
)

QUALITY_OUTPUT = os.path.join(
    OUTPUT_DIR,
    "pctt_historical_180days_quality_report.csv"
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
    if field not in [
        "thoigianxa",
        "ngay",
        "gio",
    ]
]


def rows_are_identical(group):
    """
    Return True when all records for a timestamp
    contain identical values.
    """

    comparison_columns = [
        field
        for field in EXPECTED_FIELDS
        if field != "thoigianxa"
    ]

    return (
        group[comparison_columns]
        .nunique(dropna=False)
        .max()
        <= 1
    )


def standardize_dataframe(df):
    """
    Validate and standardize the historical raw dataset.
    """

    missing_fields = [
        field
        for field in EXPECTED_FIELDS
        if field not in df.columns
    ]

    if missing_fields:
        raise ValueError(
            f"Missing API fields: {missing_fields}"
        )

    df = df[
        EXPECTED_FIELDS
        + ["timestamp", "source_date"]
    ].copy()

    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        errors="coerce",
    )

    for field in NUMERIC_FIELDS:
        df[field] = pd.to_numeric(
            df[field],
            errors="coerce",
        )

    return df


def process_dataset(df):

    quality_records = []

    # --------------------------------------------------
    # 1. Invalid timestamps
    # --------------------------------------------------

    invalid_timestamp = df["timestamp"].isna()

    if invalid_timestamp.any():

        quality_records.append({
            "date": "",
            "timestamp": "",
            "issue_type": "invalid_timestamp",
            "number_of_records": int(
                invalid_timestamp.sum()
            ),
            "resolution": "removed_from_clean_dataset",
        })

        df = df[
            ~invalid_timestamp
        ].copy()

    # --------------------------------------------------
    # 2. Missing numeric values
    # --------------------------------------------------

    missing_mask = (
        df[NUMERIC_FIELDS]
        .isna()
        .any(axis=1)
    )

    for _, row in df[missing_mask].iterrows():

        missing_fields = [
            field
            for field in NUMERIC_FIELDS
            if pd.isna(row[field])
        ]

        quality_records.append({
            "date": row["source_date"],
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

    duplicate_mask = (
        df["timestamp"]
        .duplicated(keep=False)
    )

    duplicate_groups = (
        df[duplicate_mask]
        .groupby("timestamp", sort=True)
    )

    conflicting_timestamps = set()

    exact_duplicate_timestamps = set()

    for timestamp, group in duplicate_groups:

        if rows_are_identical(group):

            exact_duplicate_timestamps.add(
                timestamp
            )

            quality_records.append({
                "date": (
                    group["source_date"]
                    .iloc[0]
                ),
                "timestamp": timestamp,
                "issue_type": "exact_duplicate",
                "number_of_records": len(group),
                "resolution": "kept_first_record",
            })

        else:

            conflicting_timestamps.add(
                timestamp
            )

            quality_records.append({
                "date": (
                    group["source_date"]
                    .iloc[0]
                ),
                "timestamp": timestamp,
                "issue_type": "conflicting_duplicate",
                "number_of_records": len(group),
                "resolution": (
                    "flagged_and_removed_from_"
                    "clean_dataset"
                ),
            })

    # --------------------------------------------------
    # 4. Remove conflicting duplicates
    # --------------------------------------------------

    clean_df = df[
        ~df["timestamp"].isin(
            conflicting_timestamps
        )
    ].copy()

    # --------------------------------------------------
    # 5. Remove exact duplicate copies
    # --------------------------------------------------

    clean_df = clean_df.drop_duplicates(
        subset=EXPECTED_FIELDS,
        keep="first",
    )

    clean_df = clean_df.sort_values(
        "timestamp"
    ).reset_index(
        drop=True
    )

    return clean_df, quality_records


def main():

    print("=" * 80)
    print("PCTT HISTORICAL 180-DAY QUALITY CONTROL")
    print("=" * 80)

    print(
        f"Input : {RAW_INPUT}"
    )

    print(
        f"Period: {START_DATE} → {END_DATE}"
    )

    print()

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True,
    )

    # --------------------------------------------------
    # Load raw dataset
    # --------------------------------------------------

    if not os.path.exists(RAW_INPUT):

        raise FileNotFoundError(
            f"Raw PCTT dataset not found: {RAW_INPUT}"
        )

    raw_df = pd.read_csv(
        RAW_INPUT
    )

    print(
        f"Raw rows loaded: {len(raw_df)}"
    )

    print(
        f"Raw columns    : {len(raw_df.columns)}"
    )

    # --------------------------------------------------
    # Standardize
    # --------------------------------------------------

    raw_df = standardize_dataframe(
        raw_df
    )

    # --------------------------------------------------
    # Process
    # --------------------------------------------------

    clean_df, quality_records = (
        process_dataset(
            raw_df
        )
    )

    quality_df = pd.DataFrame(
        quality_records,
        columns=[
            "date",
            "timestamp",
            "issue_type",
            "number_of_records",
            "resolution",
        ],
    )

    # --------------------------------------------------
    # Save clean dataset
    # --------------------------------------------------

    clean_df.to_csv(
        CLEAN_OUTPUT,
        index=False,
    )

    # --------------------------------------------------
    # Save quality report
    # --------------------------------------------------

    quality_df.to_csv(
        QUALITY_OUTPUT,
        index=False,
    )

    # --------------------------------------------------
    # Final summary
    # --------------------------------------------------

    print()
    print("=" * 80)
    print("FINAL QUALITY-CONTROL SUMMARY")
    print("=" * 80)

    print(
        f"Raw rows       : {len(raw_df)}"
    )

    print(
        f"Clean rows     : {len(clean_df)}"
    )

    print(
        f"Rows removed   : "
        f"{len(raw_df) - len(clean_df)}"
    )

    print(
        f"QC records     : {len(quality_df)}"
    )

    if not quality_df.empty:

        print()
        print("QC issue counts")
        print("-" * 80)

        print(
            quality_df[
                "issue_type"
            ]
            .value_counts()
            .to_string()
        )

    print()
    print("Clean dataset")
    print("-" * 80)

    print(
        f"Start time     : "
        f"{clean_df['timestamp'].min()}"
    )

    print(
        f"End time       : "
        f"{clean_df['timestamp'].max()}"
    )

    print()
    print("Missing values in clean dataset")
    print("-" * 80)

    missing_counts = (
        clean_df[
            NUMERIC_FIELDS
        ]
        .isna()
        .sum()
    )

    missing_counts = (
        missing_counts[
            missing_counts > 0
        ]
    )

    if missing_counts.empty:

        print(
            "No missing numeric values."
        )

    else:

        print(
            missing_counts.to_string()
        )

    print()
    print("Duplicate timestamps remaining")
    print("-" * 80)

    remaining_duplicates = (
        clean_df["timestamp"]
        .duplicated(
            keep=False
        )
        .sum()
    )

    print(
        f"Duplicate timestamp rows: "
        f"{remaining_duplicates}"
    )

    print()
    print("Output files")
    print("-" * 80)

    print(
        f"Clean dataset : {CLEAN_OUTPUT}"
    )

    print(
        f"Quality report: {QUALITY_OUTPUT}"
    )

    print()
    print("=" * 80)
    print("PCTT QUALITY CONTROL COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()