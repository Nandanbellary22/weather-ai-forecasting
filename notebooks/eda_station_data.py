import pandas as pd


INPUT_FILE = "data/processed/all_stations.csv"


def main():
    print(f"Loading: {INPUT_FILE}")

    df = pd.read_csv(INPUT_FILE)

    df["station_id"] = df["station_id"].astype(str)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")

    print("\n--- Dataset Overview ---")
    print(f"Rows: {len(df)}")
    print(f"Stations: {df['station_id'].nunique()}")
    print(f"Start time: {df['timestamp'].min()}")
    print(f"End time: {df['timestamp'].max()}")

    print("\n--- Statistics by Station ---")

    statistics = (
        df.groupby("station_id")["value"]
        .agg(
            count="count",
            mean="mean",
            median="median",
            minimum="min",
            maximum="max",
            std="std",
        )
    )

    print(statistics)

    print("\n--- First and Last Values ---")

    for station_id, station_df in df.groupby("station_id"):
        station_df = station_df.sort_values("timestamp")

        first_value = station_df.iloc[0]["value"]
        last_value = station_df.iloc[-1]["value"]
        change = last_value - first_value

        print(f"\nStation {station_id}")
        print(f"  First value: {first_value}")
        print(f"  Last value:  {last_value}")
        print(f"  Change:      {change:.3f}")

    print("\n--- Hour-to-Hour Changes ---")

    df = df.sort_values(["station_id", "timestamp"])

    df["value_change"] = (
        df.groupby("station_id")["value"]
        .diff()
    )

    print(
        df[
            [
                "station_id",
                "timestamp",
                "value",
                "value_change",
            ]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()