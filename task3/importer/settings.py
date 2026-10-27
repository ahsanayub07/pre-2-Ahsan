"""Reads and validates configuration from importer/.env (never hardcode secrets)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ENV_FILE = Path(__file__).with_name(".env")
REQUIRED = ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD")
LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR"}


class ConfigError(Exception):
    """Raised when a setting is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    app_env: str
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str = ""
    db_connect_timeout: int = 10
    csv_file_path: Path = Path("articles_large.csv")
    batch_size: int = 2000
    log_level: str = "INFO"

    def conninfo(self) -> dict:
        """Keyword arguments for psycopg.connect (password stays out of any URL)."""
        return {"host": self.db_host, "port": self.db_port, "dbname": self.db_name,
                "user": self.db_user, "password": self.db_password,
                "connect_timeout": self.db_connect_timeout}

    def __repr__(self) -> str:                 # never print the password
        return (f"Settings(app_env={self.app_env!r}, db={self.db_user}@"
                f"{self.db_host}:{self.db_port}/{self.db_name}, "
                f"csv={self.csv_file_path}, batch_size={self.batch_size})")


def _int(name: str, default: str, minimum: int = 1) -> int:
    raw = os.getenv(name, default)
    try:
        value = int(raw)
    except ValueError:
        raise ConfigError(f"{name} must be a whole number, got {raw!r}") from None
    if value < minimum:
        raise ConfigError(f"{name} must be at least {minimum}")
    return value


def load_settings() -> Settings:
    """Load .env, check every required value, and return a Settings object."""
    load_dotenv(ENV_FILE)
    missing = [k for k in REQUIRED if not os.getenv(k)]
    if missing:
        raise ConfigError("Missing in .env: " + ", ".join(missing)
                          + f" (copy .env.example to {ENV_FILE.name} and fill it in)")
    if os.getenv("DB_PASSWORD") == "change_me":
        raise ConfigError("DB_PASSWORD is still 'change_me'. Put your real password in .env")
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    if level not in LOG_LEVELS:
        raise ConfigError(f"LOG_LEVEL must be one of {sorted(LOG_LEVELS)}")
    return Settings(
        app_env=os.getenv("APP_ENV", "development"),
        db_host=os.environ["DB_HOST"],
        db_port=_int("DB_PORT", "5432"),
        db_name=os.environ["DB_NAME"],
        db_user=os.environ["DB_USER"],
        db_password=os.environ["DB_PASSWORD"],
        db_connect_timeout=_int("DB_CONNECT_TIMEOUT", "10"),
        csv_file_path=Path(os.getenv("CSV_FILE_PATH", "articles_large.csv")),
        batch_size=_int("BATCH_SIZE", "2000"),
        log_level=level,
    )
