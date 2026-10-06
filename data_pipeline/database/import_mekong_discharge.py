import io
import os
import zipfile

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values


ZIP_PATH = "data/processed/mekong_discharge_2005_2015.zip"

TABLE_NAME = "mekong_discharge_observations"

SOURCE_NAME = (
    "CEH/NERC Water and suspended sediment discharges "
    "for the Mekong Delta, Vietnam (2005-2015)"
)

SOURCE_FILES = {
    "Tan Chau": "data/Tanchauratings.csv",
    "Chau Doc": "data/Chaudocratings.csv",
    "Can Tho": "data/Canthoratings.csv",
    "My Thuan": "data/Mythaunratings.csv",
}


def get_connection():
    """
    Use the same PostgreSQL connection convention as the existing project.
    """
    return psycopg2.connect(
        host="localhost",
        port=5432,
        dbname="weather_forecasting",
        user="postgres",
        password=os.environ.get("PGPASSWORD"),
    )


def create_table(conn):
    """
    Create the discharge observation table if it does not already exist.
    """

    sql = f"""
    CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
        id BIGSERIAL PRIMARY KEY,

        station_name VARCHAR(100) NOT NULL,

        observation_date DATE,

        month INTEGER,
        day INTEGER,

        source_year_original INTEGER,
        source_year_normalized INTEGER,

        discharge_m3s DOUBLE PRECISION,
        suspended_sediment_mg_l DOUBLE PRECISION,
        sediment_flux_kg_s DOUBLE PRECISION,

        quality_flag VARCHAR(100),

        source_file VARCHAR(255) NOT NULL,
        source VARCHAR(255) NOT NULL,

        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """

    with conn.cursor() as cur:
        cur.execute(sql)

    conn.commit()


