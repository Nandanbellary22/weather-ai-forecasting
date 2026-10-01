import os

import psycopg2


def main():

    conn = psycopg2.connect(
        host="localhost",
        port=5432,
        dbname="weather_forecasting",
        user="postgres",
        password=os.environ.get("PGPASSWORD"),
    )

    try:

        with conn.cursor() as cur:

            # Make both columns represent exactly the same instant.
            cur.execute(
                """
                UPDATE mrc_hydromet_observations
                SET timestamp = timestamp_utc;
                """
            )

            updated = cur.rowcount

            # Display timestamps in Vietnam time for this session.
            cur.execute(
                """
                SET TIME ZONE 'Asia/Ho_Chi_Minh';
                """
            )

            print(
                f"Restored {updated} MRC timestamps."
            )

            cur.execute(
                """
                SELECT
                    station_id,
                    timestamp_utc,
                    timestamp
                FROM mrc_hydromet_observations
                ORDER BY timestamp_utc
                LIMIT 3;
                """
            )

            print()
            print("Verification:")
            print("-" * 70)

            for row in cur.fetchall():

                print(
                    f"Station: {row[0]} | "
                    f"UTC: {row[1]} | "
                    f"Vietnam: {row[2]}"
                )

        conn.commit()

    finally:

        conn.close()

    print()
    print("MRC timestamp correction completed.")


if __name__ == "__main__":
    main()