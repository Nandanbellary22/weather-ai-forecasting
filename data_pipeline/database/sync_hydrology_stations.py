import os

import psycopg2


DB_CONFIG = {
    "dbname": "weather_forecasting",
    "user": "postgres",
    "host": "localhost",
    "port": 5432,
    "password": os.environ["PGPASSWORD"],
}


HYDROLOGY_STATIONS = [
    "553000",
    "553100",
    "553200",
    "553300",
    "553400",
    "553800",
    "553900",
    "554000",
    "554100",
    "554200",
    "554300",
    "554400",
    "554500",
    "554600",
    "554700",
    "554800",
    "554900",
    "555000",
    "555100",
    "555200",
    "555300",
    "555400",
    "555500",
    "555800",
    "555900",
    "556100",
    "557600",
    "559200",
]

SOURCE = "professor_hydrology_api"


def main():
    connection = psycopg2.connect(**DB_CONFIG)

    try:
        with connection.cursor() as cursor:
            query = """
                INSERT INTO stations (
                    station_id,
                    station_type,
                    source,
                    is_active
                )
                VALUES (%s, %s, %s, TRUE)
                ON CONFLICT (station_id)
                DO UPDATE SET
                    station_type = EXCLUDED.station_type,
                    source = EXCLUDED.source,
                    is_active = TRUE,
                    updated_at = NOW();
            """

            for station_id in HYDROLOGY_STATIONS:
                cursor.execute(
                    query,
                    (
                        station_id,
                        "hydrology",
                        SOURCE,
                    ),
                )

        connection.commit()

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM stations
                WHERE station_type = 'hydrology'
                  AND source = %s
                """,
                (SOURCE,),
            )

            station_count = cursor.fetchone()[0]

        print("========== STATION SYNC COMPLETE ==========")
        print(f"Hydrology stations configured: {len(HYDROLOGY_STATIONS)}")
        print(f"Hydrology stations in database: {station_count}")

    finally:
        connection.close()


if __name__ == "__main__":
    main()