def read_rating_file(zip_file, station_name, source_file):
    """
    Read one rating CSV from the official CEH/NERC ZIP dataset.

    Raw source values are preserved. No source values are overwritten.
    """

    raw = zip_file.read(source_file)

    df = pd.read_csv(io.BytesIO(raw))

    required_columns = [
        "Month",
        "Day",
        "Year",
        "Discharge (m3/s)",
        "Section Averaged SSC (mg/l)",
        "Sediment Flux (kg/s)",
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing_columns:
        raise ValueError(
            f"{station_name}: missing required columns: {missing_columns}"
        )

    df = df[required_columns].copy()

    df["station_name"] = station_name
    df["source_file"] = source_file
    df["source"] = SOURCE_NAME

    return df


def normalize_year(df):
    """
    Preserve the original source year while creating a normalized year.

    Can Tho contains Year=10 for 152 records. We deliberately DO NOT
    silently convert this to 2010 because the source already contains
    legitimate Year=2010 observations.

    Those records are retained and flagged as source_year_anomaly.
    """

    df["source_year_original"] = pd.to_numeric(
        df["Year"],
        errors="coerce",
    ).astype("Int64")

    df["source_year_normalized"] = df["source_year_original"]

    anomaly_mask = df["source_year_original"] == 10

    df.loc[anomaly_mask, "source_year_normalized"] = pd.NA

    df["quality_flag"] = "valid"

    df.loc[
        anomaly_mask,
        "quality_flag",
    ] = "source_year_anomaly"

    return df


def build_observation_dates(df):
    """
    Construct dates only when the source year is usable.

    Invalid/anomalous source years retain a NULL observation_date.
    """

    dates = pd.Series(
        pd.NaT,
        index=df.index,
        dtype="datetime64[ns]",
    )

    valid_year = df["source_year_normalized"].notna()

    if valid_year.any():
        date_parts = pd.DataFrame(
            {
                "year": (
                    df.loc[
                        valid_year,
                        "source_year_normalized",
                    ]
                    .astype(int)
                ),
                "month": (
                    df.loc[
                        valid_year,
                        "Month",
                    ]
                    .astype(int)
                ),
                "day": (
                    df.loc[
                        valid_year,
                        "Day",
                    ]
                    .astype(int)
                ),
            },
            index=df.index[valid_year],
        )

        dates.loc[valid_year] = pd.to_datetime(
            date_parts,
            errors="coerce",
        )

    invalid_date = (
        df["source_year_normalized"].notna()
        & dates.isna()
    )

    df.loc[
        invalid_date,
        "quality_flag",
    ] = "invalid_date"

    df["observation_date"] = dates.dt.date

    return df


def prepare_dataframe(df):
    """
    Prepare a rating dataframe for database insertion.
    """

    df = normalize_year(df)

    df = build_observation_dates(df)

    df["month"] = pd.to_numeric(
        df["Month"],
        errors="coerce",
    ).astype("Int64")

    df["day"] = pd.to_numeric(
        df["Day"],
        errors="coerce",
    ).astype("Int64")

    df["discharge_m3s"] = pd.to_numeric(
        df["Discharge (m3/s)"],
        errors="coerce",
    )

    df["suspended_sediment_mg_l"] = pd.to_numeric(
        df["Section Averaged SSC (mg/l)"],
        errors="coerce",
    )

    df["sediment_flux_kg_s"] = pd.to_numeric(
        df["Sediment Flux (kg/s)"],
        errors="coerce",
    )

    negative_discharge = (
        df["discharge_m3s"].notna()
        & (df["discharge_m3s"] < 0)
    )

    df.loc[
        negative_discharge,
        "quality_flag",
    ] = "invalid_discharge"

    return df


def validate_dataframe(df):
    """
    Perform source-level validation before database insertion.
    """

    print()
    print("=" * 70)
    print("DISCHARGE DATA VALIDATION")
    print("=" * 70)

    print(f"Rows: {len(df):,}")
    print(f"Stations: {df['station_name'].nunique()}")

    print()
    print("Rows by station:")

    station_counts = (
        df.groupby("station_name")
        .size()
        .sort_index()
    )

    for station, count in station_counts.items():
        print(f"  {station}: {count:,}")

    print()
    print("Missing values:")

    for column in [
        "observation_date",
        "discharge_m3s",
        "suspended_sediment_mg_l",
        "sediment_flux_kg_s",
    ]:
        print(
            f"  {column}: "
            f"{df[column].isna().sum():,}"
        )

    print()
    print("Quality flags:")

    quality_counts = (
        df["quality_flag"]
        .value_counts(dropna=False)
        .sort_index()
    )

    for flag, count in quality_counts.items():
        print(f"  {flag}: {count:,}")

    print()
    print("Discharge range:")

    valid_discharge = df["discharge_m3s"].dropna()

    if not valid_discharge.empty:
        print(
            f"  Minimum: {valid_discharge.min():.6f} m3/s"
        )
        print(
            f"  Maximum: {valid_discharge.max():.6f} m3/s"
        )

    print()
    print("Date coverage by station:")

    for station, group in df.groupby("station_name"):
        valid_dates = group["observation_date"].dropna()

        if valid_dates.empty:
            print(f"  {station}: no valid dates")
        else:
            print(
                f"  {station}: "
                f"{valid_dates.min()} -> "
                f"{valid_dates.max()}"
            )

    print()
    print(
        "Can Tho Year=10 anomalies:",
        (
            (
                (df["station_name"] == "Can Tho")
                & (df["source_year_original"] == 10)
            )
            .sum()
        ),
    )

    print("=" * 70)


def to_python_value(value):
    """
    Convert Pandas/NumPy scalar values to native Python values
    accepted by psycopg2.

    NaN/NA/NaT are converted to None.
    """

    if pd.isna(value):
        return None

    if hasattr(value, "item"):
        try:
            value = value.item()
        except (ValueError, AttributeError):
            pass

    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()

    return value


def insert_data(conn, df):
    """
    Insert observations using batch insertion.

    Multiple observations on the same date are preserved because
    they are legitimate observations in the source rating datasets.
    """

    columns = [
        "station_name",
        "observation_date",
        "month",
        "day",
        "source_year_original",
        "source_year_normalized",
        "discharge_m3s",
        "suspended_sediment_mg_l",
        "sediment_flux_kg_s",
        "quality_flag",
        "source_file",
        "source",
    ]

    rows = []

    for row in df[columns].itertuples(
        index=False,
        name=None,
    ):
        rows.append(
            tuple(
                to_python_value(value)
                for value in row
            )
        )

    sql = f"""
    INSERT INTO {TABLE_NAME} (
        station_name,
        observation_date,
        month,
        day,
        source_year_original,
        source_year_normalized,
        discharge_m3s,
        suspended_sediment_mg_l,
        sediment_flux_kg_s,
        quality_flag,
        source_file,
        source
    )
    VALUES %s
    """

    with conn.cursor() as cur:
        execute_values(
            cur,
            sql,
            rows,
            page_size=1000,
        )

    conn.commit()

    return len(rows)


def print_database_summary(conn):
    """
    Print the final database summary.
    """

    print()
    print("=" * 70)
    print("DATABASE SUMMARY")
    print("=" * 70)

    with conn.cursor() as cur:

        cur.execute(
            f"""
            SELECT COUNT(*)
            FROM {TABLE_NAME}
            """
        )

        total_rows = cur.fetchone()[0]

        print(
            f"Total observations: {total_rows:,}"
        )

        cur.execute(
            f"""
            SELECT
                station_name,
                COUNT(*),
                MIN(observation_date),
                MAX(observation_date)
            FROM {TABLE_NAME}
            GROUP BY station_name
            ORDER BY station_name
            """
        )

        print()
        print("Station coverage:")

        for station, count, minimum, maximum in cur.fetchall():
            print(
                f"  {station}: "
                f"{count:,} rows | "
                f"{minimum} -> {maximum}"
            )

        cur.execute(
            f"""
            SELECT quality_flag, COUNT(*)
            FROM {TABLE_NAME}
            GROUP BY quality_flag
            ORDER BY quality_flag
            """
        )

        print()
        print("Quality flags in database:")

        for flag, count in cur.fetchall():
            print(
                f"  {flag}: {count:,}"
            )

    print("=" * 70)


def main():
    print("=" * 70)
    print("MEKONG DISCHARGE IMPORTER")
    print("=" * 70)

    if not os.path.exists(ZIP_PATH):
        raise FileNotFoundError(
            f"Source ZIP not found: {ZIP_PATH}"
        )

    print(f"Source: {ZIP_PATH}")
    print(f"Target table: {TABLE_NAME}")

    all_frames = []

    with zipfile.ZipFile(ZIP_PATH, "r") as zip_file:

        available_files = set(
            zip_file.namelist()
        )

        print()
        print("Reading official rating files:")

        for station_name, source_file in SOURCE_FILES.items():

            if source_file not in available_files:
                raise FileNotFoundError(
                    "Missing source file in ZIP: "
                    f"{source_file}"
                )

            print(
                f"  {station_name}: "
                f"{source_file}"
            )

            df = read_rating_file(
                zip_file,
                station_name,
                source_file,
            )

            df = prepare_dataframe(df)

            all_frames.append(df)

    combined = pd.concat(
        all_frames,
        ignore_index=True,
    )

    validate_dataframe(combined)

    conn = get_connection()

    try:
        create_table(conn)

        inserted = insert_data(
            conn,
            combined,
        )

        print()
        print(
            f"Inserted observations: {inserted:,}"
        )

        print_database_summary(conn)

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()

    print()
    print("Import completed successfully.")


if __name__ == "__main__":
    main()