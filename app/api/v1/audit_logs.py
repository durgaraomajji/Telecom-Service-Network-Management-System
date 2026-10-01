from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import ADMIN, get_or_404, paging, require_roles
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.models.user import User
from app.schemas.audit_log import AuditLogResponse

router = APIRouter(prefix="/audit-logs", tags=["Audit Logs"])


@router.get("/", response_model=list[AuditLogResponse], summary="Who did what (super_admin)")
def list_logs(user_id: int | None = Query(default=None), entity: str | None = Query(default=None),
              action: str | None = Query(default=None), entity_id: int | None = Query(default=None),
              date_from: datetime | None = Query(default=None), date_to: datetime | None = Query(default=None),
              page=Depends(paging), db: Session = Depends(get_db), actor: User = Depends(require_roles(*ADMIN))):
    skip, limit = page
    stmt = select(AuditLog).order_by(AuditLog.id.desc())
    for column, value in ((AuditLog.user_id, user_id), (AuditLog.entity, entity),
                          (AuditLog.action, action), (AuditLog.entity_id, entity_id)):
        if value is not None:
            stmt = stmt.where(column == value)
    if date_from:
        stmt = stmt.where(AuditLog.created_at >= date_from)
    if date_to:
        stmt = stmt.where(AuditLog.created_at <= date_to)
    return list(db.scalars(stmt.offset(skip).limit(limit)).all())


@router.get("/{log_id}", response_model=AuditLogResponse)
def get_log(log_id: int, db: Session = Depends(get_db), actor: User = Depends(require_roles(*ADMIN))):
    return get_or_404(db, AuditLog, log_id, "Audit log")
