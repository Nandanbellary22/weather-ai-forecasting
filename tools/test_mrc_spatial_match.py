import os
from math import radians, sin, cos, asin, sqrt

import pandas as pd
import psycopg2


DB_CONFIG = {
    "host": "localhost",
    "database": "weather_forecasting",
    "user": "postgres",
    "password": os.environ.get("PGPASSWORD"),
}


def haversine_km(lat1, lon1, lat2, lon2):
    radius_km = 6371.0088

    lat1 = radians(lat1)
    lon1 = radians(lon1)
    lat2 = radians(lat2)
    lon2 = radians(lon2)

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        sin(dlat / 2) ** 2
        + cos(lat1)
        * cos(lat2)
        * sin(dlon / 2) ** 2
    )

    return 2 * radius_km * asin(sqrt(a))


def classify_distance(distance_km):
    if distance_km <= 25:
        return "Nearby"
    if distance_km <= 75:
        return "Regional"
    if distance_km <= 150:
        return "Distant"

    return "No nearby MRC station"


def main():
    conn = psycopg2.connect(**DB_CONFIG)

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT
                    location_code,
                    latitude,
                    longitude
                FROM weather_observations
                WHERE latitude IS NOT NULL
                  AND longitude IS NOT NULL
                ORDER BY location_code;
                """
            )

            weather = pd.DataFrame(
                cur.fetchall(),
                columns=[
                    "location_code",
                    "latitude",
                    "longitude",
                ],
            )
    finally:
        conn.close()

    mrc = pd.read_csv(
        "data/processed/mrc_vietnam_stations.csv"
    )

    mrc = mrc.dropna(
        subset=["latitude", "longitude"]
    ).copy()

    results = []

    for _, weather_row in weather.iterrows():
        best_station = None
        best_distance = None

        for _, mrc_row in mrc.iterrows():
            distance = haversine_km(
                weather_row["latitude"],
                weather_row["longitude"],
                mrc_row["latitude"],
                mrc_row["longitude"],
            )

            if best_distance is None or distance < best_distance:
                best_distance = distance
                best_station = mrc_row

        results.append(
            {
                "weather_location": weather_row["location_code"],
                "nearest_mrc_station": best_station["station_name"],
                "nearest_mrc_id": best_station["station_id"],
                "distance_km": best_distance,
                "classification": classify_distance(
                    best_distance
                ),
            }
        )

    result = pd.DataFrame(results)

    print("Weather locations:", len(result))
    print("MRC stations:", len(mrc))
    print()

    print("Spatial relevance:")
    print(
        result["classification"]
        .value_counts()
        .sort_index()
        .to_string()
    )

    print()

    print("Percentages:")
    percentages = (
        result["classification"]
        .value_counts(normalize=True)
        .mul(100)
        .sort_index()
    )

    for category, percentage in percentages.items():
        print(f"{category}: {percentage:.1f}%")

    print()

    print("Distance statistics:")
    print(
        "Minimum:",
        round(result["distance_km"].min(), 2),
        "km",
    )
    print(
        "Mean:",
        round(result["distance_km"].mean(), 2),
        "km",
    )
    print(
        "Median:",
        round(result["distance_km"].median(), 2),
        "km",
    )
    print(
        "Maximum:",
        round(result["distance_km"].max(), 2),
        "km",
    )


if __name__ == "__main__":
    main()