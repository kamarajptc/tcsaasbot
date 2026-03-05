#!/usr/bin/env python3
import json
import os
from pathlib import Path

from sqlalchemy import MetaData, create_engine, text
from sqlalchemy.sql.sqltypes import JSON

ROOT = Path(__file__).resolve().parents[1]
SOURCE_URL = os.getenv("SOURCE_DATABASE_URL", f"sqlite:///{ROOT / 'backend' / 'sql_app.db'}")
TARGET_URL = os.getenv("TARGET_DATABASE_URL", "postgresql+psycopg:///tcsaasbot")

# Import metadata after target URL is available for any dependent settings usage.
os.environ.setdefault("DATABASE_URL", TARGET_URL)
from app.core.database import Base  # noqa: E402
from app.models import bot  # noqa: F401,E402


def _normalize_row(row: dict, target_table) -> dict:
    normalized = {}
    for column in target_table.columns:
        if column.name not in row:
            continue
        value = row[column.name]
        if value is None:
            normalized[column.name] = None
            continue
        if isinstance(column.type, JSON) and isinstance(value, str):
            try:
                normalized[column.name] = json.loads(value)
                continue
            except Exception:
                pass
        normalized[column.name] = value
    return normalized


def main() -> None:
    source_engine = create_engine(SOURCE_URL)
    target_engine = create_engine(TARGET_URL)

    Base.metadata.create_all(bind=target_engine)

    source_meta = MetaData()
    source_meta.reflect(bind=source_engine)
    target_meta = MetaData()
    target_meta.reflect(bind=target_engine)

    target_tables = [table for table in target_meta.sorted_tables if table.name in source_meta.tables]

    with target_engine.begin() as conn:
        if target_tables:
            table_list = ", ".join(f'"{table.name}"' for table in reversed(target_tables))
            conn.execute(text(f"TRUNCATE TABLE {table_list} RESTART IDENTITY CASCADE"))

    for table in target_tables:
        source_table = source_meta.tables[table.name]
        with source_engine.connect() as source_conn:
            rows = [dict(row._mapping) for row in source_conn.execute(source_table.select())]
        if not rows:
            continue
        payload = [_normalize_row(row, table) for row in rows]
        with target_engine.begin() as target_conn:
            target_conn.execute(table.insert(), payload)

    with target_engine.begin() as conn:
        for table in target_tables:
            pk_columns = list(table.primary_key.columns)
            if len(pk_columns) != 1:
                continue
            pk = pk_columns[0]
            if not getattr(pk.type, "python_type", None):
                continue
            try:
                if pk.type.python_type is not int:
                    continue
            except Exception:
                continue
            conn.execute(
                text(
                    "SELECT setval(pg_get_serial_sequence(:table_name, :column_name), "
                    "COALESCE((SELECT MAX(" + pk.name + ") FROM \"" + table.name + "\"), 1), true)"
                ),
                {"table_name": table.name, "column_name": pk.name},
            )

    print(f"Migrated {len(target_tables)} tables from {SOURCE_URL} to {TARGET_URL}")


if __name__ == "__main__":
    main()
