from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import OPS, require_roles
from app.core.timeutil import utcnow
from app.db.session import get_db
from app.models.outage import Outage
from app.models.service_plan import ServicePlan
from app.models.sim_card import SimCard
from app.models.sla_tracking import SlaTracking
from app.models.subscription_history import SubscriptionHistory
from app.models.support_ticket import SupportTicket
from app.models.usage_record import UsageRecord
from app.models.user import User
from app.schemas.reports import (OutageReport, RevenueReport, RevenueRow, SlaReport, TicketReport, UsageReport)
from app.services import sla_service

router = APIRouter(prefix="/reports", tags=["Reports"])
_ops = require_roles(*OPS)


def _range(stmt, column, date_from, date_to):
    if date_from:
        stmt = stmt.where(column >= date_from)
    if date_to:
        stmt = stmt.where(column <= date_to)
    return stmt


def _group(db, column, stmt_filter=None) -> dict[str, int]:
    stmt = select(column, func.count()).group_by(column)
    if stmt_filter is not None:
        stmt = stmt_filter(stmt)
    return {k: int(v) for k, v in db.execute(stmt).all()}


@router.get("/revenue", response_model=RevenueReport, summary="Revenue from plan activations and renewals")
def revenue(date_from: datetime | None = Query(default=None), date_to: datetime | None = Query(default=None),
            db: Session = Depends(get_db), user: User = Depends(_ops)):
    stmt = (select(ServicePlan.id, ServicePlan.name, func.count(SubscriptionHistory.id), func.sum(ServicePlan.price))
            .join(ServicePlan, ServicePlan.id == SubscriptionHistory.new_plan_id)
            .where(SubscriptionHistory.action.in_(("created", "renewed")))
            .group_by(ServicePlan.id, ServicePlan.name).order_by(ServicePlan.id))
    stmt = _range(stmt, SubscriptionHistory.created_at, date_from, date_to)
    rows = [RevenueRow(plan_id=i, plan_name=n, charges=int(c), revenue=float(r or 0)) for i, n, c, r in db.execute(stmt).all()]
    return RevenueReport(rows=rows, total_charges=sum(r.charges for r in rows),
                         total_revenue=round(sum(r.revenue for r in rows), 2))


@router.get("/tickets", response_model=TicketReport)
def tickets(date_from: datetime | None = Query(default=None), date_to: datetime | None = Query(default=None),
            db: Session = Depends(get_db), user: User = Depends(_ops)):
    def flt(s):
        return _range(s, SupportTicket.created_at, date_from, date_to)
    by_status = _group(db, SupportTicket.status, flt)
    resolved = db.execute(_range(select(SupportTicket.created_at, SupportTicket.resolved_at)
                                 .where(SupportTicket.resolved_at.is_not(None)),
                                 SupportTicket.created_at, date_from, date_to)).all()
    hours = [(r - c).total_seconds() / 3600 for c, r in resolved]
    return TicketReport(total=sum(by_status.values()), by_status=by_status,
                        by_priority=_group(db, SupportTicket.priority, flt),
                        by_category=_group(db, SupportTicket.category, flt),
                        avg_resolution_hours=round(sum(hours) / len(hours), 2) if hours else None)


@router.get("/sla-compliance", response_model=SlaReport)
def sla_compliance(db: Session = Depends(get_db), user: User = Depends(_ops)):
    tracks = db.scalars(select(SlaTracking)).all()
    now = utcnow()
    for t in tracks:
        sla_service.refresh_flags(t, now)
    db.commit()
    total = len(tracks)
    bad_resp = sum(t.response_breached for t in tracks)
    bad_reso = sum(t.resolution_breached for t in tracks)
    ok = sum(1 for t in tracks if not (t.response_breached or t.resolution_breached))
    return SlaReport(tracked=total, response_breached=bad_resp, resolution_breached=bad_reso,
                     compliance_percent=round(100 * ok / total, 1) if total else 100.0)


@router.get("/sims", response_model=dict[str, int], summary="SIM inventory by status")
def sims(db: Session = Depends(get_db), user: User = Depends(_ops)):
    return _group(db, SimCard.status)


@router.get("/outages", response_model=OutageReport)
def outages(date_from: datetime | None = Query(default=None), date_to: datetime | None = Query(default=None),
            db: Session = Depends(get_db), user: User = Depends(_ops)):
    def flt(s):
        return _range(s, Outage.started_at, date_from, date_to)
    by_status = _group(db, Outage.status, flt)
    done = db.execute(_range(select(Outage.started_at, Outage.resolved_at).where(Outage.resolved_at.is_not(None)),
                             Outage.started_at, date_from, date_to)).all()
    hours = [(r - s).total_seconds() / 3600 for s, r in done]
    return OutageReport(total=sum(by_status.values()), by_severity=_group(db, Outage.severity, flt),
                        by_status=by_status,
                        avg_duration_hours=round(sum(hours) / len(hours), 2) if hours else None)


@router.get("/usage", response_model=UsageReport, summary="Total data (MB) / voice (min) / sms by type")
def usage(date_from: datetime | None = Query(default=None), date_to: datetime | None = Query(default=None),
          db: Session = Depends(get_db), user: User = Depends(_ops)):
    stmt = select(UsageRecord.usage_type, func.sum(UsageRecord.quantity), func.count()).group_by(UsageRecord.usage_type)
    stmt = _range(stmt, UsageRecord.recorded_at, date_from, date_to)
    rows = db.execute(stmt).all()
    return UsageReport(records=sum(int(c) for _, _, c in rows), totals={t: int(q or 0) for t, q, _ in rows})
