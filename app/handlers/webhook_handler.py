from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.config import WEBHOOK_SECRET
from app.database import save_lead
from app.utils.logging_utils import get_app_logger
from app.utils.request_parser import read_request_payload

router = APIRouter()
logger = get_app_logger()


@router.post("/api/provider-test/{secret}")
async def provider_test(secret: str, request: Request) -> JSONResponse:
    if secret != WEBHOOK_SECRET:
        # 404 helps hide route existence for random scanners.
        raise HTTPException(status_code=404, detail="Not Found")

    payload, request_format = await read_request_payload(request)
    headers = dict(request.headers)
    inserted_id, is_duplicate = save_lead(
        payload=payload if isinstance(payload, dict) else {"payload": payload},
        headers=headers,
        request_format=request_format,
    )

    lead_state = "duplicate" if is_duplicate else "new"
    _log_lead(
        payload=payload,
        headers=headers,
        request_format=request_format,
        inserted_id=inserted_id,
        lead_state=lead_state,
    )
    return JSONResponse({"ok": True, "lead_id": inserted_id, "lead_state": lead_state})


def _log_lead(
    payload: dict[str, Any],
    headers: dict[str, Any],
    request_format: str,
    inserted_id: int,
    lead_state: str,
) -> None:
    logger.info(
        json.dumps(
            {
                "db_id": inserted_id,
                "lead_state": lead_state,
                "format": request_format,
                "headers": headers,
                "payload": payload,
            },
            ensure_ascii=False,
        )
    )

