from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.deps import STAFF_ROLES, ensure_customer_access, get_or_404, own_customer, paging, resolve_customer_id
from app.api.v1.auth import current_user
from app.db.session import get_db
from app.models.address import Address
from app.models.user import User
from app.schemas.address import AddressCreate, AddressResponse, AddressUpdate
from app.services.audit_service import audit

router = APIRouter(prefix="/addresses", tags=["Addresses"])


def _clear_primary(db, customer_id, except_id=None):
    stmt = update(Address).where(Address.customer_id == customer_id)
    if except_id:
        stmt = stmt.where(Address.id != except_id)
    db.execute(stmt.values(is_primary=False))


@router.post("/", response_model=AddressResponse, status_code=201)
def create_address(payload: AddressCreate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    customer_id = resolve_customer_id(db, user, payload.customer_id)
    data = payload.model_dump(exclude={"customer_id"})
    first = db.scalar(select(Address.id).where(Address.customer_id == customer_id)) is None
    addr = Address(customer_id=customer_id, **data)
    if first:
        addr.is_primary = True
    db.add(addr)
    db.flush()
    if addr.is_primary:
        _clear_primary(db, customer_id, addr.id)
    audit(db, user, "create", "address", addr.id)
    db.commit()
    db.refresh(addr)
    return addr


@router.get("/", response_model=list[AddressResponse])
def list_addresses(customer_id: int | None = Query(default=None), page=Depends(paging),
                   db: Session = Depends(get_db), user: User = Depends(current_user)):
    skip, limit = page
    stmt = select(Address).order_by(Address.id)
    if user.role in STAFF_ROLES:
        if customer_id:
            stmt = stmt.where(Address.customer_id == customer_id)
    else:
        mine = own_customer(db, user)
        if not mine:
            return []
        stmt = stmt.where(Address.customer_id == mine.id)
    return list(db.scalars(stmt.offset(skip).limit(limit)).all())


@router.get("/{address_id}", response_model=AddressResponse)
def get_address(address_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    addr = get_or_404(db, Address, address_id, "Address")
    ensure_customer_access(db, user, addr.customer_id)
    return addr


@router.put("/{address_id}", response_model=AddressResponse)
def update_address(address_id: int, payload: AddressUpdate, db: Session = Depends(get_db),
                   user: User = Depends(current_user)):
    addr = get_or_404(db, Address, address_id, "Address")
    ensure_customer_access(db, user, addr.customer_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(addr, key, value)
    if addr.is_primary:
        _clear_primary(db, addr.customer_id, addr.id)
    audit(db, user, "update", "address", addr.id)
    db.commit()
    db.refresh(addr)
    return addr


@router.delete("/{address_id}", status_code=204)
def delete_address(address_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    addr = get_or_404(db, Address, address_id, "Address")
    ensure_customer_access(db, user, addr.customer_id)
    db.delete(addr)
    audit(db, user, "delete", "address", address_id)
    db.commit()
