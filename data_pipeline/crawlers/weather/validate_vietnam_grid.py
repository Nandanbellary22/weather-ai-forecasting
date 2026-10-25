
"""Read-only validation of the Vietnam weather grid using pinned boundaries."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from shapely.geometry import Point, shape
from shapely.ops import unary_union


ROOT = Path(__file__).resolve().parents[3]

GRID_FILE = ROOT / "data/config/vietnam_weather_grid_500.csv"
SEED_FILE = ROOT / "data/config/vietnam_locations.csv"

# GADM 4.1 is the primary boundary used to generate the existing grid.
BOUNDARY_FILE = (
    ROOT / "data/config/boundaries/"
    "vietnam_gadm41_adm0.json"
)
METADATA_FILE = (
    ROOT / "data/config/boundaries/"
    "vietnam_gadm41_adm0.metadata.json"
)

# Retain geoBoundaries as an independent comparison dataset.
GEOBOUNDARIES_FILE = (
    ROOT / "data/config/boundaries/"
    "vietnam_gbopen_vnm_adm0_2016.geojson"
)
GEOBOUNDARIES_METADATA_FILE = (
    ROOT / "data/config/boundaries/"
    "vietnam_gbopen_vnm_adm0_2016.metadata.json"
)

GADM_URL = (
    "https://geodata.ucdavis.edu/gadm/gadm4.1/json/"
    "gadm41_VNM_0.json"
)

EXPECTED_COUNT = 500
REQUIRED_COLUMNS = {"location_id", "latitude", "longitude"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _valid_geometry(boundary) -> None:
    if boundary is None or boundary.is_empty or not boundary.is_valid:
        raise ValueError("Boundary geometry must be non-empty and valid.")


def classify(point, boundary) -> str:
    if boundary.contains(point):
        return "strictly_interior"
    if boundary.boundary.covers(point):
        return "boundary_touching"
    return "outside"


def validate_grid_rows(
    rows,
    boundary,
    *,
    grid_sha256: str,
    boundary_sha256: str,
    run_timestamp_utc: str | None = None,
    expected_count: int | None = None,
    boundary_metadata: dict | None = None,
    boundary_details: dict | None = None,
) -> dict:
    """Classify grid rows without changing, filtering, or reordering them."""
    _valid_geometry(boundary)

    timestamp = run_timestamp_utc or (
        datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )
    rows = list(rows)

    classified = {
        "strictly_interior": [],
        "boundary_touching": [],
        "outside": [],
        "invalid_coordinate": [],
    }
    id_rows = {}
    coordinate_rows = {}
    invalid_ids = []
    points = []

    for row_number, row in enumerate(rows, start=2):
        missing = REQUIRED_COLUMNS - set(row)
        if missing:
            raise ValueError(
                f"Grid row {row_number} is missing columns: {sorted(missing)}"
            )

        location_id = str(row.get("location_id") or "").strip()
        id_entry = {
            "row_number": row_number,
            "latitude": None,
            "longitude": None,
        }

        if location_id:
            id_rows.setdefault(location_id, []).append(id_entry)
        else:
            invalid_ids.append({
                "row_number": row_number,
                "location_id": location_id,
            })

        raw_lat = row.get("latitude")
        raw_lon = row.get("longitude")

        try:
            latitude = float(raw_lat)
            longitude = float(raw_lon)
        except (TypeError, ValueError):
            latitude = longitude = None

        finite = (
            latitude is not None
            and longitude is not None
            and math.isfinite(latitude)
            and math.isfinite(longitude)
        )
        in_range = (
            finite
            and -90 <= latitude <= 90
            and -180 <= longitude <= 180
        )

        detail = {
            "row_number": row_number,
            "location_id": location_id,
            "latitude": latitude if finite else None,
            "longitude": longitude if finite else None,
        }

        if not in_range:
            detail["classification"] = "invalid_coordinate"
            detail["raw_latitude"] = (
                None if raw_lat is None else str(raw_lat)
            )
            detail["raw_longitude"] = (
                None if raw_lon is None else str(raw_lon)
            )
            classified["invalid_coordinate"].append(detail)
        else:
            id_entry["latitude"] = latitude
            id_entry["longitude"] = longitude

            coordinate_rows.setdefault(
                (latitude, longitude), []
            ).append(detail)

            point = Point(longitude, latitude)
            category = classify(point, boundary)
            detail["classification"] = category
            classified[category].append(detail)

        points.append(detail)

    duplicate_ids = [
        {"location_id": key, "rows": value}
        for key, value in id_rows.items()
        if len(value) > 1
    ]

    duplicate_coordinates = [
        {
            "latitude": coordinate[0],
            "longitude": coordinate[1],
            "rows": value,
        }
        for coordinate, value in coordinate_rows.items()
        if len(value) > 1
    ]

    counts = {key: len(value) for key, value in classified.items()}
    total = len(rows)
    expected_count_passed = (
        expected_count is None or total == expected_count
    )
    all_points_covered = (
        counts["outside"] == 0
        and counts["invalid_coordinate"] == 0
    )

    validation_passed = (
        all_points_covered
        and not duplicate_ids
        and not duplicate_coordinates
        and not invalid_ids
        and expected_count_passed
    )

    return {
        "report_version": 3,
        "run_timestamp_utc": timestamp,
        "grid_file_sha256": grid_sha256,
        "boundary_file_sha256": boundary_sha256,
        "boundary_metadata": boundary_metadata or {},
        "boundary_validation": boundary_details or {
            "geometry_type": boundary.geom_type,
            "is_empty": boundary.is_empty,
            "is_valid": boundary.is_valid,
            "bounds_longitude_latitude": list(boundary.bounds),
        },
        "membership_policy": (
            "Boundary-inclusive for coverage; boundary contacts are "
            "reported separately."
        ),
        "expected_grid_count": expected_count,
        "grid_count": total,
        "expected_grid_count_passed": expected_count_passed,
        "classification_counts": counts,
        "classified_point_count": sum(counts.values()),
        "all_points_covered_by_boundary": all_points_covered,
        "unique_location_id_count": len(id_rows),
        "unique_coordinate_count": len(coordinate_rows),
        "duplicate_location_ids": duplicate_ids,
        "duplicate_coordinates": duplicate_coordinates,
        "invalid_location_ids": invalid_ids,
        "points": points,
        "validation_passed": validation_passed,
    }


def load_geojson_boundary(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))

    if data.get("type") == "FeatureCollection":
        features = data.get("features", [])
    elif data.get("type") == "Feature":
        features = [data]
    else:
        raise ValueError(f"Unsupported GeoJSON structure: {path}")

    if not features:
        raise ValueError(f"No features found in {path}")

    geometries = []
    for feature in features:
        geometry_data = feature.get("geometry")
        if not geometry_data:
            raise ValueError(f"Feature has no geometry in {path}")

        geometry = shape(geometry_data)
        _valid_geometry(geometry)
        geometries.append(geometry)

    boundary = unary_union(geometries)
    _valid_geometry(boundary)
    return boundary, data, len(features)


def load_pinned_boundary(
    boundary_path: Path = BOUNDARY_FILE,
    metadata_path: Path = METADATA_FILE,
):
    """Load a local boundary and verify its checksum and metadata."""
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    actual_hash = sha256_file(boundary_path)

    if not metadata.get("sha256") or actual_hash != metadata["sha256"]:
        raise ValueError(
            f"Boundary checksum does not match metadata: {boundary_path}"
        )

    boundary, data, feature_count = load_geojson_boundary(boundary_path)

    checks = {
        "checksum_matches_metadata": True,
        "crs_matches_metadata": (
            data.get("crs") == metadata.get("declared_crs")
        ),
        "axis_order_is_longitude_latitude": (
            metadata.get("coordinate_axis_order")
            == ["longitude", "latitude"]
        ),
        "feature_count_matches_metadata": (
            feature_count == metadata.get("feature_count")
        ),
        "geometry_type_matches_metadata": (
            boundary.geom_type == metadata.get("geometry_type")
        ),
        "geometry_is_valid": boundary.is_valid,
        "geometry_is_nonempty": not boundary.is_empty,
    }

    if not all(checks.values()):
        raise ValueError(
            f"Boundary metadata validation failed for {boundary_path}: "
            f"{checks}"
        )

    details = {
        "checks": checks,
        "feature_count": feature_count,
        "geometry_type": boundary.geom_type,
        "is_empty": boundary.is_empty,
        "is_valid": boundary.is_valid,
        "bounds_longitude_latitude": list(boundary.bounds),
        "declared_crs": data.get("crs"),
    }
    return boundary, metadata, actual_hash, details


def load_grid(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if not reader.fieldnames:
            raise ValueError("Grid CSV has no header.")

        missing = REQUIRED_COLUMNS - set(reader.fieldnames)
        if missing:
            raise ValueError(
                f"Grid CSV is missing columns: {sorted(missing)}"
            )
        return list(reader)


def load_seeds():
    if not SEED_FILE.exists():
        return None

    with SEED_FILE.open(
        "r", encoding="utf-8-sig", newline=""
    ) as file:
        reader = csv.DictReader(file)
        required = {"location_id", "latitude", "longitude"}

        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            return None

        return list(reader)


def validate_files(
    grid_path: Path = GRID_FILE,
    boundary_path: Path = BOUNDARY_FILE,
    metadata_path: Path = METADATA_FILE,
    *,
    run_timestamp_utc: str | None = None,
) -> dict:
    """Validate the grid against a checksum-pinned boundary."""
    boundary, metadata, actual_hash, details = load_pinned_boundary(
        boundary_path, metadata_path
    )

    return validate_grid_rows(
        load_grid(grid_path),
        boundary,
        grid_sha256=sha256_file(grid_path),
        boundary_sha256=actual_hash,
        run_timestamp_utc=run_timestamp_utc,
        expected_count=EXPECTED_COUNT,
        boundary_metadata=metadata,
        boundary_details=details,
    )


def _compare_boundaries(rows, primary_boundary, comparison_boundary):
    """Report classification differences without changing primary results."""
    counts = {
        "strictly_interior": 0,
        "boundary_touching": 0,
        "outside": 0,
    }
    disagreements = []

    for row in rows:
        try:
            latitude = float(row["latitude"])
            longitude = float(row["longitude"])
        except (TypeError, ValueError, KeyError):
            continue

        if (
            not math.isfinite(latitude)
            or not math.isfinite(longitude)
            or not -90 <= latitude <= 90
            or not -180 <= longitude <= 180
        ):
            continue

        point = Point(longitude, latitude)
        primary_category = classify(point, primary_boundary)
        comparison_category = classify(point, comparison_boundary)
        counts[comparison_category] += 1

        if primary_category != comparison_category:
            disagreements.append({
                "location_id": str(row.get("location_id") or "").strip(),
                "latitude": latitude,
                "longitude": longitude,
                "primary_gadm_4_1": primary_category,
                "comparison_geoboundaries_2016": comparison_category,
            })

    return counts, disagreements


def comprehensive_report():
    """Validate against pinned GADM and compare local geoBoundaries data."""
    primary, metadata, primary_hash, primary_checks = load_pinned_boundary()
    rows = load_grid(GRID_FILE)

    base = validate_grid_rows(
        rows,
        primary,
        grid_sha256=sha256_file(GRID_FILE),
        boundary_sha256=primary_hash,
        expected_count=EXPECTED_COUNT,
        boundary_metadata=metadata,
        boundary_details=primary_checks,
    )

    grid_by_id = {
        str(row.get("location_id") or "").strip(): row
        for row in rows
    }
    seeds = load_seeds()
    missing_seeds = []
    mismatched_seeds = []

    if seeds is not None:
        for seed in seeds:
            seed_id = str(seed.get("location_id") or "").strip()
            grid_row = grid_by_id.get(seed_id)

            if grid_row is None:
                missing_seeds.append(seed_id)
                continue

            try:
                if (
                    float(seed["latitude"]) != float(grid_row["latitude"])
                    or float(seed["longitude"]) != float(grid_row["longitude"])
                ):
                    mismatched_seeds.append(seed_id)
            except (TypeError, ValueError, KeyError):
                mismatched_seeds.append(seed_id)

    structure_passed = (
        base["grid_count"] == EXPECTED_COUNT
        and not base["duplicate_location_ids"]
        and not base["duplicate_coordinates"]
        and not base["invalid_location_ids"]
        and base["classification_counts"]["invalid_coordinate"] == 0
    )

    primary_counts = base["classification_counts"]
    geographic_passed = (
        primary_counts["outside"] == 0
        and primary_counts["boundary_touching"] == 0
        and primary_counts["invalid_coordinate"] == 0
    )

    report = {
        "report_version": 3,
        "run_timestamp_utc": base["run_timestamp_utc"],
        "grid_count": base["grid_count"],
        "expected_grid_count": EXPECTED_COUNT,
        "grid_structure": {
            "expected_count_passed": base["expected_grid_count_passed"],
            "unique_nonempty_ids": (
                not base["duplicate_location_ids"]
                and not base["invalid_location_ids"]
            ),
            "unique_coordinates": not base["duplicate_coordinates"],
            "all_coordinates_valid": (
                primary_counts["invalid_coordinate"] == 0
            ),
            "duplicate_ids": base["duplicate_location_ids"],
            "duplicate_coordinates": base["duplicate_coordinates"],
            "invalid_rows": primary_counts["invalid_coordinate"],
        },
        "primary_boundary": {
            "dataset": metadata.get("dataset_name", "GADM Vietnam ADM0"),
            "version": metadata.get("version", "4.1"),
            "file": BOUNDARY_FILE.name,
            "sha256": primary_hash,
            "checks": primary_checks,
            "bounds_longitude_latitude": list(primary.bounds),
        },
        "pinned_boundary": {
            "dataset": metadata.get("dataset_name", "GADM Vietnam ADM0"),
            "sha256": primary_hash,
            "checks": primary_checks,
            "bounds_longitude_latitude": list(primary.bounds),
        },
        "primary_boundary_membership": {
            "counts": primary_counts,
            "outside_points": [
                {
                    "location_id": point["location_id"],
                    "row_number": point["row_number"],
                    "latitude": point["latitude"],
                    "longitude": point["longitude"],
                }
                for point in base["points"]
                if point["classification"] == "outside"
            ],
        },
        # Retain the former field name for consumers of report version 2.
        "pinned_boundary_membership": {
            "counts": primary_counts,
            "outside_points": [
                {
                    "location_id": point["location_id"],
                    "row_number": point["row_number"],
                    "latitude": point["latitude"],
                    "longitude": point["longitude"],
                }
                for point in base["points"]
                if point["classification"] == "outside"
            ],
        },
        "seed_preservation": {
            "seed_file_exists": SEED_FILE.exists(),
            "seed_file_readable": seeds is not None,
            "seed_count": len(seeds) if seeds is not None else None,
            "missing_seed_ids": missing_seeds,
            "coordinate_mismatches": mismatched_seeds,
        },
        "original_gadm_comparison": {
            "source_url": GADM_URL,
            "comparison_completed": True,
            "counts": primary_counts,
            "boundary_disagreement_count": 0,
            "boundary_disagreements": [],
            "note": (
                "The checksum-pinned local GADM 4.1 boundary is the primary "
                "validation source; no live download is used."
            ),
        },
        "geoboundaries_comparison": {
            "comparison_completed": False,
            "error": None,
        },
        "warnings": [],
        "errors": [],
        "overall_structural_status": (
            "PASS" if structure_passed else "FAIL"
        ),
        "overall_geographic_status": (
            "PASS" if geographic_passed else "REVIEW_REQUIRED"
        ),
    }

    try:
        comparison, comparison_metadata, comparison_hash, comparison_checks = (
            load_pinned_boundary(
                GEOBOUNDARIES_FILE,
                GEOBOUNDARIES_METADATA_FILE,
            )
        )
        comparison_counts, disagreements = _compare_boundaries(
            rows, primary, comparison
        )

        report["geoboundaries_comparison"] = {
            "source": comparison_metadata.get(
                "dataset_name", "geoBoundaries Vietnam ADM0"
            ),
            "artifact_file": GEOBOUNDARIES_FILE.name,
            "sha256": comparison_hash,
            "checks": comparison_checks,
            "comparison_completed": True,
            "counts": comparison_counts,
            "boundary_disagreement_count": len(disagreements),
            "boundary_disagreements": disagreements,
            "note": (
                "Differences from geoBoundaries are diagnostic only. "
                "Primary grid validation uses the pinned GADM 4.1 boundary."
            ),
        }

        if disagreements:
            report["warnings"].append(
                "Grid classifications differ between GADM 4.1 and "
                f"geoBoundaries for {len(disagreements)} points."
            )

    except (OSError, ValueError, json.JSONDecodeError, KeyError, TypeError) as exc:
        report["geoboundaries_comparison"]["error"] = str(exc)
        report["warnings"].append(
            "The local geoBoundaries comparison could not be completed; "
            "primary GADM validation remains available."
        )

    if not geographic_passed:
        report["warnings"].append(
            "Some grid points are outside or touch the primary GADM boundary; "
            "inspect primary_boundary_membership."
        )

    if seeds is None:
        report["warnings"].append(
            "The seed file is missing or does not contain the required columns."
        )
    elif missing_seeds or mismatched_seeds:
        report["warnings"].append(
            "Seed locations are missing from the grid or have different coordinates."
        )

    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate the Vietnam weather grid."
    )
    parser.add_argument("--grid", type=Path, default=GRID_FILE)
    parser.add_argument("--boundary", type=Path, default=BOUNDARY_FILE)
    parser.add_argument("--metadata", type=Path, default=METADATA_FILE)
    parser.add_argument(
        "--comprehensive",
        action="store_true",
        help=(
            "Also check seed preservation and compare the pinned GADM "
            "boundary with the local geoBoundaries dataset."
        ),
    )
    args = parser.parse_args(argv)

    try:
        if args.comprehensive:
            report = comprehensive_report()
        else:
            report = validate_files(
                args.grid,
                args.boundary,
                args.metadata,
            )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({
            "validation_passed": False,
            "error": str(exc),
        }, ensure_ascii=False))
        return 1

    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))

    if args.comprehensive:
        return 0 if (
            report["overall_structural_status"] == "PASS"
            and report["overall_geographic_status"] == "PASS"
        ) else 1

    return 0 if report["validation_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
