from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import SUPPORT, get_or_404, paging, require_roles
from app.api.v1.auth import current_user
from app.core.timeutil import utcnow
from app.db.session import get_db
from app.models.device import Device
from app.models.device_assignment import DeviceAssignment
from app.models.sim_card import SimCard
from app.models.user import User
from app.schemas.device import (DeviceAssign, DeviceAssignmentResponse, DeviceBlock, DeviceCreate, DeviceResponse)
from app.services.audit_service import audit

router = APIRouter(prefix="/devices", tags=["Devices"])


def _open_assignment(db, device_id):
    return db.scalar(select(DeviceAssignment).where(DeviceAssignment.device_id == device_id,
                                                    DeviceAssignment.released_at.is_(None)))


@router.post("/", response_model=DeviceResponse, status_code=201)
def register_device(payload: DeviceCreate, db: Session = Depends(get_db),
                    actor: User = Depends(require_roles(*SUPPORT))):
    if db.scalar(select(Device).where(Device.imei == payload.imei)):
        raise HTTPException(409, "IMEI already registered")
    device = Device(**payload.model_dump())
    db.add(device)
    db.flush()
    audit(db, actor, "create", "device", device.id, payload.imei)
    db.commit()
    db.refresh(device)
    return device


@router.get("/", response_model=list[DeviceResponse])
def list_devices(is_blocked: bool | None = None, page=Depends(paging), db: Session = Depends(get_db),
                 actor: User = Depends(require_roles(*SUPPORT))):
    skip, limit = page
    stmt = select(Device).order_by(Device.id)
    if is_blocked is not None:
        stmt = stmt.where(Device.is_blocked.is_(is_blocked))
    return list(db.scalars(stmt.offset(skip).limit(limit)).all())


@router.get("/{device_id}", response_model=DeviceResponse)
def get_device(device_id: int, db: Session = Depends(get_db), actor: User = Depends(require_roles(*SUPPORT))):
    return get_or_404(db, Device, device_id, "Device")


@router.post("/{device_id}/assign", response_model=DeviceAssignmentResponse, status_code=201,
             summary="Attach a device to an active SIM")
def assign_device(device_id: int, payload: DeviceAssign, db: Session = Depends(get_db),
                  actor: User = Depends(require_roles(*SUPPORT))):
    device = get_or_404(db, Device, device_id, "Device")
    sim = get_or_404(db, SimCard, payload.sim_id, "SIM")
    if device.is_blocked:
        raise HTTPException(409, "Device is blocked (lost/stolen) and cannot be assigned")
    if sim.status != "active":
        raise HTTPException(409, f"SIM must be active (current: {sim.status})")
    if _open_assignment(db, device_id):
        raise HTTPException(409, "Device is already assigned; release it first")
    other = db.scalar(select(DeviceAssignment).where(DeviceAssignment.sim_id == sim.id,
                                                     DeviceAssignment.released_at.is_(None)))
    if other:
        raise HTTPException(409, f"SIM is already in use by device {other.device_id}")
    rec = DeviceAssignment(device_id=device.id, sim_id=sim.id, customer_id=sim.customer_id)
    db.add(rec)
    db.flush()
    audit(db, actor, "assign", "device", device.id, f"sim={sim.id}")
    db.commit()
    db.refresh(rec)
    return rec


@router.post("/{device_id}/release", response_model=DeviceAssignmentResponse)
def release_device(device_id: int, db: Session = Depends(get_db), actor: User = Depends(require_roles(*SUPPORT))):
    get_or_404(db, Device, device_id, "Device")
    rec = _open_assignment(db, device_id)
    if not rec:
        raise HTTPException(409, "Device is not assigned")
    rec.released_at = utcnow()
    audit(db, actor, "release", "device", device_id)
    db.commit()
    db.refresh(rec)
    return rec


@router.patch("/{device_id}/block", response_model=DeviceResponse, summary="Block / unblock a device (lost or stolen)")
def block_device(device_id: int, payload: DeviceBlock, db: Session = Depends(get_db),
                 actor: User = Depends(require_roles(*SUPPORT))):
    device = get_or_404(db, Device, device_id, "Device")
    device.is_blocked = payload.is_blocked
    if payload.is_blocked:
        rec = _open_assignment(db, device_id)
        if rec:
            rec.released_at = utcnow()
    audit(db, actor, "block" if payload.is_blocked else "unblock", "device", device.id)
    db.commit()
    db.refresh(device)
    return device


@router.get("/{device_id}/assignments", response_model=list[DeviceAssignmentResponse])
def device_assignments(device_id: int, db: Session = Depends(get_db), actor: User = Depends(require_roles(*SUPPORT))):
    get_or_404(db, Device, device_id, "Device")
    return list(db.scalars(select(DeviceAssignment).where(DeviceAssignment.device_id == device_id)
                           .order_by(DeviceAssignment.id)).all())
