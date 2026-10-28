"""Database connection for the preprocessing task (settings come from .env)."""
import os

import psycopg2
from dotenv import load_dotenv

# Load database settings from the .env file in this folder
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))


def get_connection():
    """Create and return a PostgreSQL connection. Never prints the password."""
    password = os.getenv("DB_PASSWORD")
    if not password or password == "change_me":
        raise SystemExit("DB_PASSWORD is missing in .env. Put your real password there.")
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "task3_articles"),
        user=os.getenv("DB_USER", "task3_user"),
        password=password,
        connect_timeout=int(os.getenv("DB_CONNECT_TIMEOUT", "10")),
    )
