from __future__ import annotations

import threading
import time

from app.config import EMAIL_MAX_ATTEMPTS, EMAIL_POLL_INTERVAL_SECONDS, EMAIL_SEND_DELAY_SECONDS
from app.database import get_pending_email_leads, mark_email_failed, mark_email_sent
from app.services.mailer import send_lead_email
from app.utils.logging_utils import get_app_logger

logger = get_app_logger()
_stop_event = threading.Event()
_worker_thread: threading.Thread | None = None


def start_email_worker() -> None:
    global _worker_thread
    if _worker_thread and _worker_thread.is_alive():
        return

    _stop_event.clear()
    _worker_thread = threading.Thread(target=_run_worker, name="email-worker", daemon=True)
    _worker_thread.start()
    logger.info("Email worker started")


def stop_email_worker() -> None:
    _stop_event.set()
    if _worker_thread and _worker_thread.is_alive():
        _worker_thread.join(timeout=3)
    logger.info("Email worker stopped")


def _run_worker() -> None:
    while not _stop_event.is_set():
        try:
            leads = get_pending_email_leads(batch_size=20, max_attempts=EMAIL_MAX_ATTEMPTS)
            if not leads:
                _stop_event.wait(EMAIL_POLL_INTERVAL_SECONDS)
                continue

            for lead in leads:
                if _stop_event.is_set():
                    return
                _process_single_lead(lead)
                _stop_event.wait(EMAIL_SEND_DELAY_SECONDS)
        except Exception as exc:
            logger.error("Email worker loop error: %s", exc)
            _stop_event.wait(EMAIL_POLL_INTERVAL_SECONDS)


def _process_single_lead(lead: dict) -> None:
    lead_id = int(lead["id"])
    attempts = int(lead.get("email_attempts") or 0)
    try:
        logger.info(
            "Lead email processing: lead_id=%s attempt=%s/%s",
            lead_id,
            attempts + 1,
            EMAIL_MAX_ATTEMPTS,
        )
        send_lead_email(lead)
        mark_email_sent(lead_id)
        logger.info("Lead email sent: lead_id=%s", lead_id)
    except Exception as exc:
        is_final = attempts + 1 >= EMAIL_MAX_ATTEMPTS
        mark_email_failed(lead_id, str(exc), final=is_final)
        logger.error(
            "Lead email failed: lead_id=%s attempt=%s/%s final=%s error=%s",
            lead_id,
            attempts + 1,
            EMAIL_MAX_ATTEMPTS,
            is_final,
            exc,
        )

