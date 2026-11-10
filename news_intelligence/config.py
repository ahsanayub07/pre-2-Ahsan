"""Settings for news_intelligence. Nothing in this file is secret: the database password
comes from the environment (a local .env file that Git ignores)."""
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
load_dotenv(HERE / ".env")

# ---- Data sources (read-only) ---------------------------------------------------------------
INPUT_TABLE = "public.articles_cleaned"      # never modified by this project
ML_READY_CSV = Path(os.getenv(
    "ML_READY_CSV",
    REPO_ROOT / "data_validation_quality_assessment" / "validation_output" / "data_ml_ready.csv"))
LABELS_DIR = Path(os.getenv("LABELS_DIR", REPO_ROOT / "data_analysis_task" / "analysis_output"))

# ---- Outputs ----------------------------------------------------------------------------------
ARTIFACTS_DIR = HERE / "artifacts"           # git-ignored: embeddings, neighbour lists, results
REPORTS_DIR = HERE / "reports"

# ---- Text and model settings (provisional until measured; see reports/experiments.md) ---------
LEAD_CHARS = 1500                            # same lead length the rule classifier uses
FETCH_BATCH = 2000                           # articles read from the database per query
MODEL_NAME = os.getenv("MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2")
MAX_SEQ_TOKENS = 256                         # all-MiniLM-L6-v2 cuts longer input (confirm in Phase 3)
SEED = 42

# The planned classes: the five topics plus "other". "uncertain" and non-articles stay out of training.
CLASSES = ["market_stocks", "technology", "health", "energy", "politics", "other"]

# Figures documented by the earlier stages, used by explore.py --counts to detect any change.
DOCUMENTED_COUNTS = {"articles": 100_026, "articles_cleaned": 100_026, "ml_ready": 95_094}


class ConfigError(Exception):
    """A setting is missing or unsafe."""


@dataclass(frozen=True)
class DbSettings:
    host: str
    port: int
    dbname: str
    user: str
    password: str = field(repr=False)        # never shown, even if the object is printed
    connect_timeout: int = 10


def load_db_settings(env=None):
    """Read the database settings. Refuses a missing or placeholder password."""
    env = os.environ if env is None else env
    password = env.get("DB_PASSWORD", "")
    if not password or password == "change_me":
        raise ConfigError("DB_PASSWORD is missing or still 'change_me'. "
                          "Copy .env.example to .env and put your own password there.")
    try:
        port = int(env.get("DB_PORT", "5432"))
        timeout = int(env.get("DB_CONNECT_TIMEOUT", "10"))
    except ValueError as exc:
        raise ConfigError(f"DB_PORT and DB_CONNECT_TIMEOUT must be whole numbers ({exc})") from None
    return DbSettings(host=env.get("DB_HOST", "localhost"), port=port,
                      dbname=env.get("DB_NAME", "task3_articles"),
                      user=env.get("DB_USER", "task3_user"), password=password,
                      connect_timeout=timeout)
