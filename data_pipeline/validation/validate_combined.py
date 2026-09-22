import pandas as pd


INPUT_FILE = "data/processed/all_stations.csv"


def validate_combined_data(df):
    results = {}

    required_columns = ["station_id", "timestamp", "value"]

    # 1. Check required columns
    results["required_columns"] = all(
        column in df.columns for column in required_columns
    )

    # 2. Check missing values
    results["missing_values"] = int(df[required_columns].isna().sum().sum())

    # 3. Check duplicate rows
    results["duplicate_rows"] = int(df.duplicated().sum())

    # 4. Check row count
    results["row_count"] = len(df)

    # 5. Check timestamp type
    results["timestamp_datetime"] = pd.api.types.is_datetime64_any_dtype(
        df["timestamp"]
    )

    # 6. Check numeric values
    results["numeric_values"] = pd.api.types.is_numeric_dtype(
        df["value"]
    )

    # 7. Check duplicate station + timestamp combinations
    results["duplicate_station_timestamps"] = int(
        df.duplicated(subset=["station_id", "timestamp"]).sum()
    )

    # 8. Check each station separately
    station_results = {}

    for station_id, station_df in df.groupby("station_id"):
        station_results[str(station_id)] = {
            "row_count": len(station_df),
            "missing_values": int(
                station_df[["timestamp", "value"]].isna().sum().sum()
            ),
            "duplicate_timestamps": int(
                station_df["timestamp"].duplicated().sum()
            ),
            "timestamps_sorted": station_df["timestamp"].is_monotonic_increasing,
        }

    results["stations"] = station_results

    # Overall validation
    results["valid"] = (
        results["required_columns"]
        and results["missing_values"] == 0
        and results["duplicate_rows"] == 0
        and results["timestamp_datetime"]
        and results["numeric_values"]
        and results["duplicate_station_timestamps"] == 0
    )

    return results


def main():
    print(f"Loading: {INPUT_FILE}")

    df = pd.read_csv(INPUT_FILE)

    df["station_id"] = df["station_id"].astype(str)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")

    results = validate_combined_data(df)

    print("\n--- Combined Dataset Validation ---")

    for key, value in results.items():
        if key != "stations":
            print(f"{key}: {value}")

    print("\n--- Station-level Validation ---")

    for station_id, station_result in results["stations"].items():
        print(f"\nStation {station_id}")

        for key, value in station_result.items():
            print(f"  {key}: {value}")


if __name__ == "__main__":
    main()