from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import STAFF_ROLES, ensure_customer_access, get_or_404, own_customer, paging, require_roles
from app.api.v1.auth import current_user
from app.db.session import get_db
from app.models.service_plan import ServicePlan
from app.models.subscription import Subscription
from app.models.usage_record import UsageRecord
from app.models.user import User
from app.schemas.usage import UsageCreate, UsageLine, UsageResponse, UsageSummary
from app.services import subscription_service as svc

router = APIRouter(prefix="/usage", tags=["Usage"])
RECORDERS = ("super_admin", "operations_manager", "support_agent", "network_engineer")


@router.post("/", response_model=UsageResponse, status_code=201, summary="Record data / voice / sms usage")
def record_usage(payload: UsageCreate, db: Session = Depends(get_db), actor: User = Depends(require_roles(*RECORDERS))):
    sub = get_or_404(db, Subscription, payload.subscription_id, "Subscription")
    svc.expire_if_due(db, sub)
    if sub.status != "active":
        db.commit()
        raise HTTPException(409, f"Usage can only be recorded on an active subscription (current: {sub.status})")
    rec = UsageRecord(**payload.model_dump())
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


@router.get("/", response_model=list[UsageResponse])
def list_usage(subscription_id: int | None = Query(default=None), usage_type: str | None = Query(default=None),
               page=Depends(paging), db: Session = Depends(get_db), user: User = Depends(current_user)):
    skip, limit = page
    stmt = select(UsageRecord).order_by(UsageRecord.id.desc())
    if user.role not in STAFF_ROLES:
        mine = own_customer(db, user)
        if not mine:
            return []
        stmt = stmt.join(Subscription, Subscription.id == UsageRecord.subscription_id).where(Subscription.customer_id == mine.id)
    if subscription_id:
        stmt = stmt.where(UsageRecord.subscription_id == subscription_id)
    if usage_type:
        stmt = stmt.where(UsageRecord.usage_type == usage_type)
    return list(db.scalars(stmt.offset(skip).limit(limit)).all())


def _line(used: int, limit: int) -> UsageLine:
    return UsageLine(used=used, limit=limit, remaining=max(limit - used, 0), exceeded=used > limit)


@router.get("/subscriptions/{sub_id}/summary", response_model=UsageSummary,
            summary="Usage vs plan limits for the current billing period")
def usage_summary(sub_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    sub = get_or_404(db, Subscription, sub_id, "Subscription")
    ensure_customer_access(db, user, sub.customer_id)
    plan = db.get(ServicePlan, sub.plan_id)
    totals = dict(db.execute(select(UsageRecord.usage_type, func.coalesce(func.sum(UsageRecord.quantity), 0))
                             .where(UsageRecord.subscription_id == sub.id, UsageRecord.recorded_at >= sub.start_date)
                             .group_by(UsageRecord.usage_type)).all())
    return UsageSummary(subscription_id=sub.id, plan_id=plan.id, period_start=sub.start_date, period_end=sub.end_date,
                        data_mb=_line(int(totals.get("data", 0)), plan.data_limit_mb),
                        voice_minutes=_line(int(totals.get("voice", 0)), plan.voice_minutes),
                        sms=_line(int(totals.get("sms", 0)), plan.sms_limit))
