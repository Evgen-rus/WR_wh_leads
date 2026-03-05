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
MAIL_PROVIDER = (os.getenv("MAIL_PROVIDER") or "yandex").strip().lower()

YANDEX_EMAIL = (os.getenv("YANDEX_EMAIL") or "").strip()
YANDEX_APP_PASSWORD = (os.getenv("YANDEX_APP_PASSWORD") or "").strip()
TO_EMAIL = (os.getenv("TO_EMAIL") or "").strip()
SMTP_SERVER = (os.getenv("SMTP_SERVER") or "smtp.yandex.com").strip()
SMTP_PORT = int((os.getenv("SMTP_PORT") or "465").strip())

UNIS_SMTP_HOST = (os.getenv("UNIS_SMTP_HOST") or "smtp.go2.unisender.ru").strip()
UNIS_SMTP_PORT = int((os.getenv("UNIS_SMTP_PORT") or "587").strip())
UNIS_SMTP_USERNAME = (os.getenv("UNIS_SMTP_USERNAME") or "").strip()
UNIS_SMTP_PASSWORD = (os.getenv("UNIS_SMTP_PASSWORD") or "").strip()
UNIS_FROM_EMAIL = (os.getenv("UNIS_FROM_EMAIL") or "").strip()
UNIS_TO_EMAIL = (os.getenv("UNIS_TO_EMAIL") or "").strip()
SMTP_TIMEOUT_SECONDS = int((os.getenv("SMTP_TIMEOUT_SECONDS") or "20").strip())

# Worker behavior
EMAIL_SEND_DELAY_SECONDS = int((os.getenv("EMAIL_SEND_DELAY_SECONDS") or "5").strip())
EMAIL_MAX_ATTEMPTS = int((os.getenv("EMAIL_MAX_ATTEMPTS") or "5").strip())
EMAIL_POLL_INTERVAL_SECONDS = int((os.getenv("EMAIL_POLL_INTERVAL_SECONDS") or "2").strip())
EMAIL_TIMEZONE_LABEL = (os.getenv("EMAIL_TIMEZONE_LABEL") or "UTC +3").strip()
CITY_LEADS = (os.getenv("CITY_LEADS") or "Moscow").strip()

