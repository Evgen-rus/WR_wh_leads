from __future__ import annotations

from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
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
    deduplicate_existing_lead_uids_sql = """
    WITH ranked AS (
        SELECT
            id,
            row_number() OVER (
                PARTITION BY lead_uid
                ORDER BY id ASC
            ) AS rn
        FROM provider_leads
        WHERE lead_uid IS NOT NULL
          AND lead_uid <> ''
    )
    UPDATE provider_leads AS pl
    SET lead_uid = NULL
    FROM ranked
    WHERE pl.id = ranked.id
      AND ranked.rn > 1
    """
    create_unique_index_sql = """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_provider_leads_lead_uid_not_empty
    ON provider_leads (lead_uid)
    WHERE lead_uid IS NOT NULL AND lead_uid <> ''
    """
    with engine.begin() as connection:
        for stmt in alter_statements:
            connection.execute(text(stmt))
        connection.execute(text(deduplicate_existing_lead_uids_sql))
        connection.execute(text(create_unique_index_sql))


def save_lead(payload: dict[str, Any], headers: dict[str, Any], request_format: str) -> tuple[int, bool]:
    lead_uid = str(payload.get("uuid") or payload.get("vid") or "").strip()
    site = str(payload.get("site") or "")

    stmt = (
        pg_insert(provider_leads)
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
        .on_conflict_do_nothing(
            index_elements=[provider_leads.c.lead_uid],
            index_where=text("lead_uid IS NOT NULL AND lead_uid <> ''"),
        )
        .returning(provider_leads.c.id)
    )

    try:
        with engine.begin() as connection:
            inserted_id = connection.execute(stmt).scalar_one_or_none()
            if inserted_id is not None:
                return int(inserted_id), False
            if not lead_uid:
                raise RuntimeError("Lead insert returned no id for payload without lead_uid")
            existing_id = connection.execute(
                select(provider_leads.c.id)
                .where(provider_leads.c.lead_uid == lead_uid)
                .order_by(provider_leads.c.id.asc())
                .limit(1)
            ).scalar_one_or_none()
            if existing_id is None:
                raise RuntimeError(f"Lead conflict found, but existing id is missing for lead_uid={lead_uid}")
    except SQLAlchemyError as exc:
        raise RuntimeError(f"Database write failed: {exc}") from exc

    return int(existing_id), True


def requeue_processing_email_leads() -> int:
    stmt = (
        update(provider_leads)
        .where(provider_leads.c.email_status == "processing")
        .values(email_status="pending")
    )
    with engine.begin() as connection:
        result = connection.execute(stmt)
    return int(result.rowcount or 0)


def claim_pending_email_leads(batch_size: int, max_attempts: int) -> list[dict[str, Any]]:
    claim_sql = text(
        """
        WITH claimed AS (
            SELECT id
            FROM provider_leads
            WHERE email_status = 'pending'
              AND email_attempts < :max_attempts
            ORDER BY id ASC
            FOR UPDATE SKIP LOCKED
            LIMIT :batch_size
        )
        UPDATE provider_leads AS pl
        SET email_status = 'processing'
        FROM claimed
        WHERE pl.id = claimed.id
        RETURNING
            pl.id,
            pl.lead_uid,
            pl.site,
            pl.payload,
            pl.received_at,
            pl.email_attempts
        """
    )
    with engine.begin() as connection:
        rows = connection.execute(
            claim_sql,
            {"max_attempts": max_attempts, "batch_size": batch_size},
        ).mappings().all()
    return [dict(row) for row in rows]


def mark_email_sent(lead_id: int) -> None:
    stmt = (
        update(provider_leads)
        .where(provider_leads.c.id == lead_id)
        .where(provider_leads.c.email_status == "processing")
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
        .where(provider_leads.c.email_status == "processing")
        .values(
            email_status=next_status,
            email_attempts=provider_leads.c.email_attempts + 1,
            email_last_error=error_message[:2000],
        )
    )
    with engine.begin() as connection:
        connection.execute(stmt)

