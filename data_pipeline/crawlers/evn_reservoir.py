import re
from io import StringIO
from pathlib import Path

import pandas as pd
import requests


EVN_URL = (
    "https://hochuathuydien.evn.com.vn/"
    "PageHoChuaThuyDienEmbedEVN.aspx"
)

OUTPUT_PATH = Path(
    "data/processed/evn_reservoir_current.csv"
)


COLUMN_MAP = {
    "Tên hồ": "reservoir_name",
    "Thời điểm": "observation_time",
    "Htl": "water_level_m",
    "Hdbt": "normal_water_level_m",
    "Hc": "dead_water_level_m",
    "Qve": "inflow_m3s",
    "ΣQx": "total_discharge_m3s",
    "Qxt": "spillway_discharge_m3s",
    "Qxm": "powerhouse_discharge_m3s",
    "Ncxs": "deep_release_gates",
    "Ncxm": "surface_release_gates",
}


NUMERIC_COLUMNS = [
    "water_level_m",
    "normal_water_level_m",
    "dead_water_level_m",
    "inflow_m3s",
    "total_discharge_m3s",
    "spillway_discharge_m3s",
    "powerhouse_discharge_m3s",
    "deep_release_gates",
    "surface_release_gates",
]


REGIONAL_HEADERS = {
    "Đông Bắc Bộ",
    "Tây Bắc Bộ",
    "Bắc Trung Bộ",
    "Nam Trung Bộ",
    "Tây Nguyên",
    "Đông Nam Bộ",
}


def fetch_evn_table() -> pd.DataFrame:
    """
    Download the current EVN reservoir table.
    """

    response = requests.get(
        EVN_URL,
        timeout=30,
        headers={
            "User-Agent": "Mozilla/5.0"
        },
    )

    response.raise_for_status()

    print(
        f"HTTP status: {response.status_code}"
    )

    print(
        f"Content-Type: "
        f"{response.headers.get('Content-Type')}"
    )

    # StringIO prevents pandas from treating the HTML
    # string as a file path.
    tables = pd.read_html(
        StringIO(response.text)
    )

    if not tables:
        raise RuntimeError(
            "No HTML table found in EVN response."
        )

    return tables[0]


def flatten_columns(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Flatten EVN's multi-level HTML column names.
    """

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [
            str(column[0]).strip()
            for column in df.columns
        ]
    else:
        df.columns = [
            str(column).strip()
            for column in df.columns
        ]

    return df


def extract_sync_time(value):
    """
    Extract the EVN synchronization time.

    Example:
        Tuyên Quang Đồng bộ lúc: 16:15 24/09

    Returns:
        16:15 24/09
    """

    if pd.isna(value):
        return None

    text = str(value).strip()

    match = re.search(
        r"Đồng bộ lúc:\s*(.+)$",
        text,
        flags=re.IGNORECASE,
    )

    if match:
        return match.group(1).strip()

    return None


def extract_reservoir_name(value):
    """
    Extract only the reservoir name.

    Example:
        Tuyên Quang Đồng bộ lúc: 16:15 24/09

    becomes:
        Tuyên Quang
    """

    if pd.isna(value):
        return None

    text = str(value).strip()

    if not text:
        return None

    text = re.sub(
        r"\s*Đồng bộ lúc:.*$",
        "",
        text,
        flags=re.IGNORECASE,
    )

    return text.strip()


def clean_evn_table(
    raw_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Clean the raw EVN reservoir table.
    """

    df = flatten_columns(
        raw_df.copy()
    )

    print("\nRaw columns:")
    print(df.columns.tolist())

    # --------------------------------------------------
    # Step 1: Keep rows that contain a reservoir name
    # --------------------------------------------------

    df = df[
        df["Tên hồ"].notna()
    ].copy()

    # --------------------------------------------------
    # Step 2: Extract synchronization time
    # before cleaning the reservoir name
    # --------------------------------------------------

    df["sync_time"] = df[
        "Tên hồ"
    ].apply(
        extract_sync_time
    )

    # --------------------------------------------------
    # Step 3: Clean reservoir names
    # --------------------------------------------------

    df["Tên hồ"] = df[
        "Tên hồ"
    ].apply(
        extract_reservoir_name
    )

    # --------------------------------------------------
    # Step 4: Remove regional header rows
    # --------------------------------------------------

    df = df[
        ~df["Tên hồ"].isin(
            REGIONAL_HEADERS
        )
    ].copy()

    # --------------------------------------------------
    # Step 5: Keep only actual reservoir rows
    #
    # Regional/header rows have no Htl value.
    # --------------------------------------------------

    df = df[
        df["Htl"].notna()
    ].copy()

    # --------------------------------------------------
    # Step 6: Rename columns
    # --------------------------------------------------

    df = df.rename(
        columns=COLUMN_MAP
    )

    # --------------------------------------------------
    # Step 7: Convert numeric fields
    # --------------------------------------------------

    for column in NUMERIC_COLUMNS:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    # --------------------------------------------------
    # Step 8: Select final column order
    # --------------------------------------------------

    columns = [
        "reservoir_name",
        "observation_time",
        "water_level_m",
        "normal_water_level_m",
        "dead_water_level_m",
        "inflow_m3s",
        "total_discharge_m3s",
        "spillway_discharge_m3s",
        "powerhouse_discharge_m3s",
        "deep_release_gates",
        "surface_release_gates",
        "sync_time",
    ]

    df = df[columns]

    # --------------------------------------------------
    # Step 9: Sort by reservoir name
    # --------------------------------------------------

    df = df.sort_values(
        "reservoir_name"
    ).reset_index(
        drop=True
    )

    return df


def validate_evn_data(
    df: pd.DataFrame,
) -> None:
    """
    Run basic data-quality checks.
    """

    print("\nValidation:")
    print(
        f"Rows: {len(df)}"
    )

    print(
        f"Columns: {len(df.columns)}"
    )

    print("\nMissing values:")

    print(
        df.isna().sum()
    )

    print(
        "\nDuplicate reservoir names:"
    )

    print(
        df["reservoir_name"]
        .duplicated()
        .sum()
    )

    print(
        "\nReservoir names:"
    )

    for name in df[
        "reservoir_name"
    ]:
        print(
            f"  - {name}"
        )


def main():
    print(
        "Fetching EVN reservoir data..."
    )

    # --------------------------------------------------
    # Fetch
    # --------------------------------------------------

    raw_df = fetch_evn_table()

    print(
        f"Raw table shape: "
        f"{raw_df.shape}"
    )

    # --------------------------------------------------
    # Clean
    # --------------------------------------------------

    df = clean_evn_table(
        raw_df
    )

    # --------------------------------------------------
    # Validate
    # --------------------------------------------------

    validate_evn_data(
        df
    )

    # --------------------------------------------------
    # Save
    # --------------------------------------------------

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    df.to_csv(
        OUTPUT_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    print("\nSaved:")
    print(
        OUTPUT_PATH
    )

    # --------------------------------------------------
    # Preview
    # --------------------------------------------------

    print("\nPreview:")

    print(
        df.to_string(
            index=False
        )
    )


if __name__ == "__main__":
    main()