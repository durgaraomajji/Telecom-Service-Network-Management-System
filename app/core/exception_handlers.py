from fastapi import Request
from fastapi.responses import JSONResponse
from app.core.exceptions import BusinessRuleError

async def business_rule_handler(request: Request, exc: BusinessRuleError):
    return JSONResponse(status_code=409, content={"detail": exc.message})
