from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from sqlalchemy import select

from app.config import CITY_LEADS, EMAIL_TIMEZONE_LABEL
from app.database import engine, provider_leads

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
HEADER = [
    "Дата определения",
    "Имя",
    "Город",
    "Часовой пояс",
    "Телефон",
    "utm_term",
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_content",
    "yclid",
    "URL",
    "Статус почта",
]
MONTH_NAMES_RU = {
    1: "Январь",
    2: "Февраль",
    3: "Март",
    4: "Апрель",
    5: "Май",
    6: "Июнь",
    7: "Июль",
    8: "Август",
    9: "Сентябрь",
    10: "Октябрь",
    11: "Ноябрь",
    12: "Декабрь",
}
LOGGER = logging.getLogger("export_leads_to_sheet")


@dataclass
class LeadRow:
    lead_uid: str
    row_values: list[str]
    email_status: str


def _configure_logger() -> None:
    if LOGGER.handlers:
        return

    log_path_raw = (os.getenv("EXPORT_LEADS_LOG_PATH") or "logs/export_leads_to_sheet.log").strip()
    log_path = Path(log_path_raw)
    if not log_path.is_absolute():
        log_path = Path.cwd() / log_path
    log_path.parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    LOGGER.setLevel(logging.INFO)
    LOGGER.addHandler(file_handler)
    LOGGER.addHandler(console_handler)
    LOGGER.propagate = False
    LOGGER.info("Логгер инициализирован: path=%s", str(log_path))


def _retry_google_call(operation_name: str, func, *args, **kwargs):
    retries = 5
    delay = 1.0
    for attempt in range(1, retries + 1):
        try:
            return func(*args, **kwargs).execute()
        except HttpError as exc:
            status = getattr(exc.resp, "status", None)
            if status in {429, 500, 502, 503, 504} and attempt < retries:
                LOGGER.warning(
                    "Google API retry: op=%s attempt=%s/%s status=%s wait=%.1fs",
                    operation_name,
                    attempt,
                    retries,
                    status,
                    delay,
                )
                time.sleep(delay)
                delay = min(delay * 2, 16)
                continue
            LOGGER.error(
                "Google API failed: op=%s attempt=%s/%s status=%s error=%s",
                operation_name,
                attempt,
                retries,
                status,
                exc,
            )
            raise
        except Exception as exc:
            if attempt < retries:
                LOGGER.warning(
                    "Retry after generic error: op=%s attempt=%s/%s wait=%.1fs error=%s",
                    operation_name,
                    attempt,
                    retries,
                    delay,
                    exc,
                )
                time.sleep(delay)
                delay = min(delay * 2, 16)
                continue
            LOGGER.error(
                "Operation failed: op=%s attempt=%s/%s error=%s",
                operation_name,
                attempt,
                retries,
                exc,
            )
            raise
    raise RuntimeError(f"Google API call failed: {operation_name}")


