import os
from pathlib import Path

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values


PROJECT_ROOT = Path(__file__).resolve().parents[1]

CSV_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "pctt_historical_180days_clean.csv"
)


DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "weather_forecasting",
    "user": "postgres",
}


PCTT_COLUMNS = [
    "htl1",
    "qvao1",
    "luuluongnhamay1",
    "qxaquacua1",
    "htl2",
    "qvao2",
    "luuluongnhamay2",
    "qxaquacua2",
    "htl3",
    "qvao3",
    "luuluongnhamay3",
    "qxaquacua3",
    "htl4",
    "qvao4",
    "luuluongnhamay4",
    "qxaquacua4",
    "qvevugia",
    "qvethubon",
]


def get_connection():
    password = os.getenv("POSTGRES_PASSWORD")

    if not password:
        raise RuntimeError(
            "POSTGRES_PASSWORD environment variable is not set."
        )

    return psycopg2.connect(
        host=DB_CONFIG["host"],
        port=DB_CONFIG["port"],
        database=DB_CONFIG["database"],
        user=DB_CONFIG["user"],
        password=password,
    )


def load_csv():
    print(f"Loading PCTT CSV: {CSV_PATH}")

    df = pd.read_csv(CSV_PATH)

    required_columns = {
        "timestamp",
        *PCTT_COLUMNS,
    }

    missing = required_columns - set(df.columns)

    if missing:
        raise ValueError(
            f"Missing required columns: {sorted(missing)}"
        )

    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        errors="coerce",
    )

    if df["timestamp"].isna().any():
        raise ValueError(
            "Clean PCTT CSV still contains invalid timestamps."
        )

    for column in PCTT_COLUMNS:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    duplicate_count = df.duplicated(
        subset=["timestamp"]
    ).sum()

    if duplicate_count:
        raise ValueError(
            f"Clean PCTT CSV contains "
            f"{duplicate_count} duplicate timestamps."
        )

    df = df.sort_values(
        "timestamp"
    ).reset_index(drop=True)

    print(f"Rows: {len(df)}")
    print(
        f"Time range: "
        f"{df['timestamp'].min()} "
        f"to "
        f"{df['timestamp'].max()}"
    )

    print(
        f"Missing numeric values: "
        f"{int(df[PCTT_COLUMNS].isna().sum().sum())}"
    )

    return df


def insert_data(df):
    connection = get_connection()

    try:
        with connection:
            with connection.cursor() as cursor:

                rows = []

                for row in df.itertuples(
                    index=False
                ):
                    rows.append(
                        (
                            row.timestamp,
                            None
                            if pd.isna(row.htl1)
                            else float(row.htl1),
                            None
                            if pd.isna(row.qvao1)
                            else float(row.qvao1),
                            None
                            if pd.isna(
                                row.luuluongnhamay1
                            )
                            else float(
                                row.luuluongnhamay1
                            ),
                            None
                            if pd.isna(
                                row.qxaquacua1
                            )
                            else float(
                                row.qxaquacua1
                            ),
                            None
                            if pd.isna(row.htl2)
                            else float(row.htl2),
                            None
                            if pd.isna(row.qvao2)
                            else float(row.qvao2),
                            None
                            if pd.isna(
                                row.luuluongnhamay2
                            )
                            else float(
                                row.luuluongnhamay2
                            ),
                            None
                            if pd.isna(
                                row.qxaquacua2
                            )
                            else float(
                                row.qxaquacua2
                            ),
                            None
                            if pd.isna(row.htl3)
                            else float(row.htl3),
                            None
                            if pd.isna(row.qvao3)
                            else float(row.qvao3),
                            None
                            if pd.isna(
                                row.luuluongnhamay3
                            )
                            else float(
                                row.luuluongnhamay3
                            ),
                            None
                            if pd.isna(
                                row.qxaquacua3
                            )
                            else float(
                                row.qxaquacua3
                            ),
                            None
                            if pd.isna(row.htl4)
                            else float(row.htl4),
                            None
                            if pd.isna(row.qvao4)
                            else float(row.qvao4),
                            None
                            if pd.isna(
                                row.luuluongnhamay4
                            )
                            else float(
                                row.luuluongnhamay4
                            ),
                            None
                            if pd.isna(
                                row.qxaquacua4
                            )
                            else float(
                                row.qxaquacua4
                            ),
                            None
                            if pd.isna(row.qvevugia)
                            else float(row.qvevugia),
                            None
                            if pd.isna(row.qvethubon)
                            else float(row.qvethubon),
                            "pctt_danang",
                        )
                    )

                query = """
                    INSERT INTO pctt_observations
                    (
                        timestamp,
                        htl1,
                        qvao1,
                        luuluongnhamay1,
                        qxaquacua1,
                        htl2,
                        qvao2,
                        luuluongnhamay2,
                        qxaquacua2,
                        htl3,
                        qvao3,
                        luuluongnhamay3,
                        qxaquacua3,
                        htl4,
                        qvao4,
                        luuluongnhamay4,
                        qxaquacua4,
                        qvevugia,
                        qvethubon,
                        source
                    )
                    VALUES %s
                    ON CONFLICT (timestamp)
                    DO UPDATE SET
                        htl1 = EXCLUDED.htl1,
                        qvao1 = EXCLUDED.qvao1,
                        luuluongnhamay1 =
                            EXCLUDED.luuluongnhamay1,
                        qxaquacua1 =
                            EXCLUDED.qxaquacua1,
                        htl2 = EXCLUDED.htl2,
                        qvao2 = EXCLUDED.qvao2,
                        luuluongnhamay2 =
                            EXCLUDED.luuluongnhamay2,
                        qxaquacua2 =
                            EXCLUDED.qxaquacua2,
                        htl3 = EXCLUDED.htl3,
                        qvao3 = EXCLUDED.qvao3,
                        luuluongnhamay3 =
                            EXCLUDED.luuluongnhamay3,
                        qxaquacua3 =
                            EXCLUDED.qxaquacua3,
                        htl4 = EXCLUDED.htl4,
                        qvao4 = EXCLUDED.qvao4,
                        luuluongnhamay4 =
                            EXCLUDED.luuluongnhamay4,
                        qxaquacua4 =
                            EXCLUDED.qxaquacua4,
                        qvevugia = EXCLUDED.qvevugia,
                        qvethubon = EXCLUDED.qvethubon,
                        source = EXCLUDED.source
                """

                execute_values(
                    cursor,
                    query,
                    rows,
                    page_size=500,
                )

                print(
                    f"Inserted/updated {len(rows)} "
                    f"PCTT rows."
                )

    finally:
        connection.close()


def main():
    df = load_csv()

    insert_data(df)

    print(
        "PCTT data ingestion completed successfully."
    )


if __name__ == "__main__":
    main()