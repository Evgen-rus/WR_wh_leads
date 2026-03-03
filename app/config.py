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

# Mail settings
YANDEX_EMAIL = (os.getenv("YANDEX_EMAIL") or "").strip()
YANDEX_APP_PASSWORD = (os.getenv("YANDEX_APP_PASSWORD") or "").strip()
TO_EMAIL = (os.getenv("TO_EMAIL") or "").strip()
SMTP_SERVER = (os.getenv("SMTP_SERVER") or "smtp.yandex.com").strip()
SMTP_PORT = int((os.getenv("SMTP_PORT") or "465").strip())
SMTP_TIMEOUT_SECONDS = int((os.getenv("SMTP_TIMEOUT_SECONDS") or "20").strip())

# Worker behavior
EMAIL_SEND_DELAY_SECONDS = int((os.getenv("EMAIL_SEND_DELAY_SECONDS") or "5").strip())
EMAIL_MAX_ATTEMPTS = int((os.getenv("EMAIL_MAX_ATTEMPTS") or "5").strip())
EMAIL_POLL_INTERVAL_SECONDS = int((os.getenv("EMAIL_POLL_INTERVAL_SECONDS") or "2").strip())
EMAIL_TIMEZONE_LABEL = (os.getenv("EMAIL_TIMEZONE_LABEL") or "UTC +3").strip()

