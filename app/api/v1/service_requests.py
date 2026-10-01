from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import STAFF_ROLES, SUPPORT, ensure_customer_access, get_or_404, own_customer, paging, require_roles, resolve_customer_id
from app.api.v1.auth import current_user
from app.core.timeutil import utcnow
from app.db.session import get_db
from app.models.customer import Customer
from app.models.service_plan import ServicePlan
from app.models.service_request import ServiceRequest
from app.models.service_request_history import ServiceRequestHistory
from app.models.subscription import Subscription
from app.models.user import User
from app.schemas.service_request import (ServiceRequestCreate, ServiceRequestHistoryResponse, ServiceRequestResponse,
                                         ServiceRequestStatusUpdate)
from app.services import subscription_service as subs
from app.services.audit_service import audit
from app.services.notification_service import notify

router = APIRouter(prefix="/service-requests", tags=["Service Requests"])
FLOW = {"submitted": {"under_review", "approved", "rejected"}, "under_review": {"approved", "rejected"},
        "approved": {"completed"}, "rejected": set(), "completed": set()}


def _log(db, req, old, new, user, note=None):
    db.add(ServiceRequestHistory(request_id=req.id, old_status=old, new_status=new, changed_by=user.id, note=note))


@router.post("/", response_model=ServiceRequestResponse, status_code=201)
def create_request(payload: ServiceRequestCreate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if user.role in STAFF_ROLES and user.role not in SUPPORT:
        raise HTTPException(403, f"Role '{user.role}' cannot raise service requests")
    customer_id = resolve_customer_id(db, user, payload.customer_id)
    if payload.request_type in ("plan_change", "disconnection", "sim_replacement") and not payload.subscription_id:
        raise HTTPException(422, f"subscription_id is required for {payload.request_type}")
    if payload.request_type == "plan_change":
        if not payload.target_plan_id:
            raise HTTPException(422, "target_plan_id is required for plan_change")
        plan = get_or_404(db, ServicePlan, payload.target_plan_id, "Plan")
        if not plan.is_active:
            raise HTTPException(409, "Target plan is not active")
    if payload.subscription_id:
        sub = get_or_404(db, Subscription, payload.subscription_id, "Subscription")
        if sub.customer_id != customer_id:
            raise HTTPException(403, "That subscription belongs to another customer")
    req = ServiceRequest(request_number=f"SRQ-{uuid4().hex[:10].upper()}", customer_id=customer_id,
                         request_type=payload.request_type, description=payload.description,
                         subscription_id=payload.subscription_id, target_plan_id=payload.target_plan_id,
                         status="submitted", created_at=utcnow(), updated_at=utcnow())
    db.add(req)
    db.flush()
    _log(db, req, None, "submitted", user, "Request submitted")
    audit(db, user, "create", "service_request", req.id, f"{req.request_number} {req.request_type}")
    notify(db, db.get(Customer, customer_id).user_id, "Request received", f"{req.request_number} ({req.request_type})", "request")
    db.commit()
    db.refresh(req)
    return req


@router.get("/", response_model=list[ServiceRequestResponse])
def list_requests(status: str | None = Query(default=None), request_type: str | None = Query(default=None),
                  customer_id: int | None = Query(default=None), page=Depends(paging),
                  db: Session = Depends(get_db), user: User = Depends(current_user)):
    skip, limit = page
    stmt = select(ServiceRequest).order_by(ServiceRequest.id.desc())
    if user.role in SUPPORT:
        if customer_id:
            stmt = stmt.where(ServiceRequest.customer_id == customer_id)
    elif user.role in STAFF_ROLES:
        raise HTTPException(403, f"Role '{user.role}' cannot view service requests")
    else:
        mine = own_customer(db, user)
        if not mine:
            return []
        stmt = stmt.where(ServiceRequest.customer_id == mine.id)
    if status:
        stmt = stmt.where(ServiceRequest.status == status)
    if request_type:
        stmt = stmt.where(ServiceRequest.request_type == request_type)
    return list(db.scalars(stmt.offset(skip).limit(limit)).all())


def _load(db, req_id, user):
    req = get_or_404(db, ServiceRequest, req_id, "Service request")
    if user.role in STAFF_ROLES and user.role not in SUPPORT:
        raise HTTPException(403, f"Role '{user.role}' cannot view service requests")
    ensure_customer_access(db, user, req.customer_id)
    return req


@router.get("/{req_id}", response_model=ServiceRequestResponse)
def get_request(req_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return _load(db, req_id, user)


@router.get("/{req_id}/history", response_model=list[ServiceRequestHistoryResponse])
def request_history(req_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _load(db, req_id, user)
    return list(db.scalars(select(ServiceRequestHistory).where(ServiceRequestHistory.request_id == req_id)
                           .order_by(ServiceRequestHistory.id)).all())


@router.patch("/{req_id}/status", response_model=ServiceRequestResponse,
              summary="Review / approve / reject / complete (completing applies plan_change or disconnection)")
def update_status(req_id: int, payload: ServiceRequestStatusUpdate, db: Session = Depends(get_db),
                  actor: User = Depends(require_roles(*SUPPORT))):
    req = get_or_404(db, ServiceRequest, req_id, "Service request")
    old, new = req.status, payload.status
    if new not in FLOW[old]:
        allowed = ", ".join(sorted(FLOW[old])) or "none (final state)"
        raise HTTPException(409, f"Cannot move request from '{old}' to '{new}'. Allowed: {allowed}")
    if new == "completed" and req.subscription_id:
        sub = db.get(Subscription, req.subscription_id)
        if req.request_type == "plan_change":
            subs.change_plan(db, actor, sub, db.get(ServicePlan, req.target_plan_id))
        elif req.request_type == "disconnection":
            subs.cancel(db, actor, sub, f"Disconnection request {req.request_number}")
    req.status = new
    _log(db, req, old, new, actor, payload.note)
    audit(db, actor, "status_change", "service_request", req.id, f"{old} -> {new}")
    notify(db, db.get(Customer, req.customer_id).user_id, f"Request {req.request_number} {new.replace('_', ' ')}",
           payload.note or req.request_type, "request")
    db.commit()
    db.refresh(req)
    return req
