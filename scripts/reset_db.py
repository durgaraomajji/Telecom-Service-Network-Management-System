"""DROP every table and recreate it from the current models (ALL DATA LOST).
    python -m scripts.reset_db --yes"""
import sys

from app.db.base import Base
from app.db.session import engine
import app.models  # noqa: F401

if "--yes" not in sys.argv:
    raise SystemExit("This deletes all data. Re-run with --yes to confirm.")
Base.metadata.drop_all(engine)
Base.metadata.create_all(engine)
print("Database reset: all tables recreated.")
