from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import OPS, STAFF_ROLES, SUPPORT, ensure_customer_access, get_or_404, own_customer, paging, require_roles
from app.api.v1.auth import current_user
from app.core.constants import SIM_TRANSITIONS
from app.core.timeutil import utcnow
from app.db.session import get_db
from app.models.customer import Customer
from app.models.sim_card import SimCard
from app.models.sim_replacement import SimReplacement
from app.models.subscription import Subscription
from app.models.user import User
from app.schemas.sim_card import (SimCreate, SimReplaceRequest, SimReplacementResponse, SimResponse, SimStatusUpdate)
from app.services.audit_service import audit
from app.services.notification_service import notify

router = APIRouter(prefix="/sims", tags=["SIM Cards"])


@router.post("/", response_model=SimResponse, status_code=201, summary="Add a SIM to inventory")
def create_sim(payload: SimCreate, db: Session = Depends(get_db), actor: User = Depends(require_roles(*OPS))):
    if db.scalar(select(SimCard).where(SimCard.iccid == payload.iccid)):
        raise HTTPException(409, "ICCID already exists")
    if db.scalar(select(SimCard).where(SimCard.msisdn == payload.msisdn)):
        raise HTTPException(409, "Phone number (msisdn) already assigned to another SIM")
    sim = SimCard(iccid=payload.iccid, msisdn=payload.msisdn, status="available")
    db.add(sim)
    db.flush()
    audit(db, actor, "create", "sim_card", sim.id, payload.iccid)
    db.commit()
    db.refresh(sim)
    return sim


@router.get("/", response_model=list[SimResponse])
def list_sims(status: str | None = Query(default=None), customer_id: int | None = Query(default=None),
              page=Depends(paging), db: Session = Depends(get_db), user: User = Depends(current_user)):
    skip, limit = page
    stmt = select(SimCard).order_by(SimCard.id)
    if user.role in STAFF_ROLES:
        if customer_id:
            stmt = stmt.where(SimCard.customer_id == customer_id)
    else:
        mine = own_customer(db, user)
        if not mine:
            return []
        stmt = stmt.where(SimCard.customer_id == mine.id)
    if status:
        stmt = stmt.where(SimCard.status == status)
    return list(db.scalars(stmt.offset(skip).limit(limit)).all())


@router.get("/{sim_id}", response_model=SimResponse)
def get_sim(sim_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    sim = get_or_404(db, SimCard, sim_id, "SIM")
    if user.role not in STAFF_ROLES:
        if sim.customer_id is None:
            raise HTTPException(403, "You can only access your own SIMs")
        ensure_customer_access(db, user, sim.customer_id)
    return sim


@router.patch("/{sim_id}/status", response_model=SimResponse, summary="Change SIM status (validated transitions)")
def change_status(sim_id: int, payload: SimStatusUpdate, db: Session = Depends(get_db),
                  actor: User = Depends(require_roles(*SUPPORT))):
    sim = get_or_404(db, SimCard, sim_id, "SIM")
    if payload.status not in SIM_TRANSITIONS[sim.status]:
        allowed = ", ".join(sorted(SIM_TRANSITIONS[sim.status])) or "none (final state)"
        raise HTTPException(409, f"Cannot move SIM from '{sim.status}' to '{payload.status}'. Allowed: {allowed}")
    if payload.status == "active" and sim.customer_id is None:
        raise HTTPException(409, "A SIM can only be activated through a subscription (POST /subscriptions/)")
    old = sim.status
    sim.status = payload.status
    live = db.scalars(select(Subscription).where(Subscription.sim_id == sim.id,
                                                 Subscription.status.in_(("active", "suspended")))).all()
    for sub in live:  # keep subscription in step with the SIM
        if payload.status == "suspended" and sub.status == "active":
            sub.status = "suspended"
        elif payload.status == "active" and sub.status == "suspended":
            sub.status = "active"
        elif payload.status in ("blocked", "deactivated", "lost"):
            sub.status = "suspended" if payload.status == "lost" else "cancelled"
    audit(db, actor, "status_change", "sim_card", sim.id, f"{old} -> {payload.status}; {payload.reason or ''}")
    if sim.customer_id:
        cust = db.get(Customer, sim.customer_id)
        notify(db, cust.user_id, "SIM status changed", f"Your SIM {sim.msisdn or sim.iccid} is now {payload.status}.", "sim")
    db.commit()
    db.refresh(sim)
    return sim


@router.post("/{sim_id}/replace", response_model=SimReplacementResponse, status_code=201,
             summary="Replace a lost/damaged SIM (number moves to the new SIM)")
def replace_sim(sim_id: int, payload: SimReplaceRequest, db: Session = Depends(get_db),
                actor: User = Depends(require_roles(*SUPPORT))):
    old = get_or_404(db, SimCard, sim_id, "SIM")
    if old.status not in ("active", "suspended", "lost"):
        raise HTTPException(409, f"Only active, suspended or lost SIMs can be replaced (current: {old.status})")
    if db.scalar(select(SimCard).where(SimCard.iccid == payload.new_iccid)):
        raise HTTPException(409, "New ICCID already exists")
    number, keep_status, now = old.msisdn, old.status, utcnow()
    old.msisdn = None
    old.status = "deactivated"
    db.flush()
    new = SimCard(iccid=payload.new_iccid, msisdn=number, customer_id=old.customer_id, activated_at=now,
                  status="suspended" if keep_status == "suspended" else "active")
    db.add(new)
    db.flush()
    for sub in db.scalars(select(Subscription).where(Subscription.sim_id == old.id,
                                                     Subscription.status.in_(("active", "suspended")))).all():
        sub.sim_id = new.id
    rec = SimReplacement(old_sim_id=old.id, new_sim_id=new.id, reason=payload.reason,
                         notes=payload.notes, replaced_by=actor.id)
    db.add(rec)
    db.flush()
    audit(db, actor, "replace", "sim_card", old.id, f"new sim {new.id} ({payload.reason})")
    if old.customer_id:
        cust = db.get(Customer, old.customer_id)
        notify(db, cust.user_id, "SIM replaced", f"Your number {number} is now on a new SIM.", "sim")
    db.commit()
    db.refresh(rec)
    return rec


@router.get("/{sim_id}/replacements", response_model=list[SimReplacementResponse])
def list_replacements(sim_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    sim = get_or_404(db, SimCard, sim_id, "SIM")
    if user.role not in STAFF_ROLES:
        if sim.customer_id is None:
            raise HTTPException(403, "You can only access your own SIMs")
        ensure_customer_access(db, user, sim.customer_id)
    return list(db.scalars(select(SimReplacement).where(
        or_(SimReplacement.old_sim_id == sim_id, SimReplacement.new_sim_id == sim_id))
        .order_by(SimReplacement.id)).all())
