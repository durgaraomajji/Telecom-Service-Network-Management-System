from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import OPS, get_or_404, paging, require_roles
from app.db.session import get_db
from app.models.service_plan import ServicePlan
from app.models.user import User
from app.schemas.service_plan import PlanCreate, PlanResponse, PlanUpdate
from app.services.audit_service import audit

router = APIRouter(prefix="/plans", tags=["Service Plans"])


@router.post("/", response_model=PlanResponse, status_code=201)
def create_plan(payload: PlanCreate, db: Session = Depends(get_db),
                actor: User = Depends(require_roles(*OPS))):
    if db.scalar(select(ServicePlan).where(ServicePlan.name == payload.name)):
        raise HTTPException(409, "Plan name already exists")
    plan = ServicePlan(**payload.model_dump())
    db.add(plan)
    db.flush()
    audit(db, actor, "create", "service_plan", plan.id, plan.name)
    db.commit()
    db.refresh(plan)
    return plan


@router.get("/", response_model=list[PlanResponse], summary="List active plans (public)")
def list_plans(page=Depends(paging), db: Session = Depends(get_db)):
    skip, limit = page
    return list(db.scalars(select(ServicePlan).where(ServicePlan.is_active.is_(True))
                           .order_by(ServicePlan.id).offset(skip).limit(limit)).all())


@router.get("/{plan_id}", response_model=PlanResponse)
def get_plan(plan_id: int, db: Session = Depends(get_db)):
    return get_or_404(db, ServicePlan, plan_id, "Plan")


@router.patch("/{plan_id}", response_model=PlanResponse)
def update_plan(plan_id: int, payload: PlanUpdate, db: Session = Depends(get_db),
                actor: User = Depends(require_roles(*OPS))):
    plan = get_or_404(db, ServicePlan, plan_id, "Plan")
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"] != plan.name and \
            db.scalar(select(ServicePlan).where(ServicePlan.name == data["name"])):
        raise HTTPException(409, "Plan name already exists")
    for key, value in data.items():
        setattr(plan, key, value)
    audit(db, actor, "update", "service_plan", plan.id, ",".join(data))
    db.commit()
    db.refresh(plan)
    return plan


@router.delete("/{plan_id}", response_model=PlanResponse, summary="Deactivate a plan (existing subscriptions keep working)")
def deactivate_plan(plan_id: int, db: Session = Depends(get_db), actor: User = Depends(require_roles(*OPS))):
    plan = get_or_404(db, ServicePlan, plan_id, "Plan")
    plan.is_active = False
    audit(db, actor, "deactivate", "service_plan", plan.id)
    db.commit()
    db.refresh(plan)
    return plan
