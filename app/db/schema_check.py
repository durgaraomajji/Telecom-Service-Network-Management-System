"""Detect tables that already exist in MySQL but are older than the current models.

SQLAlchemy's create_all() creates missing tables but never alters existing ones, so a table
left over from an earlier version (e.g. `users` without `role`) causes 500 errors.
"""
from sqlalchemy import inspect, text

from app.db.base import Base
import app.models  # noqa: F401


def find_missing_columns(engine) -> dict[str, list[str]]:
    insp = inspect(engine)
    existing = set(insp.get_table_names())
    problems: dict[str, list[str]] = {}
    for table in Base.metadata.sorted_tables:
        if table.name not in existing:
            continue
        have = {c["name"] for c in insp.get_columns(table.name)}
        missing = [c.name for c in table.columns if c.name not in have]
        if missing:
            problems[table.name] = missing
    return problems


def add_missing_columns(engine) -> list[str]:
    """Non-destructive repair: ADD the missing columns (nullable) and back-fill simple defaults."""
    done = []
    for table_name, cols in find_missing_columns(engine).items():
        table = Base.metadata.tables[table_name]
        with engine.begin() as conn:
            for name in cols:
                col = table.columns[name]
                ddl_type = col.type.compile(dialect=engine.dialect)
                conn.execute(text(f"ALTER TABLE `{table_name}` ADD COLUMN `{name}` {ddl_type} NULL"))
                default = getattr(getattr(col, "default", None), "arg", None)
                if default is not None and not callable(default):
                    conn.execute(text(f"UPDATE `{table_name}` SET `{name}` = :v"), {"v": default})
                done.append(f"{table_name}.{name}")
    return done
