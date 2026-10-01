from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import OPS, get_or_404, paging, require_roles, staff_only
from app.core.timeutil import utcnow
from app.db.session import get_db
from app.models.equipment import Equipment
from app.models.outage import Outage
from app.models.support_ticket import SupportTicket
from app.models.technician import Technician
from app.models.technician_assignment import TechnicianAssignment
from app.models.technician_skill import TechnicianSkill
from app.models.user import User
from app.schemas.technician import (SkillCreate, TechnicianAvailability, TechnicianCreate, TechnicianResponse,
                                    WorkAssignCreate, WorkAssignmentResponse, WorkStatusUpdate)
from app.services.audit_service import audit
from app.services.notification_service import notify

router = APIRouter(prefix="/technicians", tags=["Technicians"])
DISPATCH = ("super_admin", "operations_manager", "network_engineer", "support_agent")


def _view(db, tech: Technician) -> TechnicianResponse:
    skills = list(db.scalars(select(TechnicianSkill.skill).where(TechnicianSkill.technician_id == tech.id)
                             .order_by(TechnicianSkill.id)).all())
    resp = TechnicianResponse.model_validate(tech)
    resp.skills = skills
    return resp


@router.post("/", response_model=TechnicianResponse, status_code=201)
def create_technician(payload: TechnicianCreate, db: Session = Depends(get_db),
                      actor: User = Depends(require_roles(*OPS))):
    if payload.user_id:
        user = get_or_404(db, User, payload.user_id, "User")
        if user.role != "field_technician":
            raise HTTPException(409, "Linked user must have the field_technician role")
        if db.scalar(select(Technician).where(Technician.user_id == payload.user_id)):
            raise HTTPException(409, "That user is already linked to a technician")
    tech = Technician(name=payload.name, phone=payload.phone, region=payload.region, user_id=payload.user_id)
    db.add(tech)
    db.flush()
    for skill in dict.fromkeys(s.strip().lower() for s in payload.skills if s.strip()):
        db.add(TechnicianSkill(technician_id=tech.id, skill=skill))
    audit(db, actor, "create", "technician", tech.id, tech.name)
    db.commit()
    db.refresh(tech)
    return _view(db, tech)


@router.get("/", response_model=list[TechnicianResponse])
def list_technicians(region: str | None = Query(default=None), available: bool | None = Query(default=None),
                     skill: str | None = Query(default=None), page=Depends(paging),
                     db: Session = Depends(get_db), user: User = Depends(staff_only)):
    skip, limit = page
    stmt = select(Technician).order_by(Technician.id)
    if region:
        stmt = stmt.where(Technician.region == region)
    if available is not None:
        stmt = stmt.where(Technician.is_available.is_(available))
    if skill:
        stmt = stmt.where(Technician.id.in_(select(TechnicianSkill.technician_id)
                                            .where(TechnicianSkill.skill == skill.strip().lower())))
    return [_view(db, t) for t in db.scalars(stmt.offset(skip).limit(limit)).all()]


@router.get("/my-assignments", response_model=list[WorkAssignmentResponse],
            summary="Work assigned to me (field technician)")
def my_assignments(db: Session = Depends(get_db), user: User = Depends(require_roles("field_technician"))):
    tech = db.scalar(select(Technician).where(Technician.user_id == user.id))
    if not tech:
        return []
    return list(db.scalars(select(TechnicianAssignment).where(TechnicianAssignment.technician_id == tech.id)
                           .order_by(TechnicianAssignment.id.desc())).all())


