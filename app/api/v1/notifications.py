from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.api.deps import OPS, SUPPORT, get_or_404, paging, require_roles
from app.api.v1.auth import current_user
from app.db.session import get_db
from app.models.notification import Notification
from app.models.user import User
from app.schemas.notification import BroadcastCreate, NotificationCreate, NotificationResponse
from app.services.audit_service import audit

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("/", response_model=list[NotificationResponse], summary="My notifications")
def my_notifications(unread_only: bool = Query(default=False), page=Depends(paging),
                     db: Session = Depends(get_db), user: User = Depends(current_user)):
    skip, limit = page
    stmt = select(Notification).where(Notification.user_id == user.id).order_by(Notification.id.desc())
    if unread_only:
        stmt = stmt.where(Notification.is_read.is_(False))
    return list(db.scalars(stmt.offset(skip).limit(limit)).all())


@router.get("/unread-count")
def unread_count(db: Session = Depends(get_db), user: User = Depends(current_user)):
    n = db.scalar(select(func.count()).select_from(Notification)
                  .where(Notification.user_id == user.id, Notification.is_read.is_(False)))
    return {"unread": n or 0}


@router.post("/read-all")
def read_all(db: Session = Depends(get_db), user: User = Depends(current_user)):
    result = db.execute(update(Notification).where(Notification.user_id == user.id, Notification.is_read.is_(False))
                        .values(is_read=True))
    db.commit()
    return {"marked_read": result.rowcount}


@router.post("/", response_model=NotificationResponse, status_code=201, summary="Send a notification to a user (support staff)")
def send_notification(payload: NotificationCreate, db: Session = Depends(get_db),
                      actor: User = Depends(require_roles(*SUPPORT))):
    get_or_404(db, User, payload.user_id, "User")
    note = Notification(**payload.model_dump())
    db.add(note)
    db.flush()
    audit(db, actor, "send", "notification", note.id, f"to user {payload.user_id}")
    db.commit()
    db.refresh(note)
    return note


@router.post("/broadcast", summary="Send a notification to every active user with a role (ops)")
def broadcast(payload: BroadcastCreate, db: Session = Depends(get_db), actor: User = Depends(require_roles(*OPS))):
    ids = db.scalars(select(User.id).where(User.role == payload.role, User.is_active.is_(True))).all()
    for uid in ids:
        db.add(Notification(user_id=uid, title=payload.title, message=payload.message, type="broadcast"))
    audit(db, actor, "broadcast", "notification", None, f"role={payload.role} count={len(ids)}")
    db.commit()
    return {"sent": len(ids)}


@router.patch("/{notification_id}/read", response_model=NotificationResponse)
def mark_read(notification_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    note = get_or_404(db, Notification, notification_id, "Notification")
    if note.user_id != user.id:
        raise HTTPException(403, "This notification belongs to another user")
    note.is_read = True
    db.commit()
    db.refresh(note)
    return note
