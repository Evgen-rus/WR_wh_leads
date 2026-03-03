from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, Column, DateTime, Integer, MetaData, String, Table, create_engine, func, insert
from sqlalchemy.exc import SQLAlchemyError

from app.config import DATABASE_URL

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
metadata = MetaData()

provider_leads = Table(
    "provider_leads",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column(
        "received_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
    Column("lead_uid", String(128), nullable=True),
    Column("site", String(255), nullable=True),
    Column("request_format", String(32), nullable=False),
    Column("payload", JSON, nullable=False),
    Column("headers", JSON, nullable=False),
)


def ensure_database() -> None:
    metadata.create_all(engine)


def save_lead(payload: dict[str, Any], headers: dict[str, Any], request_format: str) -> int:
    lead_uid = str(payload.get("uuid") or payload.get("vid") or "")
    site = str(payload.get("site") or "")

    stmt = (
        insert(provider_leads)
        .values(
            lead_uid=lead_uid or None,
            site=site or None,
            request_format=request_format,
            payload=payload,
            headers=headers,
        )
        .returning(provider_leads.c.id)
    )

    try:
        with engine.begin() as connection:
            inserted_id = connection.execute(stmt).scalar_one()
    except SQLAlchemyError as exc:
        raise RuntimeError(f"Database write failed: {exc}") from exc

    return int(inserted_id)

