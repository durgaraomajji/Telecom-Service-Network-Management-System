from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import DEFAULT_SLA
from app.core.timeutil import utcnow
from app.models.sla_rule import SlaRule
from app.models.sla_tracking import SlaTracking
from app.models.support_ticket import SupportTicket


def sla_minutes(db: Session, priority: str) -> tuple[int, int]:
    rule = db.scalar(select(SlaRule).where(SlaRule.priority == priority))
    return (rule.response_minutes, rule.resolution_minutes) if rule else DEFAULT_SLA[priority]


def start_tracking(db: Session, ticket: SupportTicket) -> SlaTracking:
    resp, reso = sla_minutes(db, ticket.priority)
    track = SlaTracking(ticket_id=ticket.id, response_due=ticket.created_at + timedelta(minutes=resp),
                        resolution_due=ticket.created_at + timedelta(minutes=reso))
    db.add(track)
    return track


def refresh_flags(track: SlaTracking, now=None) -> SlaTracking:
    """Recompute breach flags from timestamps (open clocks are measured against 'now')."""
    now = now or utcnow()
    track.response_breached = (track.responded_at or now) > track.response_due
    track.resolution_breached = (track.resolved_at or now) > track.resolution_due
    return track


def mark_responded(db: Session, ticket_id: int):
    track = db.scalar(select(SlaTracking).where(SlaTracking.ticket_id == ticket_id))
    if track and track.responded_at is None:
        track.responded_at = utcnow()
        refresh_flags(track)
