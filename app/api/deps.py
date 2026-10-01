"""Shared dependencies: role checks, pagination and customer ownership helpers."""
from fastapi import Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.auth import current_user
from app.models.customer import Customer
from app.models.user import User

STAFF_ROLES = ("super_admin", "operations_manager", "support_agent", "network_engineer", "field_technician")
ADMIN = ("super_admin",)
OPS = ("super_admin", "operations_manager")
SUPPORT = ("super_admin", "operations_manager", "support_agent")
NETWORK = ("super_admin", "operations_manager", "network_engineer")


def require_roles(*roles: str):
    def dependency(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(403, f"Role '{user.role}' is not allowed here. Allowed roles: {', '.join(roles)}.")
        return user
    return dependency


def staff_only(user: User = Depends(current_user)) -> User:
    if user.role not in STAFF_ROLES:
        raise HTTPException(403, f"Role '{user.role}' is not allowed here. Staff only.")
    return user


def paging(skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200)):
    return skip, limit


def own_customer(db: Session, user: User) -> Customer | None:
    return db.scalar(select(Customer).where(Customer.user_id == user.id))


def get_or_404(db: Session, model, obj_id: int, label: str):
    obj = db.get(model, obj_id)
    if not obj:
        raise HTTPException(404, f"{label} {obj_id} not found")
    return obj


def ensure_customer_access(db: Session, user: User, customer_id: int) -> None:
    """Staff may access any customer; a customer only their own record."""
    if user.role in STAFF_ROLES:
        return
    mine = own_customer(db, user)
    if not mine or mine.id != customer_id:
        raise HTTPException(403, "You can only access your own records")


def resolve_customer_id(db: Session, user: User, customer_id: int | None) -> int:
    """Customers act on themselves; staff must say which customer."""
    if user.role == "customer":
        mine = own_customer(db, user)
        if not mine:
            raise HTTPException(409, "Create your customer profile first: POST /api/v1/customers/me")
        if customer_id is not None and customer_id != mine.id:
            raise HTTPException(403, "You can only act on your own account")
        return mine.id
    if customer_id is None:
        raise HTTPException(422, "customer_id is required")
    get_or_404(db, Customer, customer_id, "Customer")
    return customer_id
