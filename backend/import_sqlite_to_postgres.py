"""Explicit, additive SQLite-to-PostgreSQL import.

This script never truncates or drops the destination. It requires both paths
through environment variables and never prints their values.
"""
import os
import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text


source_path = Path(os.environ.get("REFIND_IMPORT_SQLITE_PATH", "backend/refind.db"))
target_url = os.environ.get("REFIND_DATABASE_URL", "")
if not target_url.startswith(("postgresql://", "postgresql+")):
    raise SystemExit("REFIND_DATABASE_URL must be a PostgreSQL URL")
if target_url.startswith("postgresql://"):
    target_url = target_url.replace("postgresql://", "postgresql+psycopg://", 1)
if not source_path.exists():
    raise SystemExit("REFIND_IMPORT_SQLITE_PATH does not exist")

root = Path(__file__).resolve().parent.parent
config = Config(str(root / "alembic.ini"))
config.set_main_option("sqlalchemy.url", target_url.replace("%", "%%"))
command.upgrade(config, "head")
target = create_engine(target_url, pool_pre_ping=True)
with sqlite3.connect(source_path) as source, target.begin() as destination:
    source.row_factory = sqlite3.Row
    for table, columns in {
        "users": ("id", "name", "email", "password_hash", "role", "created_at"),
        "reports": ("id", "user_id", "kind", "name", "category", "location", "description", "photo_url", "status", "created_at"),
        "claims": ("id", "report_id", "user_id", "ownership_detail", "return_point", "status", "created_at"),
        "matches": ("id", "lost_report_id", "found_report_id", "score", "status", "created_at"),
        "notifications": ("id", "user_id", "kind", "message", "report_id", "read", "created_at"),
    }.items():
        rows = source.execute(f"SELECT {', '.join(columns)} FROM {table}").fetchall()
        if not rows:
            continue
        names = ", ".join(columns)
        binds = ", ".join(f":{column}" for column in columns)
        statement = text(f"INSERT INTO {table} ({names}) VALUES ({binds}) ON CONFLICT DO NOTHING")
        for item in rows:
            values = dict(item)
            destination.execute(statement, values)
print("SQLite import completed additively.")
