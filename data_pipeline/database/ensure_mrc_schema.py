
"""Initialize application and MRC database schemas without importing CSV data."""

from pathlib import Path

from backend.database import get_connection
from data_pipeline.database.import_mrc import create_table


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_FILE = PROJECT_ROOT / "database" / "schema.sql"


def main():
    if not SCHEMA_FILE.exists():
        raise FileNotFoundError(f"Database schema not found: {SCHEMA_FILE}")

    connection = get_connection()

    try:
        schema_sql = SCHEMA_FILE.read_text(encoding="utf-8")

        with connection.cursor() as cursor:
            cursor.execute(schema_sql)

        connection.commit()
        print("Application database schema initialized.")

        create_table(connection)
        print("MRC database schema initialized.")

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


if __name__ == "__main__":
    main()
