import pandas as pd


FILE_553100 = "data/processed/station_553100_30days.csv"
FILE_553300 = "data/processed/station_553300_30days.csv"

OUTPUT_FILE = "data/processed/historical_all_stations.csv"


def main():

    print("Loading station 553100...")
    df_553100 = pd.read_csv(FILE_553100)

    print("Loading station 553300...")
    df_553300 = pd.read_csv(FILE_553300)

    # Convert timestamp back to datetime
    df_553100["timestamp"] = pd.to_datetime(
        df_553100["timestamp"]
    )

    df_553300["timestamp"] = pd.to_datetime(
        df_553300["timestamp"]
    )

    # Combine
    combined = pd.concat(
        [df_553100, df_553300],
        ignore_index=True
    )

    # Sort
    combined = (
        combined
        .sort_values(
            ["timestamp", "station_id"]
        )
        .reset_index(drop=True)
    )

    print()
    print("=" * 60)
    print("COMBINED HISTORICAL DATASET")
    print("=" * 60)

    print(f"Rows: {len(combined)}")
    print(
        f"Stations: {combined['station_id'].nunique()}"
    )
    print(
        f"Start: {combined['timestamp'].min()}"
    )
    print(
        f"End:   {combined['timestamp'].max()}"
    )

    print()
    print("--- Rows by Station ---")

    print(
        combined.groupby("station_id").size()
    )

    print()
    print("--- Missing Values ---")

    print(
        combined[
            ["station_id", "timestamp", "value"]
        ].isna().sum()
    )

    print()
    print("--- Duplicate Station/Timestamps ---")

    duplicate_count = combined.duplicated(
        subset=["station_id", "timestamp"]
    ).sum()

    print(duplicate_count)

    print()
    print("--- Data Types ---")

    print(combined.dtypes)

    print()
    print("--- First 10 Rows ---")

    print(
        combined.head(10).to_string(index=False)
    )

    print()
    print("--- Last 10 Rows ---")

    print(
        combined.tail(10).to_string(index=False)
    )

    # Save
    combined.to_csv(
        OUTPUT_FILE,
        index=False
    )

    print()
    print(f"Saved to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()