"""Create demo data so every Swagger endpoint has something to work with (safe to re-run).

    python -m scripts.seed_demo_data

Logins (password for all: Demo@12345):
    admin@telecom.demo (super_admin)      ops@telecom.demo (operations_manager)
    support@telecom.demo (support_agent)  network@telecom.demo (network_engineer)
    tech@telecom.demo (field_technician)  customer@telecom.demo (customer, KYC verified)
"""
from uuid import uuid4

from sqlalchemy import select

from app.core.security import hash_password
from app.core.timeutil import utcnow
from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.models.address import Address
from app.models.customer import Customer
from app.models.equipment import Equipment
from app.models.kyc import KycDocument
from app.models.service_plan import ServicePlan
from app.models.sim_card import SimCard
from app.models.technician import Technician
from app.models.technician_skill import TechnicianSkill
from app.models.tower import Tower
from app.models.tower_coverage import TowerCoverage
from app.models.user import User

PASSWORD = "Demo@12345"
USERS = [("admin@telecom.demo", "Demo Admin", "super_admin"), ("ops@telecom.demo", "Demo Operations", "operations_manager"),
         ("support@telecom.demo", "Demo Support", "support_agent"), ("network@telecom.demo", "Demo Network Engineer", "network_engineer"),
         ("tech@telecom.demo", "Demo Technician", "field_technician"), ("customer@telecom.demo", "Demo Customer", "customer")]
PLANS = [("Prepaid 199", "prepaid", 199, 28, 1024, 100, 100), ("Prepaid 399", "prepaid", 399, 56, 3072, 300, 300),
         ("Postpaid 699", "postpaid", 699, 30, 20480, 2000, 1000)]


def main():
    init_db()
    db = SessionLocal()
    try:
        users = {}
        for email, name, role in USERS:
            user = db.scalar(select(User).where(User.email == email))
            if not user:
                user = User(email=email, full_name=name, password_hash=hash_password(PASSWORD), role=role)
                db.add(user)
                db.flush()
            users[role] = user
        for name, ptype, price, days, data, voice, sms in PLANS:
            if not db.scalar(select(ServicePlan).where(ServicePlan.name == name)):
                db.add(ServicePlan(name=name, plan_type=ptype, price=price, validity_days=days,
                                   data_limit_mb=data, voice_minutes=voice, sms_limit=sms))
        for i in range(1, 6):
            iccid, msisdn = f"899110120000320{4500 + i}", f"98765000{i:02d}"
            if not db.scalar(select(SimCard).where(SimCard.iccid == iccid)):
                db.add(SimCard(iccid=iccid, msisdn=msisdn, status="available"))
        customer = db.scalar(select(Customer).where(Customer.user_id == users["customer"].id))
        if not customer:
            customer = Customer(user_id=users["customer"].id, customer_number=f"CUS-{uuid4().hex[:12].upper()}",
                                phone="9876543210", kyc_status="verified")
            db.add(customer)
            db.flush()
            db.add(Address(customer_id=customer.id, line1="12 MG Road", city="Bengaluru", state="Karnataka",
                           postal_code="560001", is_primary=True))
            db.add(KycDocument(customer_id=customer.id, document_type="aadhaar", document_number="1234-5678-9012",
                               status="verified", verified_by=users["support_agent"].id, verified_at=utcnow()))
        if not db.scalar(select(Tower).where(Tower.name == "BLR-Central-01")):
            tower = Tower(name="BLR-Central-01", city="Bengaluru", latitude=12.9716, longitude=77.5946, capacity_users=5000)
            db.add(tower)
            db.flush()
            db.add(TowerCoverage(tower_id=tower.id, area_name="MG Road", radius_km=3, technology="5G"))
            db.add(Equipment(tower_id=tower.id, name="Antenna A1", equipment_type="antenna", serial_number="SN-DEMO-001"))
        if not db.scalar(select(Technician).where(Technician.user_id == users["field_technician"].id)):
            tech = Technician(user_id=users["field_technician"].id, name="Demo Technician", phone="9123456780", region="Bengaluru")
            db.add(tech)
            db.flush()
            db.add(TechnicianSkill(technician_id=tech.id, skill="power"))
        db.commit()
        print(__doc__)
    finally:
        db.close()


if __name__ == "__main__":
    main()
