from pydantic import BaseModel


class DashboardSummary(BaseModel):
    customers: int
    users: int
    subscriptions_by_status: dict[str, int]
    sims_by_status: dict[str, int]
    tickets_by_status: dict[str, int]
    open_tickets: int
    sla_breached_tickets: int
    active_outages: int
    towers_by_status: dict[str, int]
    faulty_equipment: int
    technicians_available: int
    monthly_recurring_revenue: float


class CustomerDashboard(BaseModel):
    customer_id: int | None
    kyc_status: str | None
    active_subscriptions: int
    open_tickets: int
    open_service_requests: int
    unread_notifications: int
    active_outages_in_network: int
