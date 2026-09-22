import pandas as pd


FILE_553100 = "data/processed/station_553100.csv"
FILE_553300 = "data/processed/station_553300.csv"

OUTPUT_FILE = "data/processed/all_stations.csv"


def load_station_data(file_path):
    df = pd.read_csv(file_path)

    df["station_id"] = df["station_id"].astype(str)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")

    return df


def main():
    print("Loading station 553100...")
    df_553100 = load_station_data(FILE_553100)

    print("Loading station 553300...")
    df_553300 = load_station_data(FILE_553300)

    print("\nStation 553100:")
    print(df_553100.head())

    print("\nStation 553300:")
    print(df_553300.head())

    # Combine both stations
    combined = pd.concat(
        [df_553100, df_553300],
        ignore_index=True,
    )

    # Sort by time and station
    combined = combined.sort_values(
        ["timestamp", "station_id"]
    ).reset_index(drop=True)

    print("\n--- Combined DataFrame ---")
    print(combined)

    print("\n--- Records per station ---")
    print(combined["station_id"].value_counts())

    print("\n--- Data types ---")
    print(combined.dtypes)

    # Save combined dataset
    combined.to_csv(
        OUTPUT_FILE,
        index=False,
    )

    print(f"\nSaved combined data to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()