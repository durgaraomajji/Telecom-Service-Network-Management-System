from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import STAFF_ROLES, SUPPORT, get_or_404, paging, require_roles, staff_only
from app.db.session import get_db
from app.models.customer import Customer
from app.models.support_ticket import SupportTicket
from app.models.ticket_assignment import TicketAssignment
from app.models.ticket_history import TicketHistory
from app.models.user import User
from app.schemas.ticket import AssignRequest, AssignmentResponse
from app.services import sla_service
from app.services.audit_service import audit
from app.services.notification_service import notify

router = APIRouter(prefix="/ticket-assignments", tags=["Ticket Assignments"])


@router.post("/", response_model=AssignmentResponse, status_code=201,
             summary="Assign a ticket to a staff member (open -> assigned)")
def assign_ticket(payload: AssignRequest, db: Session = Depends(get_db), actor: User = Depends(require_roles(*SUPPORT))):
    ticket = get_or_404(db, SupportTicket, payload.ticket_id, "Ticket")
    assignee = get_or_404(db, User, payload.assignee_id, "User")
    if ticket.status in ("resolved", "closed"):
        raise HTTPException(409, f"Ticket is {ticket.status} and cannot be assigned")
    if assignee.role not in STAFF_ROLES or not assignee.is_active:
        raise HTTPException(409, "Assignee must be an active staff member")
    if ticket.assigned_to == assignee.id:
        raise HTTPException(409, "Ticket is already assigned to this user")
    rec = TicketAssignment(ticket_id=ticket.id, assignee_id=assignee.id, assigned_by=actor.id)
    db.add(rec)
    ticket.assigned_to = assignee.id
    if ticket.status == "open":
        ticket.status = "assigned"
        db.add(TicketHistory(ticket_id=ticket.id, old_status="open", new_status="assigned",
                             changed_by=actor.id, note=f"Assigned to user {assignee.id}"))
    sla_service.mark_responded(db, ticket.id)
    db.flush()
    audit(db, actor, "assign", "ticket", ticket.id, f"assignee={assignee.id}")
    notify(db, assignee.id, "Ticket assigned to you", f"{ticket.ticket_number}: {ticket.subject}", "ticket")
    notify(db, db.get(Customer, ticket.customer_id).user_id, f"Ticket {ticket.ticket_number} assigned",
           "A support member is now handling your ticket.", "ticket")
    db.commit()
    db.refresh(rec)
    return rec


@router.get("/", response_model=list[AssignmentResponse])
def list_assignments(ticket_id: int | None = Query(default=None), assignee_id: int | None = Query(default=None),
                     page=Depends(paging), db: Session = Depends(get_db), user: User = Depends(staff_only)):
    skip, limit = page
    stmt = select(TicketAssignment).order_by(TicketAssignment.id.desc())
    if user.role not in SUPPORT:
        stmt = stmt.where(TicketAssignment.assignee_id == user.id)
    elif assignee_id:
        stmt = stmt.where(TicketAssignment.assignee_id == assignee_id)
    if ticket_id:
        stmt = stmt.where(TicketAssignment.ticket_id == ticket_id)
    return list(db.scalars(stmt.offset(skip).limit(limit)).all())


@router.get("/my", response_model=list[AssignmentResponse], summary="Tickets assigned to me")
def my_assignments(db: Session = Depends(get_db), user: User = Depends(staff_only)):
    return list(db.scalars(select(TicketAssignment).where(TicketAssignment.assignee_id == user.id)
                           .order_by(TicketAssignment.id.desc())).all())
