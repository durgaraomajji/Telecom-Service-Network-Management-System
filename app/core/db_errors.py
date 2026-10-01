import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DataError, IntegrityError, SQLAlchemyError

logger = logging.getLogger("uvicorn.error")

# MySQL / MariaDB error codes
SCHEMA_CODES = {1054, 1146, 1364, 1136, 1167}          # unknown column/table, no default, column count
CONNECTION_CODES = {1045, 1049, 1044, 2002, 2003, 2006, 2013}  # auth, unknown db, cannot connect, lost connection


def _code_and_message(exc: SQLAlchemyError):
    """The driver's own error code and message only (no SQL text, no credentials)."""
    orig = getattr(exc, "orig", None)
    if orig is None:
        return None, exc.__class__.__name__
    code = orig.args[0] if orig.args and isinstance(orig.args[0], int) else None
    return code, str(orig)


async def sqlalchemy_error_handler(request: Request, exc: SQLAlchemyError):
    logger.exception("Database error on %s %s", request.method, request.url.path)
    code, msg = _code_and_message(exc)
    if code in CONNECTION_CODES:
        return JSONResponse(status_code=503, content={
            "detail": f"Cannot use the database: {msg}. Check DATABASE_URL in .env and that MySQL is running."})
    if code in SCHEMA_CODES:
        return JSONResponse(status_code=500, content={
            "detail": f"Database schema problem: {msg}. Your tables are older than the code. "
                      "Run: python -m scripts.fix_schema  (keeps data)  "
                      "or python -m scripts.reset_db --yes  (wipes and recreates)."})
    if isinstance(exc, IntegrityError):
        return JSONResponse(status_code=409, content={"detail": f"Conflicts with existing data: {msg}"})
    if isinstance(exc, DataError):
        hint = " Use a utf8mb4 database/table." if code == 1366 else ""
        return JSONResponse(status_code=422, content={"detail": f"Database rejected the value: {msg}.{hint}"})
    return JSONResponse(status_code=500, content={"detail": f"Database error: {msg}"})
