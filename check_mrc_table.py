import os
import psycopg2


conn = psycopg2.connect(
    host="localhost",
    port=5432,
    dbname="weather_forecasting",
    user="postgres",
    password=os.environ.get("PGPASSWORD"),
)

cur = conn.cursor()

cur.execute(
    """
    SELECT table_name
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name LIKE 'mrc%%'
    ORDER BY table_name;
    """
)

tables = cur.fetchall()

print("MRC tables:")
print(tables)

cur.close()
conn.close()