def _required_env(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value:
        raise RuntimeError(f"{name} is not set")
    return value


def _build_sheets_service():
    credentials_file = _required_env("GOOGLE_CREDENTIALS_FILE")
    credentials = service_account.Credentials.from_service_account_file(
        credentials_file,
        scopes=SCOPES,
    )
    return build("sheets", "v4", credentials=credentials)


def _current_sheet_title(now_utc: datetime) -> str:
    msk_now = now_utc.astimezone(timezone(timedelta(hours=3)))
    month_name = MONTH_NAMES_RU[msk_now.month]
    return f"{month_name} {msk_now.year}"


def _extract_uid_from_name(name_cell: str) -> str:
    text = (name_cell or "").strip()
    prefix = "Гость #"
    if text.startswith(prefix):
        return text[len(prefix) :].strip()
    return ""


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _extract_first_phone(payload: dict[str, Any]) -> str:
    phones = payload.get("phones")
    if isinstance(phones, list) and phones:
        return _safe_text(phones[0])
    return ""


def _get_utm_value(payload: dict[str, Any], key: str) -> str:
    utm_payload = payload.get("utm")
    if isinstance(utm_payload, dict):
        value = utm_payload.get(key)
        if value not in (None, ""):
            return _safe_text(value)

    page_url = _safe_text(payload.get("page"))
    if page_url:
        parsed_qs = parse_qs(urlsplit(page_url).query)
        values = parsed_qs.get(key) or []
        if values:
            return _safe_text(values[0])
    return ""


def _format_identification_time(payload: dict[str, Any], received_at: Any) -> str:
    source_time = payload.get("time")
    if source_time is not None:
        try:
            parsed = datetime.fromtimestamp(int(str(source_time)), tz=timezone.utc)
            return parsed.astimezone(timezone(timedelta(hours=3))).replace(tzinfo=None).isoformat(sep=" ")
        except (TypeError, ValueError, OverflowError):
            pass
    if isinstance(received_at, datetime):
        if received_at.tzinfo is None:
            return received_at.isoformat(sep=" ")
        return received_at.astimezone(timezone(timedelta(hours=3))).replace(tzinfo=None).isoformat(sep=" ")
    return datetime.now().isoformat(sep=" ")


def _fetch_recent_leads(now_utc: datetime) -> list[LeadRow]:
    cutoff = now_utc - timedelta(hours=24)
    stmt = (
        select(
            provider_leads.c.lead_uid,
            provider_leads.c.payload,
            provider_leads.c.received_at,
            provider_leads.c.email_status,
        )
        .where(provider_leads.c.received_at >= cutoff)
        .order_by(provider_leads.c.received_at.asc(), provider_leads.c.id.asc())
    )
    with engine.begin() as connection:
        rows = connection.execute(stmt).mappings().all()

    result: list[LeadRow] = []
    skipped_without_uid = 0
    for row in rows:
        lead_uid = _safe_text(row.get("lead_uid"))
        if not lead_uid:
            skipped_without_uid += 1
            continue

        payload = row.get("payload") or {}
        if not isinstance(payload, dict):
            payload = {"raw_payload": _safe_text(payload)}

        values = [
            _format_identification_time(payload, row.get("received_at")),
            f"Гость #{lead_uid}",
            _safe_text(CITY_LEADS),
            _safe_text(EMAIL_TIMEZONE_LABEL),
            _extract_first_phone(payload),
            _get_utm_value(payload, "utm_term"),
            _get_utm_value(payload, "utm_source"),
            _get_utm_value(payload, "utm_medium"),
            _get_utm_value(payload, "utm_campaign"),
            _get_utm_value(payload, "utm_content"),
            _get_utm_value(payload, "yclid"),
            _safe_text(payload.get("page")),
            _safe_text(row.get("email_status")),
        ]
        result.append(LeadRow(lead_uid=lead_uid, row_values=values, email_status=_safe_text(row.get("email_status"))))

    LOGGER.info(
        "Лиды из БД: total=%s with_uid=%s skipped_without_uid=%s",
        len(rows),
        len(result),
        skipped_without_uid,
    )
    return result


def _ensure_sheet(service, spreadsheet_id: str, sheet_title: str) -> tuple[int, int]:
    spreadsheet = _retry_google_call(
        "spreadsheets.get",
        service.spreadsheets().get,
        spreadsheetId=spreadsheet_id,
    )
    for sheet in spreadsheet.get("sheets", []):
        props = sheet.get("properties", {})
        if props.get("title") == sheet_title:
            row_count = int(props.get("gridProperties", {}).get("rowCount", 1000))
            LOGGER.info("Лист найден: title=%s sheet_id=%s row_count=%s", sheet_title, props.get("sheetId"), row_count)
            return int(props["sheetId"]), row_count

    LOGGER.info("Лист отсутствует, создаю: title=%s", sheet_title)
    add_result = _retry_google_call(
        "spreadsheets.batchUpdate.addSheet",
        service.spreadsheets().batchUpdate,
        spreadsheetId=spreadsheet_id,
        body={
            "requests": [
                {
                    "addSheet": {
                        "properties": {
                            "title": sheet_title,
                            "gridProperties": {
                                "rowCount": 1001,
                                "columnCount": len(HEADER),
                            },
                        }
                    }
                }
            ]
        },
    )
    sheet_id = int(add_result["replies"][0]["addSheet"]["properties"]["sheetId"])
    _retry_google_call(
        "spreadsheets.values.update.header",
        service.spreadsheets().values().update,
        spreadsheetId=spreadsheet_id,
        range=f"'{sheet_title}'!A1:M1",
        valueInputOption="RAW",
        body={"values": [HEADER]},
    )
    LOGGER.info("Лист создан: title=%s sheet_id=%s", sheet_title, sheet_id)
    return sheet_id, 1001


def _read_existing_uid_map(service, spreadsheet_id: str, sheet_title: str) -> tuple[dict[str, int], int]:
    result = _retry_google_call(
        "spreadsheets.values.batchGet.uid_map",
        service.spreadsheets().values().batchGet,
        spreadsheetId=spreadsheet_id,
        ranges=[f"'{sheet_title}'!B2:B", f"'{sheet_title}'!M2:M"],
    )
    ranges = result.get("valueRanges", [])
    name_values = (ranges[0].get("values") if len(ranges) > 0 else []) or []
    status_values = (ranges[1].get("values") if len(ranges) > 1 else []) or []

    last_row = 1
    uid_to_row: dict[str, int] = {}
    max_len = max(len(name_values), len(status_values))
    for idx in range(max_len):
        row_number = idx + 2
        name_cell = name_values[idx][0] if idx < len(name_values) and name_values[idx] else ""
        status_cell = status_values[idx][0] if idx < len(status_values) and status_values[idx] else ""
        if name_cell or status_cell:
            last_row = row_number
        lead_uid = _extract_uid_from_name(name_cell)
        if lead_uid:
            uid_to_row[lead_uid] = row_number

    LOGGER.info("Текущая карта листа: known_uids=%s last_row=%s", len(uid_to_row), last_row)
    return uid_to_row, last_row


def _ensure_enough_rows(service, spreadsheet_id: str, sheet_id: int, current_row_count: int, required_last_row: int) -> int:
    row_count = current_row_count
    added_blocks = 0
    while required_last_row > row_count:
        _retry_google_call(
            "spreadsheets.batchUpdate.appendDimension",
            service.spreadsheets().batchUpdate,
            spreadsheetId=spreadsheet_id,
            body={
                "requests": [
                    {
                        "appendDimension": {
                            "sheetId": sheet_id,
                            "dimension": "ROWS",
                            "length": 1000,
                        }
                    }
                ]
            },
        )
        row_count += 1000
        added_blocks += 1

    if added_blocks:
        LOGGER.info("Добавлены строки в лист: blocks=%s new_row_count=%s", added_blocks, row_count)
    return row_count


def export_recent_leads_to_google_sheet() -> None:
    load_dotenv()
    _configure_logger()

    started = time.monotonic()
    spreadsheet_id = _required_env("GOOGLE_SHEET_ID")
    now_utc = datetime.now(timezone.utc)
    sheet_title = _current_sheet_title(now_utc)
    LOGGER.info("Старт выгрузки: spreadsheet_id=%s sheet_title=%s", spreadsheet_id, sheet_title)

    service = _build_sheets_service()
    sheet_id, row_count = _ensure_sheet(service, spreadsheet_id, sheet_title)
    existing_uid_map, last_row = _read_existing_uid_map(service, spreadsheet_id, sheet_title)

    leads = _fetch_recent_leads(now_utc)
    if not leads:
        LOGGER.info("За последние 24 часа лидов с lead_uid не найдено.")
        return

    status_updates = []
    append_rows = []
    append_count = 0
    for lead in leads:
        row_number = existing_uid_map.get(lead.lead_uid)
        if row_number:
            status_updates.append(
                {
                    "range": f"'{sheet_title}'!M{row_number}",
                    "values": [[lead.email_status]],
                }
            )
            continue

        append_rows.append(lead.row_values)
        append_count += 1
        existing_uid_map[lead.lead_uid] = last_row + append_count

    if status_updates:
        _retry_google_call(
            "spreadsheets.values.batchUpdate.statuses",
            service.spreadsheets().values().batchUpdate,
            spreadsheetId=spreadsheet_id,
            body={
                "valueInputOption": "RAW",
                "data": status_updates,
            },
        )
        LOGGER.info("Обновлены статусы: rows=%s", len(status_updates))

    if append_rows:
        target_last_row = last_row + len(append_rows)
        row_count = _ensure_enough_rows(service, spreadsheet_id, sheet_id, row_count, target_last_row)
        _retry_google_call(
            "spreadsheets.values.append.new_rows",
            service.spreadsheets().values().append,
            spreadsheetId=spreadsheet_id,
            range=f"'{sheet_title}'!A:M",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": append_rows},
        )
        LOGGER.info("Добавлены новые строки: rows=%s", len(append_rows))

    duration = time.monotonic() - started
    LOGGER.info(
        "Готово: sheet='%s' updated_statuses=%s appended_rows=%s row_count=%s duration_sec=%.2f",
        sheet_title,
        len(status_updates),
        len(append_rows),
        row_count,
        duration,
    )


if __name__ == "__main__":
    try:
        export_recent_leads_to_google_sheet()
    except Exception:
        LOGGER.exception("Фатальная ошибка при выгрузке лидов")
        raise
