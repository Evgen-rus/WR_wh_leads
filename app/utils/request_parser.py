from __future__ import annotations

from typing import Any

from fastapi import Request


async def read_request_payload(request: Request) -> tuple[dict[str, Any], str]:
    """
    Returns (payload, request_format).
    Supports JSON, form-data, and fallback raw body.
    """
    content_type = (request.headers.get("content-type") or "").lower()

    if "application/json" in content_type:
        payload = await request.json()
        return payload, "json"

    if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
        form_data = await request.form()
        return dict(form_data), "form"

    raw_body = await request.body()
    return {"raw": raw_body.decode("utf-8", errors="replace")}, "raw"

