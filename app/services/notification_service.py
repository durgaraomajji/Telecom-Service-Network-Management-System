from sqlalchemy.orm import Session

from app.models.notification import Notification


def notify(db: Session, user_id: int | None, title: str, message: str, type_: str = "info"):
    if user_id:
        db.add(Notification(user_id=user_id, title=title, message=message, type=type_))
