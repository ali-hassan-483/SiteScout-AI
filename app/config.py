"""SiteScout AI - central configuration. Secrets come from the .env file only."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DEMOS_DIR = BASE_DIR / "demos"
LOGS_DIR = BASE_DIR / "logs"
DB_PATH = DATA_DIR / "sitescout.db"
ENV_FILE = BASE_DIR / ".env"


def _load_env() -> None:
    """Minimal .env loader. Never prints values."""
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_env()

HOST = "127.0.0.1"
PORT = 8090
SECRET_KEY = os.environ.get("SITESCOUT_SECRET_KEY", "")
SESSION_COOKIE = "sitescout_session"
SESSION_MAX_AGE = 60 * 60 * 12  # 12 hours
USER_AGENT = "SiteScout/0.1 (personal lead research)"
