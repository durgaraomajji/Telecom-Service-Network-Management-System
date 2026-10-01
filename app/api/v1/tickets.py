from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import STAFF_ROLES, SUPPORT, get_or_404, own_customer, paging, resolve_customer_id
from app.api.v1.auth import current_user
from app.core.constants import TICKET_TRANSITIONS
from app.core.timeutil import utcnow
from app.db.session import get_db
from app.models.customer import Customer
from app.models.sla_tracking import SlaTracking
from app.models.support_ticket import SupportTicket
from app.models.ticket_comment import TicketComment
from app.models.ticket_history import TicketHistory
from app.models.user import User
from app.schemas.ticket import (CommentCreate, CommentResponse, TicketCreate, TicketHistoryResponse, TicketResponse,
                                TicketStatusUpdate)
from app.services import sla_service
from app.services.audit_service import audit
from app.services.notification_service import notify

router = APIRouter(prefix="/tickets", tags=["Support Tickets"])
CUSTOMER_MOVES = {("resolved", "closed"), ("resolved", "in_progress"), ("waiting_for_customer", "in_progress")}


def _can_view(db, user: User, ticket: SupportTicket) -> None:
    if user.role in SUPPORT:
        return
    if user.role in STAFF_ROLES:
        if ticket.assigned_to != user.id:
            raise HTTPException(403, "This ticket is not assigned to you")
        return
    mine = own_customer(db, user)
    if not mine or mine.id != ticket.customer_id:
        raise HTTPException(403, "You can only access your own tickets")


def _log(db, ticket, old, new, user, note=None):
    db.add(TicketHistory(ticket_id=ticket.id, old_status=old, new_status=new, changed_by=user.id, note=note))


