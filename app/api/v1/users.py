from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.auth import current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import RoleName, UserResponse

router = APIRouter(prefix="/users", tags=["Users"])


class RoleUpdate(BaseModel):
    role: RoleName


def _require_super_admin(user: User, action: str):
    if user.role != "super_admin":
        raise HTTPException(403, f"Role '{user.role}' cannot {action}. Log in as super_admin.")


@router.get("/me", response_model=UserResponse)
def get_me(user: User = Depends(current_user)):
    return user


@router.get("/", response_model=list[UserResponse])
def list_users(db: Session = Depends(get_db), user: User = Depends(current_user)):
    _require_super_admin(user, "list users")
    return list(db.scalars(select(User).order_by(User.id).limit(100)).all())


@router.patch("/{user_id}/role", response_model=UserResponse,
              summary="Change a user's role (super_admin only)")
def change_role(user_id: int, payload: RoleUpdate, db: Session = Depends(get_db),
                actor: User = Depends(current_user)):
    _require_super_admin(actor, "change roles")
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(404, "User not found")
    if target.role == "super_admin" and payload.role != "super_admin":
        admins = db.scalar(select(func.count(User.id)).where(User.role == "super_admin", User.is_active.is_(True)))
        if admins <= 1:
            raise HTTPException(409, "Cannot demote the last active super_admin")
    target.role = payload.role
    db.commit()
    db.refresh(target)
    return target
