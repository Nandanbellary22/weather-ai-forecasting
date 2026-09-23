from pathlib import Path
import pandas as pd


INPUT_FILES = [
    Path("data/processed/station_553100_90days.csv"),
    Path("data/processed/station_553300_90days.csv"),
]

OUTPUT_FILE = Path("data/processed/historical_90days_all_stations.csv")


def main():
    dataframes = []

    for file in INPUT_FILES:
        print(f"Loading: {file}")

        df = pd.read_csv(file)

        df["station_id"] = df["station_id"].astype(str)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df["value"] = pd.to_numeric(df["value"], errors="coerce")

        dataframes.append(df)

    combined = pd.concat(dataframes, ignore_index=True)

    combined = combined.sort_values(
        ["timestamp", "station_id"]
    ).reset_index(drop=True)

    print("\n===== 90-DAY DATASET SUMMARY =====")
    print(f"Rows: {len(combined)}")
    print(f"Stations: {combined['station_id'].nunique()}")
    print(f"Start: {combined['timestamp'].min()}")
    print(f"End: {combined['timestamp'].max()}")

    print("\nRows per station:")
    print(combined.groupby("station_id").size())

    print("\nMissing values:")
    print(combined.isna().sum())

    duplicate_count = combined.duplicated(
        subset=["station_id", "timestamp"]
    ).sum()

    print(f"\nDuplicate station/timestamp records: {duplicate_count}")

    print("\nData types:")
    print(combined.dtypes)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(OUTPUT_FILE, index=False)

    print(f"\nSaved: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()