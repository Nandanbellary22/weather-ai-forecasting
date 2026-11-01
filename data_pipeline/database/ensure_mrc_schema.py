"""Initialize the MRC observations table without importing CSV data."""

from backend.database import get_connection
from data_pipeline.database.import_mrc import create_table


def main():
    connection = get_connection()

    try:
        create_table(connection)
        print("MRC database schema initialization completed.")
    finally:
        connection.close()


if __name__ == "__main__":
    main()