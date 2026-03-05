# Запуск на отправку 270 лидов python send_leads_direct_from_md.py --file leads.md --limit 270
# Запуск без отпраки на почту с выводм тела 1 письма в консоль python send_leads_direct_from_md.py --file leads.md --limit 1 --dry-run
from __future__ import annotations

import argparse
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from app.services import mailer

LEAD_UID_PATTERN = re.compile(r"#(\d+)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Прямая отправка лидов из leads.md без записи в БД.",
    )
    parser.add_argument(
        "--file",
        type=Path,
        default=Path("leads.md"),
        help="Путь к md/tsv файлу (по умолчанию: leads.md).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=1,
        help="Сколько лидов обработать (по умолчанию: 1).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Не отправлять письмо, а вывести предпросмотр в терминал.",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=5.0,
        help="Задержка между отправками писем в секундах (по умолчанию: 5).",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=Path("logs/direct_send_from_md.log"),
        help="Файл лога отправки (по умолчанию: logs/direct_send_from_md.log).",
    )
    return parser.parse_args()


def _setup_logger(log_file: Path) -> logging.Logger:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("direct_send_from_md")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    return logger


def _normalize_header(value: str) -> str:
    return value.strip().lower().replace(" ", "_")


def _pick(row: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = (row.get(key) or "").strip()
        if value:
            return value
    return ""


def _extract_uid(name: str) -> str:
    match = LEAD_UID_PATTERN.search(name or "")
    if not match:
        return ""
    return match.group(1)


def _parse_utc_offset(tz_label: str) -> timezone:
    match = re.search(r"([+-])\s*(\d{1,2})", tz_label or "")
    if not match:
        return timezone.utc
    sign = 1 if match.group(1) == "+" else -1
    hours = int(match.group(2))
    return timezone(sign * timedelta(hours=hours))


def _date_to_unix_timestamp(date_text: str, tz_label: str) -> str:
    dt_local = datetime.strptime(date_text.strip(), "%Y-%m-%d %H:%M:%S")
    dt_with_tz = dt_local.replace(tzinfo=_parse_utc_offset(tz_label))
    return str(int(dt_with_tz.timestamp()))


def parse_rows(file_path: Path) -> list[dict[str, str]]:
    if not file_path.exists():
        raise FileNotFoundError(f"Файл не найден: {file_path}")

    lines = [line.strip() for line in file_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(lines) < 2:
        return []

    headers = [_normalize_header(part) for part in lines[0].split("\t")]
    rows: list[dict[str, str]] = []
    for line in lines[1:]:
        parts = [part.strip() for part in line.split("\t")]
        if len(parts) < len(headers):
            parts.extend([""] * (len(headers) - len(parts)))
        row = {headers[idx]: parts[idx] for idx in range(len(headers))}
        rows.append(row)
    return rows


def build_payload(row: dict[str, str]) -> dict:
    name = _pick(row, "имя", "name")
    url = _pick(row, "url")
    if not url:
        raise ValueError("Пустой URL")

    uid = _extract_uid(name)
    if not uid:
        raise ValueError("Не найден uid в поле 'Имя' (ожидается формат 'Гость #123')")

    tz_label = _pick(row, "часовой_пояс") or "UTC +0"
    date_defined = _pick(row, "дата_определения")
    event_time = _date_to_unix_timestamp(date_defined, tz_label) if date_defined else ""

    parsed_url = urlsplit(url)
    query = parse_qs(parsed_url.query)
    utm = {
        "utm_source": _pick(row, "utm_source") or (query.get("utm_source") or [""])[0],
        "utm_medium": _pick(row, "utm_medium") or (query.get("utm_medium") or [""])[0],
        "utm_campaign": _pick(row, "utm_campaign") or (query.get("utm_campaign") or [""])[0],
        "utm_content": _pick(row, "utm_content") or (query.get("utm_content") or [""])[0],
        "utm_term": _pick(row, "utm_term") or (query.get("utm_term") or [""])[0],
        "yclid": (query.get("yclid") or [""])[0],
    }

    phone = _pick(row, "телефон", "phone")
    phones = [phone] if phone else []

    return {
        "uuid": uid,
        "vid": uid,
        "name": name,
        "page": url,
        "site": parsed_url.netloc,
        "time": event_time,
        "phones": phones,
        "utm": utm,
        "comment": "direct_send_from_md",
    }


def _preview_email(lead: dict) -> None:
    payload = lead["payload"]
    from_email, _, _, to_email = mailer._get_mail_provider_settings()  # noqa: SLF001
    subject = mailer._build_subject(payload)  # noqa: SLF001
    body = mailer._build_message_body(  # noqa: SLF001
        payload=payload,
        received_at=lead.get("received_at"),
    )

    print("=" * 72)
    print("DRY RUN: письмо не отправлено")
    print(f"From: {from_email}")
    print(f"To: {to_email}")
    print(f"Subject: {subject}")
    print("-" * 72)
    print(body)
    print("=" * 72)


def main() -> None:
    args = parse_args()
    if args.limit <= 0:
        raise ValueError("--limit должен быть > 0")
    if args.delay_seconds < 0:
        raise ValueError("--delay-seconds должен быть >= 0")

    logger = _setup_logger(args.log_file)
    logger.info(
        "Start run file=%s limit=%s dry_run=%s delay_seconds=%s",
        args.file,
        args.limit,
        args.dry_run,
        args.delay_seconds,
    )

    rows = parse_rows(args.file)
    if not rows:
        print("Нет данных для обработки.")
        logger.info("No rows found in file=%s", args.file)
        return

    selected = rows[: args.limit]
    sent = 0
    skipped = 0

    for index, row in enumerate(selected, start=1):
        try:
            payload = build_payload(row)
        except ValueError as exc:
            skipped += 1
            print(f"[{index}] SKIP: {exc}")
            logger.warning("SKIP index=%s reason=%s", index, exc)
            continue

        lead = {
            "payload": payload,
            "received_at": datetime.now(timezone.utc),
        }

        if args.dry_run:
            print(f"[{index}] uid={payload.get('uuid')} site={payload.get('site')}")
            _preview_email(lead)
            logger.info(
                "DRY_RUN index=%s uid=%s site=%s phone=%s",
                index,
                payload.get("uuid"),
                payload.get("site"),
                ",".join(payload.get("phones", [])),
            )
            continue

        try:
            mailer.send_lead_email(lead)
            sent += 1
            print(
                f"[{index}] SENT uid={payload.get('uuid')} "
                f"phone={','.join(payload.get('phones', []))} site={payload.get('site')}"
            )
            logger.info(
                "SENT index=%s uid=%s site=%s phone=%s",
                index,
                payload.get("uuid"),
                payload.get("site"),
                ",".join(payload.get("phones", [])),
            )
        except Exception as exc:
            skipped += 1
            print(f"[{index}] ERROR uid={payload.get('uuid')} error={exc}")
            logger.exception(
                "ERROR index=%s uid=%s site=%s",
                index,
                payload.get("uuid"),
                payload.get("site"),
            )
            continue

        if index < len(selected) and args.delay_seconds > 0:
            logger.info("Sleep between sends seconds=%s", args.delay_seconds)
            time.sleep(args.delay_seconds)

    print(
        f"Готово. Обработано={len(selected)} "
        f"отправлено={sent} пропущено={skipped} dry_run={args.dry_run}"
    )
    logger.info(
        "Finish run processed=%s sent=%s skipped=%s dry_run=%s",
        len(selected),
        sent,
        skipped,
        args.dry_run,
    )


if __name__ == "__main__":
    main()
