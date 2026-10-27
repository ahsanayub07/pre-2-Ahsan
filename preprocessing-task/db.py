
import os

import psycopg2
from dotenv import load_dotenv

# Load database settings from task4/.env
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))


def get_connection():
    """Create and return a PostgreSQL database connection."""
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "task3_articles"),
        user=os.getenv("DB_USER", "task3_user"),
        password=os.getenv("DB_PASSWORD"),
    )
