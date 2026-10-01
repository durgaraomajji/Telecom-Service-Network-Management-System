from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import OPS, STAFF_ROLES, SUPPORT, ensure_customer_access, get_or_404, own_customer, paging, require_roles, resolve_customer_id
from app.api.v1.auth import current_user
from app.core.timeutil import utcnow
from app.db.session import get_db
from app.models.customer import Customer
from app.models.service_plan import ServicePlan
from app.models.sim_card import SimCard
from app.models.subscription import Subscription
from app.models.subscription_history import SubscriptionHistory
from app.models.user import User
from app.schemas.subscription import (PlanChange, SubscriptionCreate, SubscriptionHistoryResponse,
                                      SubscriptionNote, SubscriptionResponse)
from app.services import subscription_service as svc

router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])


def _load(db, sub_id, user) -> Subscription:
    sub = get_or_404(db, Subscription, sub_id, "Subscription")
    ensure_customer_access(db, user, sub.customer_id)
    return svc.expire_if_due(db, sub)


@router.post("/", response_model=SubscriptionResponse, status_code=201,
             summary="Subscribe a customer to a plan on a SIM (activates the SIM)")
def create_subscription(payload: SubscriptionCreate, db: Session = Depends(get_db),
                        user: User = Depends(require_roles(*SUPPORT, "customer"))):
    customer_id = resolve_customer_id(db, user, payload.customer_id)
    customer = db.get(Customer, customer_id)
    plan = get_or_404(db, ServicePlan, payload.plan_id, "Plan")
    sim = get_or_404(db, SimCard, payload.sim_id, "SIM")
    sub = svc.create_subscription(db, user, customer, plan, sim, payload.auto_renew)
    db.commit()
    db.refresh(sub)
    return sub


@router.get("/", response_model=list[SubscriptionResponse])
def list_subscriptions(status: str | None = Query(default=None), customer_id: int | None = Query(default=None),
                       page=Depends(paging), db: Session = Depends(get_db), user: User = Depends(current_user)):
    skip, limit = page
    stmt = select(Subscription).order_by(Subscription.id)
    if user.role in STAFF_ROLES:
        if customer_id:
            stmt = stmt.where(Subscription.customer_id == customer_id)
    else:
        mine = own_customer(db, user)
        if not mine:
            return []
        stmt = stmt.where(Subscription.customer_id == mine.id)
    if status:
        stmt = stmt.where(Subscription.status == status)
    subs = list(db.scalars(stmt.offset(skip).limit(limit)).all())
    for s in subs:
        svc.expire_if_due(db, s)
    db.commit()
    return subs


@router.post("/expire-due", summary="Mark all past-due active subscriptions as expired (ops)")
def expire_due(db: Session = Depends(get_db), actor: User = Depends(require_roles(*OPS))):
    due = db.scalars(select(Subscription).where(Subscription.status == "active",
                                                Subscription.end_date < utcnow())).all()
    for sub in due:
        svc.expire_if_due(db, sub)
    db.commit()
    return {"expired": len(due)}


@router.get("/{sub_id}", response_model=SubscriptionResponse)
def get_subscription(sub_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    sub = _load(db, sub_id, user)
    db.commit()
    return sub


@router.post("/{sub_id}/change-plan", response_model=SubscriptionResponse)
def change_plan(sub_id: int, payload: PlanChange, db: Session = Depends(get_db),
                actor: User = Depends(require_roles(*SUPPORT))):
    sub = _load(db, sub_id, actor)
    svc.change_plan(db, actor, sub, get_or_404(db, ServicePlan, payload.plan_id, "Plan"))
    db.commit()
    db.refresh(sub)
    return sub


@router.post("/{sub_id}/suspend", response_model=SubscriptionResponse)
def suspend(sub_id: int, payload: SubscriptionNote | None = None, db: Session = Depends(get_db),
            actor: User = Depends(require_roles(*SUPPORT))):
    sub = _load(db, sub_id, actor)
    svc.suspend(db, actor, sub, payload.note if payload else None)
    db.commit()
    db.refresh(sub)
    return sub


@router.post("/{sub_id}/resume", response_model=SubscriptionResponse)
def resume(sub_id: int, db: Session = Depends(get_db), actor: User = Depends(require_roles(*SUPPORT))):
    sub = _load(db, sub_id, actor)
    svc.resume(db, actor, sub)
    db.commit()
    db.refresh(sub)
    return sub


@router.post("/{sub_id}/renew", response_model=SubscriptionResponse)
def renew(sub_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles(*SUPPORT, "customer"))):
    sub = _load(db, sub_id, user)
    svc.renew(db, user, sub)
    db.commit()
    db.refresh(sub)
    return sub


@router.post("/{sub_id}/cancel", response_model=SubscriptionResponse)
def cancel(sub_id: int, payload: SubscriptionNote | None = None, db: Session = Depends(get_db),
           actor: User = Depends(require_roles(*SUPPORT))):
    sub = _load(db, sub_id, actor)
    svc.cancel(db, actor, sub, payload.note if payload else None)
    db.commit()
    db.refresh(sub)
    return sub


@router.get("/{sub_id}/history", response_model=list[SubscriptionHistoryResponse])
def history(sub_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _load(db, sub_id, user)
    return list(db.scalars(select(SubscriptionHistory).where(SubscriptionHistory.subscription_id == sub_id)
                           .order_by(SubscriptionHistory.id)).all())
