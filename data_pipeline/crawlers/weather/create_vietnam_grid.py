from pathlib import Path

import numpy as np
import pandas as pd
import requests
from shapely.geometry import Point, shape
from shapely.ops import unary_union


# ---------------------------------------------------------
# Paths
# ---------------------------------------------------------

EXISTING_FILE = Path("data/config/vietnam_locations.csv")
OUTPUT_FILE = Path("data/config/vietnam_weather_grid_500.csv")

TARGET_POINTS = 500

BOUNDARY_URL = (
    "https://geodata.ucdavis.edu/gadm/gadm4.1/json/"
    "gadm41_VNM_0.json"
)


# ---------------------------------------------------------
# Load Vietnam boundary
# ---------------------------------------------------------

def load_vietnam_boundary():
    print("Downloading Vietnam boundary...")

    response = requests.get(
        BOUNDARY_URL,
        timeout=60,
    )
    response.raise_for_status()

    data = response.json()

    geometries = [
        shape(feature["geometry"])
        for feature in data["features"]
    ]

    boundary = unary_union(geometries)

    if boundary.is_empty:
        raise RuntimeError(
            "Vietnam boundary geometry is empty."
        )

    print("Vietnam boundary loaded.")

    return boundary


# ---------------------------------------------------------
# Load existing locations
# ---------------------------------------------------------

def load_existing_locations():
    df = pd.read_csv(EXISTING_FILE)

    required = {
        "location_id",
        "location_name",
        "latitude",
        "longitude",
    }

    missing = required - set(df.columns)

    if missing:
        raise ValueError(
            f"Missing columns in {EXISTING_FILE}: {missing}"
        )

    df["location_id"] = (
        df["location_id"]
        .astype(str)
        .str.strip()
    )

    df["location_name"] = (
        df["location_name"]
        .astype(str)
        .str.strip()
    )

    df["latitude"] = pd.to_numeric(
        df["latitude"],
        errors="coerce",
    )

    df["longitude"] = pd.to_numeric(
        df["longitude"],
        errors="coerce",
    )

    df = df.dropna(
        subset=["latitude", "longitude"]
    )

    print(
        f"Existing locations loaded: {len(df)}"
    )

    return df


# ---------------------------------------------------------
# Generate candidate land points
# ---------------------------------------------------------

def generate_candidates(boundary):
    min_lon, min_lat, max_lon, max_lat = (
        boundary.bounds
    )

    # Dense enough to give us many candidate points.
    spacing = 0.15

    lats = np.arange(
        min_lat,
        max_lat + spacing,
        spacing,
    )

    lons = np.arange(
        min_lon,
        max_lon + spacing,
        spacing,
    )

    candidates = []

    print(
        f"Candidate grid: "
        f"{len(lats)} latitudes × "
        f"{len(lons)} longitudes"
    )

    for lat in lats:
        for lon in lons:

            point = Point(
                float(lon),
                float(lat),
            )

            if boundary.contains(point):
                candidates.append(
                    (
                        float(lat),
                        float(lon),
                    )
                )

    print(
        f"Land candidates generated: "
        f"{len(candidates)}"
    )

    return np.array(
        candidates,
        dtype=float,
    )


# ---------------------------------------------------------
# Remove candidates too close to existing locations
# ---------------------------------------------------------

def remove_existing_points(
    candidates,
    existing,
):
    existing_coords = existing[
        ["latitude", "longitude"]
    ].to_numpy(dtype=float)

    filtered = []

    minimum_distance = 0.03

    for lat, lon in candidates:

        distances = np.sqrt(
            (existing_coords[:, 0] - lat) ** 2
            +
            (existing_coords[:, 1] - lon) ** 2
        )

        if distances.min() >= minimum_distance:
            filtered.append(
                (lat, lon)
            )

    return np.array(
        filtered,
        dtype=float,
    )


# ---------------------------------------------------------
# Select spatially distributed points
# ---------------------------------------------------------

