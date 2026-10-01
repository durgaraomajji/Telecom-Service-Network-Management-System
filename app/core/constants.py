ROLES = ("super_admin", "operations_manager", "support_agent",
         "network_engineer", "field_technician", "customer")
SIM_STATUSES = ("available", "active", "suspended", "lost", "blocked", "deactivated")
TICKET_STATUSES = ("open", "assigned", "in_progress", "waiting_for_customer", "resolved", "closed")

SIM_TRANSITIONS = {
    "available": {"active", "blocked", "deactivated"},
    "active": {"suspended", "lost", "blocked", "deactivated"},
    "suspended": {"active", "lost", "blocked", "deactivated"},
    "lost": {"blocked", "deactivated"},
    "blocked": {"deactivated"},
    "deactivated": set(),
}
TICKET_TRANSITIONS = {
    "open": {"assigned", "in_progress", "closed"},
    "assigned": {"in_progress", "waiting_for_customer", "resolved"},
    "in_progress": {"waiting_for_customer", "resolved"},
    "waiting_for_customer": {"in_progress", "resolved", "closed"},
    "resolved": {"closed", "in_progress"},
    "closed": set(),
}
# priority -> (first response minutes, resolution minutes); overridden by rows in sla_rules
DEFAULT_SLA = {"critical": (30, 240), "high": (60, 480), "medium": (240, 1440), "low": (480, 4320)}
