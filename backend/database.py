"""Shared PostgreSQL connection settings for local and deployed services."""
import os

import psycopg2


def get_connection():
    options = {
        "host": os.getenv("PGHOST", "localhost"),
        "port": int(os.getenv("PGPORT", "5432")),
        "dbname": os.getenv("PGDATABASE", "weather_forecasting"),
        "user": os.getenv("PGUSER", "postgres"),
        "password": os.getenv("PGPASSWORD"),
        "connect_timeout": int(os.getenv("PGCONNECT_TIMEOUT", "10")),
    }
    sslmode = os.getenv("PGSSLMODE")
    if sslmode:
        options["sslmode"] = sslmode
    return psycopg2.connect(**options)
