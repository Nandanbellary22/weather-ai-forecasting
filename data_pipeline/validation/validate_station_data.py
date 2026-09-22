import pandas as pd


REQUIRED_COLUMNS = ["station_id", "timestamp", "value"]


def validate_station_data(df: pd.DataFrame) -> dict:
    """Validate basic structural and time-series properties."""

    results = {}

    # 1. Required columns
    results["required_columns"] = all(
        column in df.columns for column in REQUIRED_COLUMNS
    )

    # 2. Missing values
    results["missing_values"] = int(df[REQUIRED_COLUMNS].isna().sum().sum())

    # 3. Duplicate rows
    results["duplicate_rows"] = int(df.duplicated().sum())

    # 4. Number of rows
    results["row_count"] = len(df)

    # 5. Timestamp ordering
    results["timestamps_sorted"] = bool(
        df["timestamp"].is_monotonic_increasing
    )

    # 6. Duplicate timestamps
    results["duplicate_timestamps"] = int(
        df["timestamp"].duplicated().sum()
    )

    # 7. Numeric values
    results["numeric_values"] = bool(
        pd.api.types.is_numeric_dtype(df["value"])
    )

    # Overall validation
    results["valid"] = all(
        [
            results["required_columns"],
            results["missing_values"] == 0,
            results["duplicate_rows"] == 0,
            results["timestamps_sorted"],
            results["duplicate_timestamps"] == 0,
            results["numeric_values"],
        ]
    )

    return results