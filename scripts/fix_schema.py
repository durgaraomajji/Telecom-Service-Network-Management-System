"""Add columns that are missing from old tables (keeps all data).   python -m scripts.fix_schema"""
from app.db.init_db import init_db
from app.db.schema_check import add_missing_columns, find_missing_columns
from app.db.session import engine

init_db()
print("Missing before:", find_missing_columns(engine) or "none")
print("Added:", add_missing_columns(engine) or "nothing")
print("Missing after:", find_missing_columns(engine) or "none")
