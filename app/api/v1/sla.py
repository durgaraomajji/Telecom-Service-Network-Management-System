from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import OPS, STAFF_ROLES, SUPPORT, ensure_customer_access, get_or_404, paging, require_roles, staff_only
from app.api.v1.auth import current_user
from app.core.constants import DEFAULT_SLA
from app.core.timeutil import utcnow
from app.db.session import get_db
from app.models.sla_rule import SlaRule
from app.models.sla_tracking import SlaTracking
from app.models.support_ticket import SupportTicket
from app.models.user import User
from app.schemas.sla import SlaRuleCreate, SlaRuleResponse, SlaRuleUpdate, SlaTrackingResponse
from app.services import sla_service
from app.services.audit_service import audit
from app.services.notification_service import notify

router = APIRouter(prefix="/sla", tags=["SLA"])
PRIORITIES = ("critical", "high", "medium", "low")


def _rules(db):
    custom = {r.priority: r for r in db.scalars(select(SlaRule)).all()}
    out = []
    for p in PRIORITIES:
        if p in custom:
            out.append(SlaRuleResponse(priority=p, response_minutes=custom[p].response_minutes,
                                       resolution_minutes=custom[p].resolution_minutes))
        else:
            out.append(SlaRuleResponse(priority=p, response_minutes=DEFAULT_SLA[p][0],
                                       resolution_minutes=DEFAULT_SLA[p][1], is_default=True))
    return out


def _view(track: SlaTracking, ticket: SupportTicket) -> SlaTrackingResponse:
    resp = SlaTrackingResponse.model_validate(track)
    resp.ticket_number, resp.priority, resp.ticket_status = ticket.ticket_number, ticket.priority, ticket.status
    return resp


@router.get("/rules", response_model=list[SlaRuleResponse], summary="SLA targets per priority (defaults + custom)")
def list_rules(db: Session = Depends(get_db), user: User = Depends(staff_only)):
    return _rules(db)


@router.post("/rules", response_model=SlaRuleResponse, status_code=201, summary="Create a custom SLA rule")
def create_rule(payload: SlaRuleCreate, db: Session = Depends(get_db), actor: User = Depends(require_roles(*OPS))):
    if payload.resolution_minutes < payload.response_minutes:
        raise HTTPException(422, "resolution_minutes must be >= response_minutes")
    if db.scalar(select(SlaRule).where(SlaRule.priority == payload.priority)):
        raise HTTPException(409, f"Rule for '{payload.priority}' exists; use PUT /sla/rules/{payload.priority}")
    db.add(SlaRule(**payload.model_dump()))
    audit(db, actor, "create", "sla_rule", None, payload.priority)
    db.commit()
    return next(r for r in _rules(db) if r.priority == payload.priority)


@router.put("/rules/{priority}", response_model=SlaRuleResponse, summary="Update (or create) the rule for a priority")
def update_rule(priority: str, payload: SlaRuleUpdate, db: Session = Depends(get_db),
                actor: User = Depends(require_roles(*OPS))):
    if priority not in PRIORITIES:
        raise HTTPException(404, f"Unknown priority '{priority}'. Use one of {', '.join(PRIORITIES)}")
    if payload.resolution_minutes < payload.response_minutes:
        raise HTTPException(422, "resolution_minutes must be >= response_minutes")
    rule = db.scalar(select(SlaRule).where(SlaRule.priority == priority))
    if rule:
        rule.response_minutes, rule.resolution_minutes = payload.response_minutes, payload.resolution_minutes
    else:
        db.add(SlaRule(priority=priority, **payload.model_dump()))
    audit(db, actor, "update", "sla_rule", None, priority)
    db.commit()
    return next(r for r in _rules(db) if r.priority == priority)


@router.get("/tracking", response_model=list[SlaTrackingResponse], summary="SLA clocks for tickets (support staff)")
def list_tracking(breached: bool | None = Query(default=None), ticket_id: int | None = Query(default=None),
                  page=Depends(paging), db: Session = Depends(get_db), user: User = Depends(require_roles(*SUPPORT))):
    skip, limit = page
    stmt = (select(SlaTracking, SupportTicket).join(SupportTicket, SupportTicket.id == SlaTracking.ticket_id)
            .order_by(SlaTracking.id.desc()))
    if ticket_id:
        stmt = stmt.where(SlaTracking.ticket_id == ticket_id)
    rows = db.execute(stmt.offset(skip).limit(limit)).all()
    now, out = utcnow(), []
    for track, ticket in rows:
        sla_service.refresh_flags(track, now)
        if breached is None or (track.response_breached or track.resolution_breached) == breached:
            out.append(_view(track, ticket))
    db.commit()
    return out


@router.get("/tracking/{ticket_id}", response_model=SlaTrackingResponse)
def ticket_tracking(ticket_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    ticket = get_or_404(db, SupportTicket, ticket_id, "Ticket")
    ensure_customer_access(db, user, ticket.customer_id)
    track = db.scalar(select(SlaTracking).where(SlaTracking.ticket_id == ticket_id))
    if not track:
        raise HTTPException(404, "No SLA tracking for this ticket")
    sla_service.refresh_flags(track)
    db.commit()
    return _view(track, ticket)


@router.post("/check-breaches", summary="Re-evaluate every open ticket and notify about new SLA breaches (ops)")
def check_breaches(db: Session = Depends(get_db), actor: User = Depends(require_roles(*OPS))):
    rows = db.execute(select(SlaTracking, SupportTicket).join(SupportTicket, SupportTicket.id == SlaTracking.ticket_id)
                      .where(SupportTicket.status.notin_(("resolved", "closed")))).all()
    now, newly, total = utcnow(), [], 0
    for track, ticket in rows:
        before = (track.response_breached, track.resolution_breached)
        sla_service.refresh_flags(track, now)
        if any((track.response_breached, track.resolution_breached)):
            total += 1
        if (track.response_breached, track.resolution_breached) != before and any((track.response_breached, track.resolution_breached)):
            newly.append(ticket.ticket_number)
            notify(db, ticket.assigned_to or actor.id, f"SLA breach: {ticket.ticket_number}",
                   f"{ticket.subject} ({ticket.priority})", "sla")
    audit(db, actor, "check_breaches", "sla", None, f"newly={len(newly)}")
    db.commit()
    return {"checked": len(rows), "breached": total, "newly_breached": newly}
