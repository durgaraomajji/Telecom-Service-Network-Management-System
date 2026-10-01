from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import SUPPORT, ensure_customer_access, get_or_404, own_customer, paging, require_roles
from app.api.v1.auth import current_user
from app.core.security import hash_password
from app.core.timeutil import utcnow
from app.db.session import get_db
from app.models.customer import Customer
from app.models.kyc import KycDocument
from app.models.user import User
from app.schemas.customer import (CustomerCreate, CustomerProfileCreate, CustomerResponse, CustomerUpdate)
from app.schemas.kyc import KycCreate, KycResponse, KycVerify
from app.services.audit_service import audit
from app.services.notification_service import notify

router = APIRouter(prefix="/customers", tags=["Customers"])


def _number() -> str:
    return f"CUS-{uuid4().hex[:12].upper()}"


@router.post("/", response_model=CustomerResponse, status_code=201, summary="Create a customer (staff)")
def create_customer(payload: CustomerCreate, db: Session = Depends(get_db),
                    actor: User = Depends(require_roles(*SUPPORT))):
    if db.scalar(select(User).where(User.email == payload.email)):
        raise HTTPException(409, "Email already registered")
    user = User(full_name=payload.full_name, email=payload.email,
                password_hash=hash_password(payload.password), role="customer")
    db.add(user)
    db.flush()
    customer = Customer(user_id=user.id, customer_number=_number(), phone=payload.phone)
    db.add(customer)
    db.flush()
    audit(db, actor, "create", "customer", customer.id, payload.email)
    db.commit()
    db.refresh(customer)
    return customer


@router.get("/", response_model=list[CustomerResponse], summary="List customers (staff)")
def list_customers(page=Depends(paging), db: Session = Depends(get_db),
                   actor: User = Depends(require_roles(*SUPPORT))):
    skip, limit = page
    return list(db.scalars(select(Customer).order_by(Customer.id).offset(skip).limit(limit)).all())


@router.post("/me", response_model=CustomerResponse, status_code=201,
             summary="Create my customer profile (for a self-registered customer account)")
def create_my_profile(payload: CustomerProfileCreate, db: Session = Depends(get_db),
                      user: User = Depends(require_roles("customer"))):
    if own_customer(db, user):
        raise HTTPException(409, "Customer profile already exists")
    customer = Customer(user_id=user.id, customer_number=_number(), phone=payload.phone)
    db.add(customer)
    db.flush()
    audit(db, user, "create", "customer", customer.id, "self-service profile")
    db.commit()
    db.refresh(customer)
    return customer


@router.get("/me", response_model=CustomerResponse, summary="My customer profile")
def get_my_profile(db: Session = Depends(get_db), user: User = Depends(require_roles("customer"))):
    customer = own_customer(db, user)
    if not customer:
        raise HTTPException(404, "No customer profile yet. Create one with POST /api/v1/customers/me")
    return customer


@router.patch("/kyc/{doc_id}/verify", response_model=KycResponse, summary="Verify or reject a KYC document (staff)")
def verify_kyc(doc_id: int, payload: KycVerify, db: Session = Depends(get_db),
               actor: User = Depends(require_roles(*SUPPORT))):
    doc = get_or_404(db, KycDocument, doc_id, "KYC document")
    if doc.status != "pending":
        raise HTTPException(409, f"Document is already {doc.status}")
    doc.status, doc.remarks = payload.status, payload.remarks
    doc.verified_by, doc.verified_at = actor.id, utcnow()
    customer = db.get(Customer, doc.customer_id)
    if payload.status == "verified":
        customer.kyc_status = "verified"
    elif customer.kyc_status != "verified":
        customer.kyc_status = "rejected"
    audit(db, actor, f"kyc_{payload.status}", "kyc_document", doc.id, payload.remarks)
    notify(db, customer.user_id, f"KYC {payload.status}", payload.remarks or f"Your KYC document was {payload.status}.", "kyc")
    db.commit()
    db.refresh(doc)
    return doc


@router.get("/{customer_id}", response_model=CustomerResponse)
def get_customer(customer_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    ensure_customer_access(db, user, customer_id)
    return get_or_404(db, Customer, customer_id, "Customer")


@router.patch("/{customer_id}", response_model=CustomerResponse)
def update_customer(customer_id: int, payload: CustomerUpdate, db: Session = Depends(get_db),
                    user: User = Depends(current_user)):
    ensure_customer_access(db, user, customer_id)
    customer = get_or_404(db, Customer, customer_id, "Customer")
    if payload.phone:
        customer.phone = payload.phone
    audit(db, user, "update", "customer", customer.id)
    db.commit()
    db.refresh(customer)
    return customer


@router.post("/{customer_id}/kyc", response_model=KycResponse, status_code=201, summary="Submit a KYC document")
def submit_kyc(customer_id: int, payload: KycCreate, db: Session = Depends(get_db),
               user: User = Depends(current_user)):
    ensure_customer_access(db, user, customer_id)
    customer = get_or_404(db, Customer, customer_id, "Customer")
    doc = KycDocument(customer_id=customer.id, document_type=payload.document_type,
                      document_number=payload.document_number)
    db.add(doc)
    if customer.kyc_status == "rejected":
        customer.kyc_status = "pending"
    db.flush()
    audit(db, user, "submit_kyc", "kyc_document", doc.id, payload.document_type)
    db.commit()
    db.refresh(doc)
    return doc


@router.get("/{customer_id}/kyc", response_model=list[KycResponse])
def list_kyc(customer_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    ensure_customer_access(db, user, customer_id)
    get_or_404(db, Customer, customer_id, "Customer")
    return list(db.scalars(select(KycDocument).where(KycDocument.customer_id == customer_id)
                           .order_by(KycDocument.id)).all())
