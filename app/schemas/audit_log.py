from datetime import datetime
from app.schemas.common import ORM


class AuditLogResponse(ORM):
    id: int
    user_id: int | None
    action: str
    entity: str
    entity_id: int | None
    details: str | None
    created_at: datetime
