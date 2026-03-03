from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _require_env(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value:
        raise RuntimeError(f"{name} is not set")
    return value


DATABASE_URL = _require_env("DATABASE_URL")
WEBHOOK_SECRET = _require_env("WEBHOOK_SECRET")
LOG_PATH = Path(os.getenv("WEBHOOK_LOG_PATH", "logs/provider_webhook.log"))

