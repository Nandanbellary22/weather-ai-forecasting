import os

import psycopg2


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
        raise RuntimeError("POSTGRES_PASSWORD environment variable is not set.")

    return psycopg2.connect(
        host="localhost",
        port=5432,
        dbname="weather_forecasting",
        user="postgres",
        password=password,
    )


def get_pctt_summary():
    conn = get_connection()

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    COUNT(*) AS observation_count,
                    MIN(timestamp) AS start_time,
                    MAX(timestamp) AS end_time
                FROM pctt_observations;
                """
            )

            row = cur.fetchone()

            observation_count = row[0]
            start_time = row[1]
            end_time = row[2]

            missing_values = {}

            for column in PCTT_COLUMNS:
                cur.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM pctt_observations
                    WHERE {column} IS NULL;
                    """
                )

                missing_values[column] = cur.fetchone()[0]

            return {
                "observation_count": observation_count,
                "start_time": start_time,
                "end_time": end_time,
                "missing_values": missing_values,
            }

    finally:
        conn.close()


def get_pctt_latest():
    conn = get_connection()

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
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
                    qvethubon
                FROM pctt_observations
                ORDER BY timestamp DESC
                LIMIT 1;
                """
            )

            row = cur.fetchone()

            if row is None:
                return {
                    "message": "No PCTT observations found."
                }

            return {
                "timestamp": row[0],
                "htl1": row[1],
                "qvao1": row[2],
                "luuluongnhamay1": row[3],
                "qxaquacua1": row[4],
                "htl2": row[5],
                "qvao2": row[6],
                "luuluongnhamay2": row[7],
                "qxaquacua2": row[8],
                "htl3": row[9],
                "qvao3": row[10],
                "luuluongnhamay3": row[11],
                "qxaquacua3": row[12],
                "htl4": row[13],
                "qvao4": row[14],
                "luuluongnhamay4": row[15],
                "qxaquacua4": row[16],
                "qvevugia": row[17],
                "qvethubon": row[18],
            }

    finally:
        conn.close()