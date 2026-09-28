from __future__ import annotations

import os
from pathlib import Path

import h5py
import numpy as np
import requests
from dotenv import load_dotenv


# ============================================================
# PROJECT PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[3]

RAW_DIR = PROJECT_ROOT / "data" / "raw" / "imerg"


# ============================================================
# NASA CMR
# ============================================================

CMR_COLLECTION_SEARCH_URL = (
    "https://cmr.earthdata.nasa.gov/search/collections.umm_json"
)

CMR_GRANULE_SEARCH_URL = (
    "https://cmr.earthdata.nasa.gov/search/granules.umm_json"
)


# ============================================================
# IMERG COLLECTION
# ============================================================

COLLECTION_SHORT_NAME = "GPM_3IMERGHHL"
COLLECTION_VERSION = "07"

# One day only for this first test.
SEARCH_DATE = "2026-07-13"


# ============================================================
# CREDENTIALS
# ============================================================


def load_credentials() -> tuple[str, str]:
    """
    Load Earthdata credentials from the project .env file.

    Only the username and token are loaded.
    Credentials are never printed.
    """

    env_file = PROJECT_ROOT / ".env"

    load_dotenv(env_file)

    username = os.getenv("EARTHDATA_USERNAME")
    token = os.getenv("EARTHDATA_TOKEN")

    if not username:
        raise RuntimeError(
            "EARTHDATA_USERNAME is missing from .env"
        )

    if not token:
        raise RuntimeError(
            "EARTHDATA_TOKEN is missing from .env"
        )

    return username, token


# ============================================================
# COLLECTION DISCOVERY
# ============================================================


def find_collection() -> dict:
    """
    Find the official NASA CMR collection.
    """

    params = {
        "short_name": COLLECTION_SHORT_NAME,
        "version": COLLECTION_VERSION,
        "page_size": 20,
    }

    response = requests.get(
        CMR_COLLECTION_SEARCH_URL,
        params=params,
        timeout=60,
    )

    response.raise_for_status()

    data = response.json()

    items = data.get("items", [])

    if not items:
        raise RuntimeError(
            "NASA CMR collection was not found."
        )

    collection = items[0]

    concept_id = (
        collection
        .get("meta", {})
        .get("concept-id")
    )

    # CMR metadata structure can vary, so don't assume
    # temporal coverage is always present.
    temporal_start = None
    temporal_end = None

    try:
        temporal_extents = (
            collection
            .get("umm", {})
            .get("TemporalExtents", [])
        )

        if temporal_extents:
            range_datetime = (
                temporal_extents[0]
                .get("RangeDateTime", {})
            )

            temporal_start = range_datetime.get(
                "BeginningDateTime"
            )

            temporal_end = range_datetime.get(
                "EndingDateTime"
            )
    except Exception:
        pass

    print(
        f"NASA CMR collection: "
        f"{COLLECTION_SHORT_NAME}"
    )

    print(
        f"Collection concept ID: "
        f"{concept_id}"
    )

    print(
        "Collection temporal coverage: "
        f"{temporal_start} to "
        f"{temporal_end or 'unknown'}"
    )

    return collection


# ============================================================
# GRANULE SEARCH
# ============================================================


def search_granules() -> list[dict]:
    """
    Search NASA CMR for IMERG granules on one UTC day.
    """

    start_time = f"{SEARCH_DATE}T00:00:00Z"
    end_time = f"{SEARCH_DATE}T23:59:59Z"

    params = {
        "short_name": COLLECTION_SHORT_NAME,
        "version": COLLECTION_VERSION,
        "temporal": f"{start_time},{end_time}",
        "page_size": 100,
    }

    print(
        "NASA CMR granule search: "
        f"{CMR_GRANULE_SEARCH_URL}"
    )

    print(
        f"Search date (UTC): {SEARCH_DATE}"
    )

    print(
        f"Collection short name: "
        f"{COLLECTION_SHORT_NAME}"
    )

    print(
        f"Collection version: "
        f"{COLLECTION_VERSION}"
    )

    response = requests.get(
        CMR_GRANULE_SEARCH_URL,
        params=params,
        timeout=60,
    )

    response.raise_for_status()

    data = response.json()

    granules = data.get("items", [])

    print(
        f"NASA CMR granules returned: "
        f"{len(granules)}"
    )

    if not granules:
        raise RuntimeError(
            "NASA CMR returned zero IMERG granules."
        )

    return granules


