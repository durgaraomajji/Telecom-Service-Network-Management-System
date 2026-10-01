from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import NETWORK, get_or_404, paging, require_roles, staff_only
from app.api.v1.auth import current_user
from app.core.timeutil import utcnow
from app.db.session import get_db
from app.models.address import Address
from app.models.customer import Customer
from app.models.outage import Outage
from app.models.outage_customer import OutageCustomer
from app.models.outage_tower import OutageTower
from app.models.subscription import Subscription
from app.models.tower import Tower
from app.models.user import User
from app.schemas.outage import OutageCreate, OutageResponse, OutageStatusUpdate
from app.services.audit_service import audit
from app.services.notification_service import notify

router = APIRouter(prefix="/outages", tags=["Outages"])


def _view(db, outage: Outage) -> OutageResponse:
    towers = list(db.scalars(select(OutageTower.tower_id).where(OutageTower.outage_id == outage.id)).all())
    affected = db.scalar(select(func.count()).select_from(OutageCustomer).where(OutageCustomer.outage_id == outage.id))
    resp = OutageResponse.model_validate(outage)
    resp.tower_ids, resp.affected_customers = towers, affected or 0
    return resp


@router.post("/", response_model=OutageResponse, status_code=201,
             summary="Report an outage: marks towers, finds affected customers and notifies them")
def create_outage(payload: OutageCreate, db: Session = Depends(get_db), actor: User = Depends(require_roles(*NETWORK))):
    ids = sorted(set(payload.tower_ids))
    towers = list(db.scalars(select(Tower).where(Tower.id.in_(ids))).all())
    missing = set(ids) - {t.id for t in towers}
    if missing:
        raise HTTPException(404, f"Tower(s) not found: {sorted(missing)}")
    outage = Outage(title=payload.title, description=payload.description, severity=payload.severity,
                    status="open", created_by=actor.id)
    db.add(outage)
    db.flush()
    new_status = "down" if payload.severity in ("high", "critical") else "degraded"
    for tower in towers:
        db.add(OutageTower(outage_id=outage.id, tower_id=tower.id))
        tower.status = new_status
    # affected = customers with an address in a tower's city and a live subscription
    cities = {t.city.lower() for t in towers}
    customer_ids = db.scalars(
        select(Address.customer_id).join(Subscription, Subscription.customer_id == Address.customer_id)
        .where(func.lower(Address.city).in_(cities), Subscription.status == "active").distinct()).all()
    for cid in customer_ids:
        db.add(OutageCustomer(outage_id=outage.id, customer_id=cid))
        cust = db.get(Customer, cid)
        notify(db, cust.user_id, "Network outage in your area", payload.title, "outage")
    audit(db, actor, "create", "outage", outage.id, f"severity={payload.severity} towers={ids}")
    db.commit()
    db.refresh(outage)
    return _view(db, outage)


@router.get("/", response_model=list[OutageResponse], summary="List outages (any logged-in user; status page)")
def list_outages(status: str | None = Query(default=None), severity: str | None = Query(default=None),
                 page=Depends(paging), db: Session = Depends(get_db), user: User = Depends(current_user)):
    skip, limit = page
    stmt = select(Outage).order_by(Outage.id.desc())
    if status:
        stmt = stmt.where(Outage.status == status)
    if severity:
        stmt = stmt.where(Outage.severity == severity)
    return [_view(db, o) for o in db.scalars(stmt.offset(skip).limit(limit)).all()]


@router.get("/{outage_id}", response_model=OutageResponse)
def get_outage(outage_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return _view(db, get_or_404(db, Outage, outage_id, "Outage"))


@router.patch("/{outage_id}/status", response_model=OutageResponse)
def update_status(outage_id: int, payload: OutageStatusUpdate, db: Session = Depends(get_db),
                  actor: User = Depends(require_roles(*NETWORK))):
    outage = get_or_404(db, Outage, outage_id, "Outage")
    if outage.status == "resolved":
        raise HTTPException(409, "Outage is already resolved")
    if payload.status == "investigating" and outage.status != "open":
        raise HTTPException(409, f"Outage is already {outage.status}")
    outage.status = payload.status
    if payload.status == "resolved":
        outage.resolved_at = utcnow()
        for tid in db.scalars(select(OutageTower.tower_id).where(OutageTower.outage_id == outage.id)).all():
            still_down = db.scalar(select(func.count()).select_from(OutageTower)
                                   .join(Outage, Outage.id == OutageTower.outage_id)
                                   .where(OutageTower.tower_id == tid, Outage.id != outage.id,
                                          Outage.status != "resolved"))
            tower = db.get(Tower, tid)
            if not still_down and tower.status in ("down", "degraded"):
                tower.status = "active"
        for cid in db.scalars(select(OutageCustomer.customer_id).where(OutageCustomer.outage_id == outage.id)).all():
            notify(db, db.get(Customer, cid).user_id, "Network restored", outage.title, "outage")
    audit(db, actor, f"outage_{payload.status}", "outage", outage.id, payload.note)
    db.commit()
    db.refresh(outage)
    return _view(db, outage)


@router.get("/{outage_id}/affected-customers", response_model=list[int], summary="Ids of affected customers (staff)")
def affected_customers(outage_id: int, db: Session = Depends(get_db), user: User = Depends(staff_only)):
    get_or_404(db, Outage, outage_id, "Outage")
    return list(db.scalars(select(OutageCustomer.customer_id).where(OutageCustomer.outage_id == outage_id)).all())