def select_spatial_points(
    candidates,
    existing,
    target_count,
):
    existing_coords = existing[
        ["latitude", "longitude"]
    ].to_numpy(dtype=float)

    selected = []

    # Start with existing locations.
    selected.extend(
        [
            tuple(point)
            for point in existing_coords
        ]
    )

    remaining = candidates.copy()

    required_new = (
        target_count
        - len(selected)
    )

    if required_new <= 0:
        return np.array(
            selected[:target_count],
            dtype=float,
        )

    print(
        f"Selecting {required_new} "
        f"additional grid points..."
    )

    # Farthest-point sampling.
    #
    # This spreads the selected points across
    # the country instead of clustering them.

    selected_array = np.array(
        selected,
        dtype=float,
    )

    distances = np.full(
        len(remaining),
        np.inf,
    )

    for index, candidate in enumerate(
        remaining
    ):
        d = np.sqrt(
            (
                selected_array[:, 0]
                - candidate[0]
            ) ** 2
            +
            (
                selected_array[:, 1]
                - candidate[1]
            ) ** 2
        )

        distances[index] = d.min()

    for _ in range(required_new):

        index = int(
            np.argmax(distances)
        )

        point = remaining[index]

        selected.append(
            tuple(point)
        )

        # Update distances from the newly
        # selected point.
        d = np.sqrt(
            (
                remaining[:, 0]
                - point[0]
            ) ** 2
            +
            (
                remaining[:, 1]
                - point[1]
            ) ** 2
        )

        distances = np.minimum(
            distances,
            d,
        )

        distances[index] = -np.inf

    return np.array(
        selected,
        dtype=float,
    )


# ---------------------------------------------------------
# Build final dataframe
# ---------------------------------------------------------

def build_dataframe(
    selected,
    existing,
):
    existing_ids = set(
        existing["location_id"]
    )

    rows = []

    # Preserve original locations exactly.
    for _, row in existing.iterrows():

        rows.append(
            {
                "location_id": row["location_id"],
                "location_name": row["location_name"],
                "latitude": row["latitude"],
                "longitude": row["longitude"],
            }
        )

    # Add generated locations.
    generated_index = 1

    for lat, lon in selected:

        # Skip if this coordinate corresponds
        # to an existing location.
        distances = np.sqrt(
            (
                existing["latitude"].to_numpy()
                - lat
            ) ** 2
            +
            (
                existing["longitude"].to_numpy()
                - lon
            ) ** 2
        )

        if distances.min() < 0.03:
            continue

        location_id = (
            f"GRID_{generated_index:04d}"
        )

        while location_id in existing_ids:
            generated_index += 1
            location_id = (
                f"GRID_{generated_index:04d}"
            )

        rows.append(
            {
                "location_id": location_id,
                "location_name": (
                    f"Vietnam Grid "
                    f"{generated_index:04d}"
                ),
                "latitude": round(
                    float(lat),
                    6,
                ),
                "longitude": round(
                    float(lon),
                    6,
                ),
            }
        )

        existing_ids.add(location_id)

        generated_index += 1

    df = pd.DataFrame(rows)

    return df


# ---------------------------------------------------------
# Validation
# ---------------------------------------------------------

def validate(df):
    print()
    print("Final validation")
    print("----------------")

    print(
        f"Total locations: {len(df)}"
    )

    print(
        f"Unique location IDs: "
        f"{df['location_id'].nunique()}"
    )

    print(
        f"Duplicate coordinates: "
        f"{df.duplicated(['latitude', 'longitude']).sum()}"
    )

    print(
        f"Latitude range: "
        f"{df['latitude'].min():.4f} "
        f"to "
        f"{df['latitude'].max():.4f}"
    )

    print(
        f"Longitude range: "
        f"{df['longitude'].min():.4f} "
        f"to "
        f"{df['longitude'].max():.4f}"
    )

    print()
    print("First 20 locations:")
    print(
        df.head(20).to_string(
            index=False
        )
    )


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

def main():

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    existing = load_existing_locations()

    boundary = load_vietnam_boundary()

    candidates = generate_candidates(
        boundary
    )

    candidates = remove_existing_points(
        candidates,
        existing,
    )

    print(
        f"Candidates after removing "
        f"existing locations: "
        f"{len(candidates)}"
    )

    selected = select_spatial_points(
        candidates,
        existing,
        TARGET_POINTS,
    )

    df = build_dataframe(
        selected,
        existing,
    )

    # Ensure exactly TARGET_POINTS if enough
    # valid candidates were available.
    if len(df) > TARGET_POINTS:
        df = df.head(TARGET_POINTS)

    df.to_csv(
        OUTPUT_FILE,
        index=False,
    )

    validate(df)

    print()
    print(
        f"Saved grid to:\n{OUTPUT_FILE}"
    )


if __name__ == "__main__":
    main()