# ============================================================
# GRANULE URL EXTRACTION
# ============================================================


def extract_granule_url(granule: dict) -> str | None:
    """
    Extract a GES DISC data URL from one CMR granule.
    """

    links = (
        granule
        .get("umm", {})
        .get("RelatedUrls", [])
    )

    # Preferred: explicit GET DATA link.
    for link in links:

        url = link.get("URL", "")
        url_type = link.get("Type", "").upper()

        if (
            url.startswith(
                "https://data.gesdisc.earthdata.nasa.gov/"
            )
            and "GET DATA" in url_type
        ):
            return url

    # Fallback: any GES DISC data URL.
    for link in links:

        url = link.get("URL", "")

        if url.startswith(
            "https://data.gesdisc.earthdata.nasa.gov/"
        ):
            return url

    return None


# ============================================================
# SELECT ONE GRANULE
# ============================================================


def select_one_granule(
    granules: list[dict],
) -> tuple[str, str]:
    """
    Select exactly one granule.

    For the first test we intentionally download only
    one 30-minute IMERG granule.
    """

    candidates = []

    for granule in granules:

        url = extract_granule_url(granule)

        if not url:
            continue

        granule_id = (
            granule
            .get("meta", {})
            .get("native-id")
            or granule
            .get("umm", {})
            .get("GranuleUR")
            or "unknown"
        )

        candidates.append(
            (
                granule_id,
                url,
            )
        )

    if not candidates:
        raise RuntimeError(
            "CMR returned granules, but no GES DISC "
            "download URL was found."
        )

    print()
    print("First NASA CMR granule URLs:")

    for _, url in candidates[:5]:
        print(f"  {url}")

    selected_id, selected_url = candidates[0]

    filename = Path(
        selected_url.split("?", 1)[0]
    ).name

    print()
    print(
        f"Selected exactly one granule: "
        f"{filename}"
    )

    return filename, selected_url


# ============================================================
# DOWNLOAD ONE FILE
# ============================================================


