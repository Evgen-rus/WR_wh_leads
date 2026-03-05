from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select

from app.database import engine, provider_leads


def json_default(value: Any) -> str | float:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


def main() -> None:
    query = (
        select(provider_leads)
        .order_by(provider_leads.c.id.desc())
        .limit(1)
    )
    with engine.connect() as connection:
        row = connection.execute(query).mappings().first()

    if not row:
        print("Таблица provider_leads пустая.")
        return

    print(json.dumps(dict(row), ensure_ascii=False, indent=2, default=json_default))


if __name__ == "__main__":
    main()