@router.post("/", response_model=TicketResponse, status_code=201, summary="Raise a support ticket (SLA clock starts)")
def create_ticket(payload: TicketCreate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if user.role in STAFF_ROLES and user.role not in SUPPORT:
        raise HTTPException(403, f"Role '{user.role}' cannot raise tickets on behalf of customers")
    customer_id = resolve_customer_id(db, user, payload.customer_id)
    ticket = SupportTicket(ticket_number=f"TKT-{uuid4().hex[:10].upper()}", customer_id=customer_id,
                           subject=payload.subject, description=payload.description,
                           category=payload.category, priority=payload.priority, status="open",
                           created_at=utcnow(), updated_at=utcnow())
    db.add(ticket)
    db.flush()
    _log(db, ticket, None, "open", user, "Ticket created")
    sla_service.start_tracking(db, ticket)
    audit(db, user, "create", "ticket", ticket.id, f"{ticket.ticket_number} {ticket.priority}")
    notify(db, db.get(Customer, customer_id).user_id, "Ticket received",
           f"{ticket.ticket_number}: {ticket.subject}", "ticket")
    db.commit()
    db.refresh(ticket)
    return ticket


@router.get("/", response_model=list[TicketResponse])
def list_tickets(status: str | None = Query(default=None), priority: str | None = Query(default=None),
                 customer_id: int | None = Query(default=None), assigned_to: int | None = Query(default=None),
                 page=Depends(paging), db: Session = Depends(get_db), user: User = Depends(current_user)):
    skip, limit = page
    stmt = select(SupportTicket).order_by(SupportTicket.id.desc())
    if user.role in SUPPORT:
        if customer_id:
            stmt = stmt.where(SupportTicket.customer_id == customer_id)
        if assigned_to:
            stmt = stmt.where(SupportTicket.assigned_to == assigned_to)
    elif user.role in STAFF_ROLES:
        stmt = stmt.where(SupportTicket.assigned_to == user.id)
    else:
        mine = own_customer(db, user)
        if not mine:
            return []
        stmt = stmt.where(SupportTicket.customer_id == mine.id)
    if status:
        stmt = stmt.where(SupportTicket.status == status)
    if priority:
        stmt = stmt.where(SupportTicket.priority == priority)
    return list(db.scalars(stmt.offset(skip).limit(limit)).all())


@router.get("/{ticket_id}", response_model=TicketResponse)
def get_ticket(ticket_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    ticket = get_or_404(db, SupportTicket, ticket_id, "Ticket")
    _can_view(db, user, ticket)
    return ticket


@router.patch("/{ticket_id}/status", response_model=TicketResponse,
              summary="Move a ticket through its lifecycle (open -> in_progress -> resolved -> closed ...)")
def change_status(ticket_id: int, payload: TicketStatusUpdate, db: Session = Depends(get_db),
                  user: User = Depends(current_user)):
    ticket = get_or_404(db, SupportTicket, ticket_id, "Ticket")
    _can_view(db, user, ticket)
    old, new = ticket.status, payload.status
    if new not in TICKET_TRANSITIONS[old]:
        allowed = ", ".join(sorted(TICKET_TRANSITIONS[old])) or "none (ticket is closed)"
        raise HTTPException(409, f"Cannot move ticket from '{old}' to '{new}'. Allowed: {allowed}")
    if new == "assigned":
        raise HTTPException(409, "Use POST /ticket-assignments/ to assign a ticket")
    if user.role == "customer" and (old, new) not in CUSTOMER_MOVES:
        raise HTTPException(403, "Customers can only close a resolved ticket, reopen it, or reply to a waiting ticket")
    ticket.status = new
    track = db.scalar(select(SlaTracking).where(SlaTracking.ticket_id == ticket.id))
    now = utcnow()
    if new in ("resolved", "closed"):
        ticket.resolved_at = ticket.resolved_at or now
        if track and track.resolved_at is None:
            track.resolved_at = now
    elif old == "resolved":  # reopened
        ticket.resolved_at = None
        if track:
            track.resolved_at = None
    if user.role != "customer":
        sla_service.mark_responded(db, ticket.id)
    if track:
        sla_service.refresh_flags(track, now)
    _log(db, ticket, old, new, user, payload.note)
    audit(db, user, "status_change", "ticket", ticket.id, f"{old} -> {new}")
    if user.role != "customer":
        notify(db, db.get(Customer, ticket.customer_id).user_id, f"Ticket {ticket.ticket_number} is {new}",
               payload.note or ticket.subject, "ticket")
    db.commit()
    db.refresh(ticket)
    return ticket


@router.post("/{ticket_id}/comments", response_model=CommentResponse, status_code=201)
def add_comment(ticket_id: int, payload: CommentCreate, db: Session = Depends(get_db),
                user: User = Depends(current_user)):
    ticket = get_or_404(db, SupportTicket, ticket_id, "Ticket")
    _can_view(db, user, ticket)
    if ticket.status == "closed":
        raise HTTPException(409, "Ticket is closed")
    if payload.is_internal and user.role == "customer":
        raise HTTPException(403, "Customers cannot post internal notes")
    comment = TicketComment(ticket_id=ticket.id, author_id=user.id, comment=payload.comment,
                            is_internal=payload.is_internal)
    db.add(comment)
    if user.role != "customer":
        sla_service.mark_responded(db, ticket.id)
        if not payload.is_internal:
            notify(db, db.get(Customer, ticket.customer_id).user_id, f"Update on {ticket.ticket_number}",
                   payload.comment[:200], "ticket")
    elif ticket.status == "waiting_for_customer":
        ticket.status = "in_progress"
        _log(db, ticket, "waiting_for_customer", "in_progress", user, "Customer replied")
    if ticket.assigned_to and ticket.assigned_to != user.id and not payload.is_internal:
        notify(db, ticket.assigned_to, f"New comment on {ticket.ticket_number}", payload.comment[:200], "ticket")
    db.flush()
    audit(db, user, "comment", "ticket", ticket.id)
    db.commit()
    db.refresh(comment)
    return comment


@router.get("/{ticket_id}/comments", response_model=list[CommentResponse])
def list_comments(ticket_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    ticket = get_or_404(db, SupportTicket, ticket_id, "Ticket")
    _can_view(db, user, ticket)
    stmt = select(TicketComment).where(TicketComment.ticket_id == ticket_id).order_by(TicketComment.id)
    if user.role == "customer":
        stmt = stmt.where(TicketComment.is_internal.is_(False))
    return list(db.scalars(stmt).all())


@router.get("/{ticket_id}/history", response_model=list[TicketHistoryResponse])
def ticket_history(ticket_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    ticket = get_or_404(db, SupportTicket, ticket_id, "Ticket")
    _can_view(db, user, ticket)
    return list(db.scalars(select(TicketHistory).where(TicketHistory.ticket_id == ticket_id)
                           .order_by(TicketHistory.id)).all())