def download_one(
    session: requests.Session,
    token: str,
    url: str,
    filename: str,
) -> Path:
    """
    Download exactly one IMERG granule.

    Important NASA/GES DISC behavior:

        GES DISC
            |
            | 303 redirect
            v
        temporary signed CloudFront URL
            |
            v
        HDF5 file

    We therefore DO NOT allow requests to follow
    the first redirect automatically.

    We capture Location and request the signed URL
    separately.
    """

    RAW_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path = RAW_DIR / filename

    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "weather-ai-forecasting/1.0",
        "Accept": "*/*",
    }

    print()
    print(
        "Requesting GES DISC download authorization..."
    )

    # --------------------------------------------------------
    # STEP 1: GES DISC
    # --------------------------------------------------------

    response = session.get(
        url,
        headers=headers,
        allow_redirects=False,
        timeout=60,
    )

    print(
        f"GES DISC HTTP status: "
        f"{response.status_code}"
    )

    if response.status_code not in (
        301,
        302,
        303,
        307,
        308,
    ):
        raise RuntimeError(
            "GES DISC did not return a download redirect.\n"
            f"HTTP status: {response.status_code}\n"
            f"URL: {response.url}"
        )

    signed_url = response.headers.get(
        "Location"
    )

    if not signed_url:
        raise RuntimeError(
            "GES DISC returned a redirect but "
            "no Location header was provided."
        )

    print(
        "GES DISC returned a signed download URL."
    )

    # --------------------------------------------------------
    # STEP 2: SIGNED CLOUD FRONT URL
    # --------------------------------------------------------

    print(
        "Downloading from the signed CloudFront URL..."
    )

    # IMPORTANT:
    # Do NOT send the Earthdata Bearer token here.
    #
    # The signed URL already contains the temporary
    # authorization parameters.
    download_response = session.get(
        signed_url,
        allow_redirects=False,
        timeout=180,
    )

    print(
        "CloudFront download HTTP status: "
        f"{download_response.status_code}"
    )

    if download_response.status_code != 200:

        raise RuntimeError(
            "CloudFront download failed.\n"
            f"HTTP status: "
            f"{download_response.status_code}\n"
            f"Content-Type: "
            f"{download_response.headers.get('Content-Type')}"
        )

    content = download_response.content

    if not content:

        raise RuntimeError(
            "CloudFront returned an empty response."
        )

    # --------------------------------------------------------
    # VERIFY HDF5
    # --------------------------------------------------------

    hdf5_magic = b"\x89HDF\r\n\x1a\n"

    if not content.startswith(hdf5_magic):

        preview = content[:200].decode(
            "utf-8",
            errors="replace",
        )

        raise RuntimeError(
            "HTTP 200 was returned, but the response "
            "does not appear to be an HDF5 file.\n"
            f"Content-Type: "
            f"{download_response.headers.get('Content-Type')}\n"
            f"Response preview: {preview}"
        )

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    output_path.write_bytes(content)

    print()
    print(
        f"Downloaded file: "
        f"{output_path}"
    )

    print(
        f"Downloaded size: "
        f"{len(content):,} bytes"
    )

    print(
        "Content-Type: "
        f"{download_response.headers.get('Content-Type')}"
    )

    return output_path


# ============================================================
# HDF5 DATASET INSPECTION
# ============================================================


def decode_attribute(value):

    if isinstance(value, bytes):

        return value.decode(
            "utf-8",
            errors="replace",
        )

    if isinstance(value, np.ndarray):

        if value.size == 1:
            return decode_attribute(
                value.reshape(-1)[0]
            )

    return value


def print_dataset_info(
    name: str,
    dataset: h5py.Dataset,
):
    """
    Print metadata for one HDF5 dataset.
    """

    print()
    print(
        f"  Dataset: {name}"
    )

    print(
        f"    dimensions: "
        f"{dataset.shape}"
    )

    print(
        f"    dtype: "
        f"{dataset.dtype}"
    )

    units = dataset.attrs.get(
        "units"
    )

    if units is not None:

        print(
            f"    units: "
            f"{decode_attribute(units)}"
        )

    fill_value = dataset.attrs.get(
        "_FillValue"
    )

    if fill_value is not None:

        print(
            f"    _FillValue: "
            f"{decode_attribute(fill_value)}"
        )


# ============================================================
# PRECIPITATION STATISTICS
# ============================================================


def precipitation_statistics(
    name: str,
    dataset: h5py.Dataset,
):
    """
    Calculate basic statistics for precipitation
    datasets.
    """

    try:

        values = dataset[...]

        values = np.asarray(
            values,
            dtype=np.float64,
        )

        total_count = values.size

        fill_value = dataset.attrs.get(
            "_FillValue"
        )

        if fill_value is not None:

            try:

                fill_value = float(
                    np.asarray(
                        fill_value
                    ).reshape(-1)[0]
                )

                valid_mask = (
                    values != fill_value
                )

            except Exception:

                valid_mask = np.ones(
                    values.shape,
                    dtype=bool,
                )

        else:

            valid_mask = np.ones(
                values.shape,
                dtype=bool,
            )

        finite_mask = np.isfinite(
            values
        )

        valid_mask = (
            valid_mask
            & finite_mask
        )

        valid_values = values[
            valid_mask
        ]

        missing_count = (
            total_count
            - valid_values.size
        )

        print()
        print(
            f"  Statistics for: {name}"
        )

        print(
            f"    total values: "
            f"{total_count:,}"
        )

        print(
            f"    valid values: "
            f"{valid_values.size:,}"
        )

        print(
            f"    missing/fill values: "
            f"{missing_count:,}"
        )

        if valid_values.size > 0:

            print(
                f"    minimum: "
                f"{float(valid_values.min())}"
            )

            print(
                f"    maximum: "
                f"{float(valid_values.max())}"
            )

            print(
                f"    mean: "
                f"{float(valid_values.mean())}"
            )

    except Exception as exc:

        print(
            f"    Could not calculate statistics: "
            f"{exc}"
        )


