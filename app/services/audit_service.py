from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


def audit(db: Session, user, action: str, entity: str, entity_id: int | None = None, details: str | None = None):
    """Add an audit row to the current transaction (committed with the caller's commit)."""
    db.add(AuditLog(user_id=getattr(user, "id", None), action=action, entity=entity,
                    entity_id=entity_id, details=details))
