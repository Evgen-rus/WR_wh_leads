from __future__ import annotations

from typing import Any

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    func,
    insert,
    select,
    text,
    update,
)
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
    Column("email_status", String(32), nullable=False, server_default="pending"),
    Column("email_attempts", Integer, nullable=False, server_default="0"),
    Column("email_last_error", Text, nullable=True),
    Column("email_sent_at", DateTime(timezone=True), nullable=True),
)


def ensure_database() -> None:
    metadata.create_all(engine)
    # Safe migration for already-created table.
    alter_statements = [
        "ALTER TABLE provider_leads ADD COLUMN IF NOT EXISTS email_status VARCHAR(32) NOT NULL DEFAULT 'pending'",
        "ALTER TABLE provider_leads ADD COLUMN IF NOT EXISTS email_attempts INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE provider_leads ADD COLUMN IF NOT EXISTS email_last_error TEXT",
        "ALTER TABLE provider_leads ADD COLUMN IF NOT EXISTS email_sent_at TIMESTAMPTZ",
    ]
    with engine.begin() as connection:
        for stmt in alter_statements:
            connection.execute(text(stmt))


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
            email_status="pending",
            email_attempts=0,
            email_last_error=None,
            email_sent_at=None,
        )
        .returning(provider_leads.c.id)
    )

    try:
        with engine.begin() as connection:
            inserted_id = connection.execute(stmt).scalar_one()
    except SQLAlchemyError as exc:
        raise RuntimeError(f"Database write failed: {exc}") from exc

    return int(inserted_id)


def get_pending_email_leads(batch_size: int, max_attempts: int) -> list[dict[str, Any]]:
    stmt = (
        select(
            provider_leads.c.id,
            provider_leads.c.lead_uid,
            provider_leads.c.site,
            provider_leads.c.payload,
            provider_leads.c.received_at,
            provider_leads.c.email_attempts,
        )
        .where(provider_leads.c.email_status == "pending")
        .where(provider_leads.c.email_attempts < max_attempts)
        .order_by(provider_leads.c.id.asc())
        .limit(batch_size)
    )
    with engine.begin() as connection:
        rows = connection.execute(stmt).mappings().all()
    return [dict(row) for row in rows]


def mark_email_sent(lead_id: int) -> None:
    stmt = (
        update(provider_leads)
        .where(provider_leads.c.id == lead_id)
        .values(
            email_status="sent",
            email_sent_at=func.now(),
            email_last_error=None,
        )
    )
    with engine.begin() as connection:
        connection.execute(stmt)


def mark_email_failed(lead_id: int, error_message: str, final: bool) -> None:
    next_status = "failed" if final else "pending"
    stmt = (
        update(provider_leads)
        .where(provider_leads.c.id == lead_id)
        .values(
            email_status=next_status,
            email_attempts=provider_leads.c.email_attempts + 1,
            email_last_error=error_message[:2000],
        )
    )
    with engine.begin() as connection:
        connection.execute(stmt)

