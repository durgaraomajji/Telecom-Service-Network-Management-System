import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.exc import SQLAlchemyError

from app.api.router import api_router
from app.core.config import settings
from app.core.db_errors import sqlalchemy_error_handler
from app.db.init_db import init_db
from app.db.schema_check import find_missing_columns
from app.db.session import engine

logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Development convenience: create any missing tables so Swagger works
    # on a fresh database. Use Alembic migrations for production.
    try:
        init_db()
        logger.info("Database tables verified/created")
        for table, cols in find_missing_columns(engine).items():
            logger.error("Table '%s' is missing columns %s (old schema). Run: python -m scripts.fix_schema", table, cols)
    except Exception as exc:  # DB down or bad credentials: fail loudly but clearly
        logger.error("Database initialisation failed: %s", exc)
        raise
    yield


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="Telecom Service & Network Management API",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)


@app.get("/", tags=["Health"])
def root():
    return {"success": True, "message": "Telecom API is running", "docs": "/docs"}


@app.get("/health", tags=["Health"])
def health():
    return {"status": "healthy", "application": settings.app_name}


@app.get("/health/db", tags=["Health"], summary="Check database connection and table schema")
def health_db():
    from sqlalchemy import text
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    problems = find_missing_columns(engine)
    if problems:
        return {"status": "schema_outdated", "missing_columns": problems,
                "fix": "python -m scripts.fix_schema"}
    return {"status": "ok"}


app.add_exception_handler(SQLAlchemyError, sqlalchemy_error_handler)
app.include_router(api_router, prefix=settings.api_v1_prefix)
