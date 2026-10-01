from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.timeutil import utcnow
from app.models.customer import Customer
from app.models.service_plan import ServicePlan
from app.models.sim_card import SimCard
from app.models.subscription import Subscription
from app.models.subscription_history import SubscriptionHistory
from app.services.audit_service import audit
from app.services.notification_service import notify

LIVE = ("active", "suspended")


def _history(db, sub, action, actor, old_plan=None, new_plan=None, note=None):
    db.add(SubscriptionHistory(subscription_id=sub.id, action=action, old_plan_id=old_plan,
                               new_plan_id=new_plan, note=note, performed_by=getattr(actor, "id", None)))


def _notify_customer(db, sub, title, message):
    customer = db.get(Customer, sub.customer_id)
    if customer:
        notify(db, customer.user_id, title, message, "subscription")


def expire_if_due(db: Session, sub: Subscription) -> Subscription:
    if sub.status == "active" and sub.end_date < utcnow():
        sub.status = "expired"
        _history(db, sub, "expired", None)
    return sub


def create_subscription(db, actor, customer: Customer, plan: ServicePlan, sim: SimCard, auto_renew=False):
    if customer.kyc_status != "verified":
        raise HTTPException(409, "Customer KYC must be verified before creating a subscription "
                                 "(POST /customers/{id}/kyc, then PATCH /customers/kyc/{doc_id}/verify)")
    if not plan.is_active:
        raise HTTPException(409, "Plan is not active")
    if sim.status == "available":
        pass
    elif sim.status == "active" and sim.customer_id == customer.id:
        pass
    else:
        raise HTTPException(409, f"SIM is '{sim.status}' and cannot be used for a new subscription")
    if db.scalar(select(Subscription).where(Subscription.sim_id == sim.id, Subscription.status.in_(LIVE))):
        raise HTTPException(409, "This SIM already has a live subscription")
    now = utcnow()
    sub = Subscription(customer_id=customer.id, plan_id=plan.id, sim_id=sim.id, status="active",
                       start_date=now, end_date=now + timedelta(days=plan.validity_days), auto_renew=auto_renew)
    db.add(sub)
    sim.customer_id = customer.id
    sim.status = "active"
    sim.activated_at = sim.activated_at or now
    db.flush()
    _history(db, sub, "created", actor, new_plan=plan.id)
    audit(db, actor, "create", "subscription", sub.id, f"customer={customer.id} plan={plan.id} sim={sim.id}")
    _notify_customer(db, sub, "Subscription activated", f"Your plan '{plan.name}' is active until {sub.end_date:%Y-%m-%d}.")
    return sub


def suspend(db, actor, sub: Subscription, note=None):
    if sub.status != "active":
        raise HTTPException(409, f"Only active subscriptions can be suspended (current: {sub.status})")
    sub.status = "suspended"
    sim = db.get(SimCard, sub.sim_id)
    if sim and sim.status == "active":
        sim.status = "suspended"
    _history(db, sub, "suspended", actor, note=note)
    audit(db, actor, "suspend", "subscription", sub.id, note)
    _notify_customer(db, sub, "Subscription suspended", note or "Your subscription has been suspended.")


def resume(db, actor, sub: Subscription):
    if sub.status != "suspended":
        raise HTTPException(409, f"Only suspended subscriptions can be resumed (current: {sub.status})")
    sim = db.get(SimCard, sub.sim_id)
    if sim and sim.status not in ("suspended", "active"):
        raise HTTPException(409, f"SIM is '{sim.status}', cannot resume")
    if sub.end_date < utcnow():
        raise HTTPException(409, "Subscription has expired; renew it instead")
    sub.status = "active"
    if sim:
        sim.status = "active"
    _history(db, sub, "resumed", actor)
    audit(db, actor, "resume", "subscription", sub.id)
    _notify_customer(db, sub, "Subscription resumed", "Your subscription is active again.")


def cancel(db, actor, sub: Subscription, note=None):
    if sub.status not in LIVE + ("expired",):
        raise HTTPException(409, f"Subscription is already {sub.status}")
    sub.status = "cancelled"
    sim = db.get(SimCard, sub.sim_id)
    if sim and sim.status in ("active", "suspended"):
        sim.status = "deactivated"
    _history(db, sub, "cancelled", actor, note=note)
    audit(db, actor, "cancel", "subscription", sub.id, note)
    _notify_customer(db, sub, "Subscription cancelled", note or "Your subscription has been cancelled.")


def renew(db, actor, sub: Subscription):
    if sub.status not in ("active", "expired"):
        raise HTTPException(409, f"Only active or expired subscriptions can be renewed (current: {sub.status})")
    sim = db.get(SimCard, sub.sim_id)
    if not sim or sim.status != "active":
        raise HTTPException(409, "SIM must be active to renew")
    plan = db.get(ServicePlan, sub.plan_id)
    base = max(sub.end_date, utcnow())
    sub.end_date = base + timedelta(days=plan.validity_days)
    sub.status = "active"
    _history(db, sub, "renewed", actor, new_plan=plan.id)
    audit(db, actor, "renew", "subscription", sub.id)
    _notify_customer(db, sub, "Subscription renewed", f"Valid until {sub.end_date:%Y-%m-%d}.")


def change_plan(db, actor, sub: Subscription, new_plan: ServicePlan):
    if sub.status != "active":
        raise HTTPException(409, f"Only active subscriptions can change plan (current: {sub.status})")
    if not new_plan.is_active:
        raise HTTPException(409, "Target plan is not active")
    if new_plan.id == sub.plan_id:
        raise HTTPException(409, "Subscription is already on this plan")
    old = sub.plan_id
    sub.plan_id = new_plan.id
    sub.end_date = utcnow() + timedelta(days=new_plan.validity_days)
    _history(db, sub, "plan_changed", actor, old_plan=old, new_plan=new_plan.id)
    audit(db, actor, "change_plan", "subscription", sub.id, f"{old} -> {new_plan.id}")
    _notify_customer(db, sub, "Plan changed", f"You are now on '{new_plan.name}'.")