@router.patch("/assignments/{assignment_id}/status", response_model=WorkAssignmentResponse)
def update_work_status(assignment_id: int, payload: WorkStatusUpdate, db: Session = Depends(get_db),
                       user: User = Depends(require_roles(*DISPATCH, "field_technician"))):
    work = get_or_404(db, TechnicianAssignment, assignment_id, "Assignment")
    tech = db.get(Technician, work.technician_id)
    if user.role == "field_technician" and tech.user_id != user.id:
        raise HTTPException(403, "You can only update your own assignments")
    if work.status in ("completed", "cancelled"):
        raise HTTPException(409, f"Assignment is already {work.status}")
    if payload.status == "in_progress" and work.status != "assigned":
        raise HTTPException(409, f"Cannot start an assignment that is {work.status}")
    work.status = payload.status
    if payload.status in ("completed", "cancelled"):
        work.completed_at = utcnow()
        open_left = db.scalar(select(TechnicianAssignment.id).where(
            TechnicianAssignment.technician_id == tech.id, TechnicianAssignment.id != work.id,
            TechnicianAssignment.status.in_(("assigned", "in_progress"))))
        if not open_left:
            tech.is_available = True
    audit(db, user, f"work_{payload.status}", "technician_assignment", work.id)
    db.commit()
    db.refresh(work)
    return work


@router.get("/{tech_id}", response_model=TechnicianResponse)
def get_technician(tech_id: int, db: Session = Depends(get_db), user: User = Depends(staff_only)):
    return _view(db, get_or_404(db, Technician, tech_id, "Technician"))


@router.patch("/{tech_id}/availability", response_model=TechnicianResponse)
def set_availability(tech_id: int, payload: TechnicianAvailability, db: Session = Depends(get_db),
                     actor: User = Depends(require_roles(*OPS))):
    tech = get_or_404(db, Technician, tech_id, "Technician")
    tech.is_available = payload.is_available
    audit(db, actor, "availability", "technician", tech.id, str(payload.is_available))
    db.commit()
    db.refresh(tech)
    return _view(db, tech)


@router.post("/{tech_id}/skills", response_model=TechnicianResponse, status_code=201)
def add_skill(tech_id: int, payload: SkillCreate, db: Session = Depends(get_db),
              actor: User = Depends(require_roles(*OPS))):
    tech = get_or_404(db, Technician, tech_id, "Technician")
    skill = payload.skill.strip().lower()
    if db.scalar(select(TechnicianSkill).where(TechnicianSkill.technician_id == tech_id, TechnicianSkill.skill == skill)):
        raise HTTPException(409, "Skill already added")
    db.add(TechnicianSkill(technician_id=tech_id, skill=skill))
    audit(db, actor, "add_skill", "technician", tech_id, skill)
    db.commit()
    return _view(db, tech)


@router.post("/{tech_id}/assignments", response_model=WorkAssignmentResponse, status_code=201,
             summary="Dispatch a technician to an outage, ticket or equipment job")
def assign_work(tech_id: int, payload: WorkAssignCreate, db: Session = Depends(get_db),
                actor: User = Depends(require_roles(*DISPATCH))):
    tech = get_or_404(db, Technician, tech_id, "Technician")
    if not tech.is_available:
        raise HTTPException(409, "Technician is not available")
    if not (payload.outage_id or payload.ticket_id or payload.equipment_id):
        raise HTTPException(422, "Give at least one of outage_id, ticket_id or equipment_id")
    if payload.outage_id:
        get_or_404(db, Outage, payload.outage_id, "Outage")
    if payload.ticket_id:
        get_or_404(db, SupportTicket, payload.ticket_id, "Ticket")
    if payload.equipment_id:
        get_or_404(db, Equipment, payload.equipment_id, "Equipment")
    work = TechnicianAssignment(technician_id=tech.id, assigned_by=actor.id, **payload.model_dump())
    db.add(work)
    tech.is_available = False
    db.flush()
    audit(db, actor, "assign_work", "technician", tech.id, payload.task)
    notify(db, tech.user_id, "New job assigned", payload.task, "assignment")
    db.commit()
    db.refresh(work)
    return work


@router.get("/{tech_id}/assignments", response_model=list[WorkAssignmentResponse])
def list_work(tech_id: int, db: Session = Depends(get_db), user: User = Depends(staff_only)):
    tech = get_or_404(db, Technician, tech_id, "Technician")
    if user.role == "field_technician" and tech.user_id != user.id:
        raise HTTPException(403, "You can only view your own assignments")
    return list(db.scalars(select(TechnicianAssignment).where(TechnicianAssignment.technician_id == tech_id)
                           .order_by(TechnicianAssignment.id)).all())
