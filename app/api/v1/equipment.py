from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import NETWORK, get_or_404, paging, require_roles, staff_only
from app.db.session import get_db
from app.models.equipment import Equipment
from app.models.equipment_metrics import EquipmentMetric
from app.models.tower import Tower
from app.models.user import User
from app.schemas.equipment import (EquipmentCreate, EquipmentResponse, EquipmentStatusUpdate, MetricCreate,
                                   MetricResponse)
from app.services.audit_service import audit

router = APIRouter(prefix="/equipment", tags=["Network Equipment"])
MAX_TEMP_C, MAX_CPU = 85.0, 95.0  # a reading above these marks the equipment faulty


@router.post("/", response_model=EquipmentResponse, status_code=201)
def create_equipment(payload: EquipmentCreate, db: Session = Depends(get_db),
                     actor: User = Depends(require_roles(*NETWORK))):
    get_or_404(db, Tower, payload.tower_id, "Tower")
    if db.scalar(select(Equipment).where(Equipment.serial_number == payload.serial_number)):
        raise HTTPException(409, "Serial number already registered")
    eq = Equipment(**payload.model_dump())
    db.add(eq)
    db.flush()
    audit(db, actor, "create", "equipment", eq.id, eq.serial_number)
    db.commit()
    db.refresh(eq)
    return eq


@router.get("/", response_model=list[EquipmentResponse])
def list_equipment(tower_id: int | None = Query(default=None), status: str | None = Query(default=None),
                   page=Depends(paging), db: Session = Depends(get_db), user: User = Depends(staff_only)):
    skip, limit = page
    stmt = select(Equipment).order_by(Equipment.id)
    if tower_id:
        stmt = stmt.where(Equipment.tower_id == tower_id)
    if status:
        stmt = stmt.where(Equipment.status == status)
    return list(db.scalars(stmt.offset(skip).limit(limit)).all())


@router.get("/{equipment_id}", response_model=EquipmentResponse)
def get_equipment(equipment_id: int, db: Session = Depends(get_db), user: User = Depends(staff_only)):
    return get_or_404(db, Equipment, equipment_id, "Equipment")


@router.patch("/{equipment_id}/status", response_model=EquipmentResponse)
def set_status(equipment_id: int, payload: EquipmentStatusUpdate, db: Session = Depends(get_db),
               actor: User = Depends(require_roles(*NETWORK, "field_technician"))):
    eq = get_or_404(db, Equipment, equipment_id, "Equipment")
    if eq.status == "decommissioned":
        raise HTTPException(409, "Equipment is decommissioned")
    old, eq.status = eq.status, payload.status
    audit(db, actor, "status_change", "equipment", eq.id, f"{old} -> {payload.status}")
    db.commit()
    db.refresh(eq)
    return eq


@router.post("/{equipment_id}/metrics", response_model=MetricResponse, status_code=201,
             summary="Record a health reading (marks the equipment faulty if too hot / overloaded)")
def add_metric(equipment_id: int, payload: MetricCreate, db: Session = Depends(get_db),
               actor: User = Depends(require_roles(*NETWORK, "field_technician"))):
    eq = get_or_404(db, Equipment, equipment_id, "Equipment")
    if eq.status == "decommissioned":
        raise HTTPException(409, "Equipment is decommissioned")
    metric = EquipmentMetric(equipment_id=equipment_id, **payload.model_dump())
    db.add(metric)
    if eq.status == "operational" and (payload.temperature_c > MAX_TEMP_C or payload.cpu_load > MAX_CPU):
        eq.status = "faulty"
        audit(db, actor, "auto_fault", "equipment", eq.id,
              f"temp={payload.temperature_c}C cpu={payload.cpu_load}%")
    db.commit()
    db.refresh(metric)
    return metric


@router.get("/{equipment_id}/metrics", response_model=list[MetricResponse])
def list_metrics(equipment_id: int, limit: int = Query(50, ge=1, le=500), db: Session = Depends(get_db),
                 user: User = Depends(staff_only)):
    get_or_404(db, Equipment, equipment_id, "Equipment")
    return list(db.scalars(select(EquipmentMetric).where(EquipmentMetric.equipment_id == equipment_id)
                           .order_by(EquipmentMetric.id.desc()).limit(limit)).all())
