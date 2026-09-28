import os
import psycopg2


SOURCE_TIMEZONE = "Asia/Ho_Chi_Minh"


def get_connection():
    password = os.getenv("POSTGRES_PASSWORD")

    if not password:
        raise RuntimeError(
            "POSTGRES_PASSWORD environment variable is not set."
        )

    connection = psycopg2.connect(
        host="localhost",
        port=5432,
        database="weather_forecasting",
        user="postgres",
        password=password,
    )

    # Keep API timestamps explicitly in Vietnam time.
    with connection.cursor() as cursor:
        cursor.execute(
            "SET TIME ZONE 'Asia/Ho_Chi_Minh';"
        )

    return connection


def get_pctt_summary():
    query = """
        SELECT
            COUNT(*) AS observation_count,
            MIN(timestamp) AS start_time,
            MAX(timestamp) AS end_time,
            COUNT(*) FILTER (
                WHERE htl1 IS NULL
            ) AS htl1_missing,
            COUNT(*) FILTER (
                WHERE qvao1 IS NULL
            ) AS qvao1_missing,
            COUNT(*) FILTER (
                WHERE luuluongnhamay1 IS NULL
            ) AS luuluongnhamay1_missing,
            COUNT(*) FILTER (
                WHERE qxaquacua1 IS NULL
            ) AS qxaquacua1_missing,
            COUNT(*) FILTER (
                WHERE htl2 IS NULL
            ) AS htl2_missing,
            COUNT(*) FILTER (
                WHERE qvao2 IS NULL
            ) AS qvao2_missing,
            COUNT(*) FILTER (
                WHERE luuluongnhamay2 IS NULL
            ) AS luuluongnhamay2_missing,
            COUNT(*) FILTER (
                WHERE qxaquacua2 IS NULL
            ) AS qxaquacua2_missing,
            COUNT(*) FILTER (
                WHERE htl3 IS NULL
            ) AS htl3_missing,
            COUNT(*) FILTER (
                WHERE qvao3 IS NULL
            ) AS qvao3_missing,
            COUNT(*) FILTER (
                WHERE luuluongnhamay3 IS NULL
            ) AS luuluongnhamay3_missing,
            COUNT(*) FILTER (
                WHERE qxaquacua3 IS NULL
            ) AS qxaquacua3_missing,
            COUNT(*) FILTER (
                WHERE htl4 IS NULL
            ) AS htl4_missing,
            COUNT(*) FILTER (
                WHERE qvao4 IS NULL
            ) AS qvao4_missing,
            COUNT(*) FILTER (
                WHERE luuluongnhamay4 IS NULL
            ) AS luuluongnhamay4_missing,
            COUNT(*) FILTER (
                WHERE qxaquacua4 IS NULL
            ) AS qxaquacua4_missing,
            COUNT(*) FILTER (
                WHERE qvevugia IS NULL
            ) AS qvevugia_missing,
            COUNT(*) FILTER (
                WHERE qvethubon IS NULL
            ) AS qvethubon_missing
        FROM pctt_observations;
    """

    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(query)
            row = cursor.fetchone()

        (
            observation_count,
            start_time,
            end_time,
            htl1_missing,
            qvao1_missing,
            luuluongnhamay1_missing,
            qxaquacua1_missing,
            htl2_missing,
            qvao2_missing,
            luuluongnhamay2_missing,
            qxaquacua2_missing,
            htl3_missing,
            qvao3_missing,
            luuluongnhamay3_missing,
            qxaquacua3_missing,
            htl4_missing,
            qvao4_missing,
            luuluongnhamay4_missing,
            qxaquacua4_missing,
            qvevugia_missing,
            qvethubon_missing,
        ) = row

        return {
            "observation_count": int(observation_count),
            "start_time": start_time.isoformat()
            if start_time
            else None,
            "end_time": end_time.isoformat()
            if end_time
            else None,
            "missing_values": {
                "htl1": int(htl1_missing),
                "qvao1": int(qvao1_missing),
                "luuluongnhamay1": int(
                    luuluongnhamay1_missing
                ),
                "qxaquacua1": int(
                    qxaquacua1_missing
                ),
                "htl2": int(htl2_missing),
                "qvao2": int(qvao2_missing),
                "luuluongnhamay2": int(
                    luuluongnhamay2_missing
                ),
                "qxaquacua2": int(
                    qxaquacua2_missing
                ),
                "htl3": int(htl3_missing),
                "qvao3": int(qvao3_missing),
                "luuluongnhamay3": int(
                    luuluongnhamay3_missing
                ),
                "qxaquacua3": int(
                    qxaquacua3_missing
                ),
                "htl4": int(htl4_missing),
                "qvao4": int(qvao4_missing),
                "luuluongnhamay4": int(
                    luuluongnhamay4_missing
                ),
                "qxaquacua4": int(
                    qxaquacua4_missing
                ),
                "qvevugia": int(qvevugia_missing),
                "qvethubon": int(qvethubon_missing),
            },
        }

    finally:
        connection.close()


def get_pctt_latest():
    query = """
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

    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(query)
            row = cursor.fetchone()

        if row is None:
            return None

        return {
            "timestamp": row[0].isoformat(),
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
        connection.close()


def get_pctt_history(hours=72):
    """
    Return the most recent PCTT observations.

    Default:
        72 hours

    Maximum:
        168 hours / 7 days
    """

    if hours < 1:
        raise ValueError("hours must be greater than zero.")

    if hours > 168:
        hours = 168

    query = """
        SELECT
            timestamp,
            htl1,
            qvao1,
            htl2,
            qvao2,
            htl3,
            qvao3,
            htl4,
            qvao4,
            qvevugia,
            qvethubon
        FROM pctt_observations
        WHERE timestamp >= (
            SELECT MAX(timestamp)
            FROM pctt_observations
        ) - (%s * INTERVAL '1 hour')
        ORDER BY timestamp ASC;
    """

    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(query, (hours,))
            rows = cursor.fetchall()

        results = []

        for row in rows:
            results.append(
                {
                    "timestamp": row[0].isoformat(),
                    "htl1": float(row[1])
                    if row[1] is not None
                    else None,
                    "qvao1": float(row[2])
                    if row[2] is not None
                    else None,
                    "htl2": float(row[3])
                    if row[3] is not None
                    else None,
                    "qvao2": float(row[4])
                    if row[4] is not None
                    else None,
                    "htl3": float(row[5])
                    if row[5] is not None
                    else None,
                    "qvao3": float(row[6])
                    if row[6] is not None
                    else None,
                    "htl4": float(row[7])
                    if row[7] is not None
                    else None,
                    "qvao4": float(row[8])
                    if row[8] is not None
                    else None,
                    "qvevugia": float(row[9])
                    if row[9] is not None
                    else None,
                    "qvethubon": float(row[10])
                    if row[10] is not None
                    else None,
                }
            )

        return results

    finally:
        connection.close()