# ============================================================
# HDF5 INSPECTION
# ============================================================


def inspect_hdf5(
    path: Path,
):
    """
    Inspect the downloaded IMERG HDF5 file.
    """

    print()
    print("=" * 70)
    print("IMERG HDF5 INSPECTION")
    print("=" * 70)

    print(
        f"Filename: {path.name}"
    )

    print(
        f"Path: {path}"
    )

    print(
        f"File size: "
        f"{path.stat().st_size:,} bytes"
    )

    print(
        "Format: HDF5"
    )

    with h5py.File(
        path,
        "r",
    ) as h5:

        print()
        print(
            "Top-level groups/datasets:"
        )

        for key in h5.keys():

            print(
                f"  {key}"
            )

        datasets = []

        def visitor(
            name,
            obj,
        ):

            if isinstance(
                obj,
                h5py.Dataset,
            ):

                datasets.append(
                    (
                        name,
                        obj,
                    )
                )

        h5.visititems(
            visitor
        )

        print()
        print(
            f"Total datasets found: "
            f"{len(datasets)}"
        )

        print()
        print(
            "Dataset metadata:"
        )

        for name, dataset in datasets:

            print_dataset_info(
                name,
                dataset,
            )

        # ----------------------------------------------------
        # Find precipitation datasets
        # ----------------------------------------------------

        precipitation_datasets = []

        for name, dataset in datasets:

            lower_name = name.lower()

            if (
                "precipitation" in lower_name
                or "precipitationcal" in lower_name
                or "precipitationunclim" in lower_name
            ):

                precipitation_datasets.append(
                    (
                        name,
                        dataset,
                    )
                )

        print()
        print(
            "Detected precipitation datasets:"
        )

        if not precipitation_datasets:

            print(
                "  No precipitation dataset "
                "was detected automatically."
            )

        else:

            for name, dataset in (
                precipitation_datasets
            ):

                print(
                    f"  {name}"
                )

                precipitation_statistics(
                    name,
                    dataset,
                )


# ============================================================
# MAIN
# ============================================================


def main():

    print(
        "GPM IMERG Late Run CMR search, "
        "one-file download, and inspection"
    )

    # --------------------------------------------------------
    # Credentials
    # --------------------------------------------------------

    username, token = load_credentials()

    # Username is intentionally not printed.
    _ = username

    # --------------------------------------------------------
    # Collection
    # --------------------------------------------------------

    find_collection()

    # --------------------------------------------------------
    # Granules
    # --------------------------------------------------------

    granules = search_granules()

    # --------------------------------------------------------
    # Select exactly one
    # --------------------------------------------------------

    filename, selected_url = (
        select_one_granule(
            granules
        )
    )

    # --------------------------------------------------------
    # Download
    # --------------------------------------------------------

    session = requests.Session()

    downloaded_file = download_one(
        session=session,
        token=token,
        url=selected_url,
        filename=filename,
    )

    # --------------------------------------------------------
    # Inspect
    # --------------------------------------------------------

    inspect_hdf5(
        downloaded_file
    )

    print()
    print("=" * 70)
    print(
        "IMERG download and inspection "
        "completed successfully."
    )
    print("=" * 70)


if __name__ == "__main__":
    main()