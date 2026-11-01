
"""Synchronize active hydrology stations using shared database settings."""

from backend.database import get_connection


ACTIVE_HYDROLOGY_STATIONS = [
    "553100", "553300", "553800", "553900", "554000",
    "554200", "554300", "554400", "554500", "554600",
    "554700", "554800", "554900", "555000", "555100",
    "555200", "555300", "555400", "555500", "555900",
    "556100", "557600", "559200",
]

INACTIVE_HYDROLOGY_STATIONS = [
    "553000", "553200", "553400", "554100", "555800",
]

SOURCE = "professor_hydrology_api"


def main():
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            upsert_active = """
                INSERT INTO stations (
                    station_id,
                    station_type,
                    source,
                    is_active
                )
                VALUES (%s, 'hydrology', %s, TRUE)
                ON CONFLICT (station_id)
                DO UPDATE SET
                    station_type = EXCLUDED.station_type,
                    source = EXCLUDED.source,
                    is_active = TRUE,
                    updated_at = NOW();
            """

            for station_id in ACTIVE_HYDROLOGY_STATIONS:
                cursor.execute(upsert_active, (station_id, SOURCE))

            deactivate = """
                UPDATE stations
                SET is_active = FALSE,
                    updated_at = NOW()
                WHERE station_id = %s
                  AND station_type = 'hydrology';
            """

            for station_id in INACTIVE_HYDROLOGY_STATIONS:
                cursor.execute(deactivate, (station_id,))

            cursor.execute(
                """
                SELECT is_active, COUNT(*)
                FROM stations
                WHERE station_type = 'hydrology'
                  AND source = %s
                GROUP BY is_active
                ORDER BY is_active DESC;
                """,
                (SOURCE,),
            )

            counts = cursor.fetchall()

        connection.commit()

        print("========== STATION SYNC COMPLETE ==========")
        print(f"Active forecasting stations: {len(ACTIVE_HYDROLOGY_STATIONS)}")
        print(f"Temporarily excluded stations: {len(INACTIVE_HYDROLOGY_STATIONS)}")
        print("Database status counts:", counts)

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


if __name__ == "__main__":
    main()
