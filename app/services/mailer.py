from __future__ import annotations

import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Any
from urllib.parse import parse_qs, urlsplit

from app.config import (
    EMAIL_TIMEZONE_LABEL,
    SMTP_PORT,
    SMTP_SERVER,
    SMTP_TIMEOUT_SECONDS,
    TO_EMAIL,
    YANDEX_APP_PASSWORD,
    YANDEX_EMAIL,
)


def send_lead_email(lead: dict[str, Any]) -> None:
    sender_email = _required_value(YANDEX_EMAIL, "YANDEX_EMAIL")
    app_password = _required_value(YANDEX_APP_PASSWORD, "YANDEX_APP_PASSWORD")
    to_email = _required_value(TO_EMAIL, "TO_EMAIL")

    payload = lead.get("payload") or {}
    if not isinstance(payload, dict):
        payload = {"raw_payload": str(payload)}

    message = EmailMessage()
    message["From"] = sender_email
    message["To"] = to_email
    message["Subject"] = _build_subject(payload)
    message.set_content(_build_message_body(payload=payload, received_at=lead.get("received_at")))

    with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=SMTP_TIMEOUT_SECONDS) as smtp:
        smtp.login(sender_email, app_password)
        smtp.send_message(message)


def _required_value(value: str, env_name: str) -> str:
    if not value:
        raise RuntimeError(f"{env_name} is not set")
    return value


def _build_subject(payload: dict[str, Any]) -> str:
    lead_marker = _first_non_empty(payload.get("vid"), payload.get("uuid"))
    return f"Новая идентификация Гость #{lead_marker}"


def _build_message_body(payload: dict[str, Any], received_at: Any) -> str:
    identification_time = _format_identification_time(payload, received_at)
    lead_marker = _first_non_empty(payload.get("vid"), payload.get("uuid"))
    name = f"Гость #{lead_marker}"
    city = _as_text(payload.get("city"))
    phone = _extract_first_phone(payload)
    page_url = _as_text(payload.get("page"))

    utm_source = _get_utm_value(payload, "utm_source")
    utm_medium = _get_utm_value(payload, "utm_medium")
    utm_campaign = _get_utm_value(payload, "utm_campaign")
    utm_content = _get_utm_value(payload, "utm_content")
    utm_term = _get_utm_value(payload, "utm_term")
    yclid = _get_utm_value(payload, "yclid")

    lines = [
        f"Время идентификации: {identification_time}",
        f"Имя: {name}",
        f"Город: {city}",
        f"Часовой пояс: {EMAIL_TIMEZONE_LABEL}",
        f"Телефон: {phone}",
        "URL:",
        f"1) {page_url}",
        "",
        f"utm_source: {utm_source}",
        f"utm_medium: {utm_medium}",
        f"utm_campaign: {utm_campaign}",
        f"utm_content: {utm_content}",
        f"utm_term: {utm_term}",
        f"yclid: {yclid}",
    ]
    return "\n".join(lines)


def _format_identification_time(payload: dict[str, Any], received_at: Any) -> str:
    source_time = payload.get("time")
    if source_time is not None:
        try:
            parsed = datetime.fromtimestamp(int(str(source_time)), tz=timezone.utc)
            return parsed.astimezone(timezone(timedelta(hours=3))).replace(tzinfo=None).isoformat(sep=" ")
        except (TypeError, ValueError, OverflowError):
            pass

    if isinstance(received_at, datetime):
        return received_at.replace(tzinfo=None).isoformat(sep=" ")

    return datetime.now().isoformat(sep=" ")


def _extract_first_phone(payload: dict[str, Any]) -> str:
    phones = payload.get("phones")
    if isinstance(phones, list) and phones:
        return _as_text(phones[0])
    return _as_text(payload.get("phone"))


def _get_utm_value(payload: dict[str, Any], key: str) -> str:
    utm_payload = payload.get("utm")
    if isinstance(utm_payload, dict):
        value = utm_payload.get(key)
        if value not in (None, ""):
            return _as_text(value)

    page_url = _as_text(payload.get("page"))
    if page_url:
        parsed_qs = parse_qs(urlsplit(page_url).query)
        values = parsed_qs.get(key) or []
        if values:
            return _as_text(values[0])

    return ""


def _first_non_empty(*values: Any) -> str:
    for value in values:
        text = _as_text(value)
        if text:
            return text
    return ""


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()

