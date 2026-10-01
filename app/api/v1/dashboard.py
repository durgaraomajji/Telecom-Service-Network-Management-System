from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import own_customer, require_roles, staff_only
from app.db.session import get_db
from app.models.customer import Customer
from app.models.equipment import Equipment
from app.models.notification import Notification
from app.models.outage import Outage
from app.models.service_plan import ServicePlan
from app.models.service_request import ServiceRequest
from app.models.sim_card import SimCard
from app.models.sla_tracking import SlaTracking
from app.models.subscription import Subscription
from app.models.support_ticket import SupportTicket
from app.models.technician import Technician
from app.models.tower import Tower
from app.models.user import User
from app.schemas.dashboard import CustomerDashboard, DashboardSummary

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


def _count(db, stmt) -> int:
    return db.scalar(stmt) or 0


def _group(db, column) -> dict[str, int]:
    return {k: int(v) for k, v in db.execute(select(column, func.count()).group_by(column)).all()}


@router.get("/summary", response_model=DashboardSummary, summary="Operations overview (staff)")
def summary(db: Session = Depends(get_db), user: User = Depends(staff_only)):
    mrr = db.scalar(select(func.coalesce(func.sum(ServicePlan.price), 0))
                    .join(Subscription, Subscription.plan_id == ServicePlan.id)
                    .where(Subscription.status == "active"))
    tickets = _group(db, SupportTicket.status)
    return DashboardSummary(
        customers=_count(db, select(func.count()).select_from(Customer)),
        users=_count(db, select(func.count()).select_from(User)),
        subscriptions_by_status=_group(db, Subscription.status),
        sims_by_status=_group(db, SimCard.status),
        tickets_by_status=tickets,
        open_tickets=sum(v for k, v in tickets.items() if k not in ("resolved", "closed")),
        sla_breached_tickets=_count(db, select(func.count()).select_from(SlaTracking)
                                    .where((SlaTracking.response_breached.is_(True)) |
                                           (SlaTracking.resolution_breached.is_(True)))),
        active_outages=_count(db, select(func.count()).select_from(Outage).where(Outage.status != "resolved")),
        towers_by_status=_group(db, Tower.status),
        faulty_equipment=_count(db, select(func.count()).select_from(Equipment).where(Equipment.status == "faulty")),
        technicians_available=_count(db, select(func.count()).select_from(Technician)
                                     .where(Technician.is_available.is_(True))),
        monthly_recurring_revenue=float(mrr or 0),
    )


@router.get("/customer", response_model=CustomerDashboard, summary="My account overview (customer)")
def customer_dashboard(db: Session = Depends(get_db), user: User = Depends(require_roles("customer"))):
    mine = own_customer(db, user)
    cid = mine.id if mine else -1
    return CustomerDashboard(
        customer_id=mine.id if mine else None,
        kyc_status=mine.kyc_status if mine else None,
        active_subscriptions=_count(db, select(func.count()).select_from(Subscription)
                                    .where(Subscription.customer_id == cid, Subscription.status == "active")),
        open_tickets=_count(db, select(func.count()).select_from(SupportTicket)
                            .where(SupportTicket.customer_id == cid, SupportTicket.status.notin_(("resolved", "closed")))),
        open_service_requests=_count(db, select(func.count()).select_from(ServiceRequest)
                                     .where(ServiceRequest.customer_id == cid,
                                            ServiceRequest.status.in_(("submitted", "under_review", "approved")))),
        unread_notifications=_count(db, select(func.count()).select_from(Notification)
                                    .where(Notification.user_id == user.id, Notification.is_read.is_(False))),
        active_outages_in_network=_count(db, select(func.count()).select_from(Outage).where(Outage.status != "resolved")),
    )
