from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import NETWORK, get_or_404, paging, require_roles, staff_only
from app.db.session import get_db
from app.models.tower import Tower
from app.models.tower_coverage import TowerCoverage
from app.models.user import User
from app.schemas.tower import CoverageCreate, CoverageResponse, TowerCreate, TowerResponse, TowerUpdate
from app.services.audit_service import audit

router = APIRouter(prefix="/towers", tags=["Network Towers"])


@router.post("/", response_model=TowerResponse, status_code=201)
def create_tower(payload: TowerCreate, db: Session = Depends(get_db), actor: User = Depends(require_roles(*NETWORK))):
    if db.scalar(select(Tower).where(Tower.name == payload.name)):
        raise HTTPException(409, "Tower name already exists")
    tower = Tower(**payload.model_dump())
    db.add(tower)
    db.flush()
    audit(db, actor, "create", "tower", tower.id, tower.name)
    db.commit()
    db.refresh(tower)
    return tower


@router.get("/", response_model=list[TowerResponse])
def list_towers(city: str | None = Query(default=None), status: str | None = Query(default=None),
                page=Depends(paging), db: Session = Depends(get_db), user: User = Depends(staff_only)):
    skip, limit = page
    stmt = select(Tower).order_by(Tower.id)
    if city:
        stmt = stmt.where(Tower.city == city)
    if status:
        stmt = stmt.where(Tower.status == status)
    return list(db.scalars(stmt.offset(skip).limit(limit)).all())


@router.get("/{tower_id}", response_model=TowerResponse)
def get_tower(tower_id: int, db: Session = Depends(get_db), user: User = Depends(staff_only)):
    return get_or_404(db, Tower, tower_id, "Tower")


@router.patch("/{tower_id}", response_model=TowerResponse)
def update_tower(tower_id: int, payload: TowerUpdate, db: Session = Depends(get_db),
                 actor: User = Depends(require_roles(*NETWORK))):
    tower = get_or_404(db, Tower, tower_id, "Tower")
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"] != tower.name and db.scalar(select(Tower).where(Tower.name == data["name"])):
        raise HTTPException(409, "Tower name already exists")
    for key, value in data.items():
        setattr(tower, key, value)
    audit(db, actor, "update", "tower", tower.id, ",".join(data))
    db.commit()
    db.refresh(tower)
    return tower


@router.post("/{tower_id}/coverage", response_model=CoverageResponse, status_code=201)
def add_coverage(tower_id: int, payload: CoverageCreate, db: Session = Depends(get_db),
                 actor: User = Depends(require_roles(*NETWORK))):
    get_or_404(db, Tower, tower_id, "Tower")
    cov = TowerCoverage(tower_id=tower_id, **payload.model_dump())
    db.add(cov)
    db.flush()
    audit(db, actor, "add_coverage", "tower", tower_id, payload.area_name)
    db.commit()
    db.refresh(cov)
    return cov


@router.get("/{tower_id}/coverage", response_model=list[CoverageResponse])
def list_coverage(tower_id: int, db: Session = Depends(get_db), user: User = Depends(staff_only)):
    get_or_404(db, Tower, tower_id, "Tower")
    return list(db.scalars(select(TowerCoverage).where(TowerCoverage.tower_id == tower_id)
                           .order_by(TowerCoverage.id)).all())
